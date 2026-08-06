"""Aggregation helpers shared by the Home Credit auxiliary-table feature modules.

Every feature module declares its output as an explicit sequence of
:class:`Aggregation` specifications rather than letting pandas name the columns.
Two properties follow from that, and both are required for feature blocks to be
reusable:

* The output schema is a function of the code, not of the data. Deriving the
  column set from whichever categories or dtypes happen to be present makes a
  block written from a sample incompatible with one written from full data, and
  the manifest cannot detect it because both files are internally consistent.
* Each output column carries its semantic family, so family labels are produced
  by the same declaration that produces the values and cannot drift apart.

``sum`` is deliberately split into two statistics. ``SUM`` totals indicator
columns, where an absent row genuinely means zero. ``SUM_OBSERVED`` totals
measured amounts with ``min_count=1``, so a client whose source rows are all
missing keeps ``NaN`` instead of being reported as owing nothing. Collapsing
those two cases is the single most consequential mistake available here: "no
recorded debt" and "debt of zero" are different risks.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# Characters LightGBM rejects inside feature names. Category values such as
# "Spouse, partner" produce them as soon as a label is pasted into a column name.
UNSAFE_NAME_CHARACTERS = frozenset('"\\[]{}:,')

STAT_SUFFIXES: Mapping[str, str] = {
    "count": "COUNT",
    "last": "LAST",
    "max": "MAX",
    "mean": "MEAN",
    "min": "MIN",
    "nunique": "NUNIQUE",
    "std": "STD",
    "sum": "SUM",
    "sum_observed": "SUM",
    "var": "VAR",
}


def sum_observed(values: pd.Series) -> float:
    """Total ``values``, returning ``NaN`` when nothing was observed."""

    return values.sum(min_count=1)


def _aggfunc(stat: str) -> str | Callable[[pd.Series], object]:
    if stat == "sum_observed":
        return sum_observed
    if stat not in STAT_SUFFIXES:
        raise ValueError(f"Unsupported statistic: {stat!r}")
    return stat


@dataclass(frozen=True)
class Aggregation:
    """One source column, the statistics taken from it and their family."""

    column: str
    stats: Sequence[str]
    family: str
    name: str | None = None

    def output_names(self, prefix: str) -> tuple[str, ...]:
        stem = self.name or self.column
        return tuple(f"{prefix}{stem}_{STAT_SUFFIXES[stat]}" for stat in self.stats)


@dataclass(frozen=True)
class AggregationResult:
    """An aggregated frame together with the family of each produced column."""

    frame: pd.DataFrame
    families: dict[str, str] = field(default_factory=dict)


def sanitize_feature_names(names: Iterable[str]) -> list[str]:
    """Replace characters LightGBM rejects in feature names with underscores."""

    return [
        "".join("_" if character in UNSAFE_NAME_CHARACTERS else character for character in name)
        for name in names
    ]


def assert_unique_key(frame: pd.DataFrame, key_column: str, context: str) -> None:
    """Raise when ``key_column`` is not a valid one-row-per-entity key."""

    if key_column not in frame.columns:
        raise ValueError(f"{context}: missing key column {key_column!r}.")
    if not frame[key_column].is_unique:
        duplicated = int(frame[key_column].duplicated().sum())
        raise ValueError(f"{context}: {key_column!r} has {duplicated} duplicate values.")


def aggregate(
    frame: pd.DataFrame,
    group_columns: str | Sequence[str],
    specs: Sequence[Aggregation],
    *,
    prefix: str = "",
) -> AggregationResult:
    """Aggregate ``frame`` into exactly the columns declared by ``specs``.

    Source columns that are absent from ``frame`` are an error rather than a
    silently skipped feature; a schema change should stop the run, not quietly
    shrink the block.
    """

    keys = [group_columns] if isinstance(group_columns, str) else list(group_columns)
    missing_keys = [key for key in keys if key not in frame.columns]
    if missing_keys:
        raise ValueError(f"Missing group columns: {missing_keys}")

    missing_sources = sorted({spec.column for spec in specs}.difference(frame.columns))
    if missing_sources:
        raise ValueError(f"Missing source columns for aggregation: {missing_sources}")

    named: dict[str, pd.NamedAgg] = {}
    families: dict[str, str] = {}
    for spec in specs:
        for stat, output in zip(spec.stats, spec.output_names(prefix), strict=True):
            if output in named:
                raise ValueError(f"Duplicate aggregation output name: {output}")
            named[output] = pd.NamedAgg(column=spec.column, aggfunc=_aggfunc(stat))
            families[output] = spec.family

    aggregated = frame.groupby(keys, dropna=False).agg(**named).reset_index()
    return AggregationResult(frame=aggregated, families=families)


def one_hot_counts(
    frame: pd.DataFrame,
    column: str,
    *,
    categories: Sequence[str],
    group_column: str,
    prefix: str,
    family: str,
) -> AggregationResult:
    """Count occurrences of each declared category per group.

    ``categories`` is a fixed list rather than whatever the data contains, so the
    produced columns are identical for a five-thousand-row sample and for the
    full table. Values outside the list are counted together under ``OTHER``,
    which keeps the counts summing to the group size.
    """

    if column not in frame.columns:
        raise ValueError(f"Missing categorical column: {column!r}")
    if len(set(categories)) != len(categories):
        raise ValueError(f"{column}: duplicate categories declared.")

    values = frame[column].astype("object")
    known = values.isin(list(categories))
    labels = pd.Categorical(
        values.where(known, other="OTHER"),
        categories=[*categories, "OTHER"],
    )
    counts = (
        pd.DataFrame({group_column: frame[group_column].to_numpy(), "_label": labels})
        .pivot_table(
            index=group_column,
            columns="_label",
            aggfunc="size",
            fill_value=0,
            observed=False,
        )
        .reindex(columns=[*categories, "OTHER"], fill_value=0)
    )
    counts.columns = sanitize_feature_names(f"{prefix}{label}_COUNT" for label in counts.columns)
    counts = counts.astype("int32").reset_index()
    return AggregationResult(
        frame=counts,
        families={column: family for column in counts.columns if column != group_column},
    )


def merge_features(
    left: AggregationResult,
    right: AggregationResult,
    *,
    on: str,
    how: str = "left",
) -> AggregationResult:
    """Join two aggregation results, rejecting overlapping feature names."""

    collisions = sorted(
        set(right.frame.columns).intersection(left.frame.columns).difference({on})
    )
    if collisions:
        raise ValueError(f"Overlapping feature names during merge: {collisions}")
    return AggregationResult(
        frame=left.frame.merge(right.frame, on=on, how=how),
        families={**left.families, **right.families},
    )


def fill_counts(
    result: AggregationResult,
    columns: Sequence[str],
    *,
    dtype: str = "int32",
) -> AggregationResult:
    """Fill missing count columns with zero after an outer or left join.

    Counts are the one family where an absent row really does mean zero: the
    client exists and simply has no rows of that kind. Amounts, ratios and time
    features keep ``NaN``.
    """

    frame = result.frame.copy()
    for column in columns:
        if column not in frame.columns:
            raise ValueError(f"Cannot fill unknown count column: {column!r}")
        frame[column] = frame[column].fillna(0).astype(dtype)
    return AggregationResult(frame=frame, families=dict(result.families))


def longest_true_streak(flags: pd.Series) -> int:
    """Length of the longest run of ``True`` values."""

    values = flags.to_numpy(dtype=bool)
    if values.size == 0 or not values.any():
        return 0
    longest = current = 0
    for value in values:
        current = current + 1 if value else 0
        longest = max(longest, current)
    return int(longest)


def count_true_episodes(flags: pd.Series) -> int:
    """Number of distinct runs of ``True`` values."""

    values = flags.to_numpy(dtype=bool)
    if values.size == 0 or not values.any():
        return 0
    return int(np.count_nonzero(values & ~np.concatenate(([False], values[:-1]))))


def linear_trend_slope(values: pd.Series) -> float:
    """Ordinary least squares slope of ``values`` against their position.

    The caller controls the ordering, and the sign follows it: passing a series
    sorted most-recent-first reverses the meaning of the slope. Feature modules
    therefore sort oldest-first before calling this.
    """

    observed = pd.to_numeric(values, errors="coerce").dropna()
    if len(observed) < 2:
        return float("nan")
    positions = np.arange(len(observed), dtype="float64")
    measurements = observed.to_numpy(dtype="float64")
    centered = positions - positions.mean()
    denominator = float((centered**2).sum())
    if denominator == 0.0:
        return 0.0
    return float((centered * (measurements - measurements.mean())).sum() / denominator)
