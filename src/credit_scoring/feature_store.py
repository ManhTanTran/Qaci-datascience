"""Versioned on-disk storage for engineered feature blocks.

A *block* is one feature matrix at a single grain, stored as a Parquet file next
to a JSON manifest. The manifest is what makes a block reusable: it records the
key column, the exact column order, the semantic family of every feature and the
``builder_version`` of the code that produced them.

Blocks are the unit of storage; families are labels inside the manifest. A
feature belongs to exactly one source table but the same semantic family can span
several tables, so grouping by label lets callers slice either way without
duplicating data on disk.

``builder_version`` is mandatory. Feature code changes far more often than the
raw data does, and a cache that silently returns values from a previous formula
is worse than no cache at all: nothing fails, the numbers are simply wrong.
:func:`load_block` refuses to hand back a block whose version does not match what
the caller expects.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

UNASSIGNED_FAMILY = "unassigned"
MANIFEST_SCHEMA_VERSION = "1.0"


class FeatureStoreError(RuntimeError):
    """Raised when a stored block fails verification."""


@dataclass(frozen=True)
class BlockManifest:
    """Metadata describing one stored feature block."""

    name: str
    key_column: str
    builder_version: str
    feature_names: tuple[str, ...]
    families: Mapping[str, str]
    row_count: int
    unique_key_count: int
    created_at: str
    schema_version: str = MANIFEST_SCHEMA_VERSION

    def features_in_family(self, family: str) -> tuple[str, ...]:
        """Return the feature names labelled with ``family``, in stored order."""

        return tuple(name for name in self.feature_names if self.families[name] == family)

    @property
    def family_names(self) -> tuple[str, ...]:
        """Return the distinct families present, in stored order."""

        seen: dict[str, None] = {}
        for name in self.feature_names:
            seen.setdefault(self.families[name], None)
        return tuple(seen)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "key_column": self.key_column,
            "builder_version": self.builder_version,
            "row_count": self.row_count,
            "unique_key_count": self.unique_key_count,
            "created_at": self.created_at,
            "features": [
                {"name": name, "family": self.families[name]} for name in self.feature_names
            ],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> BlockManifest:
        features = payload["features"]
        return cls(
            name=payload["name"],
            key_column=payload["key_column"],
            builder_version=payload["builder_version"],
            feature_names=tuple(entry["name"] for entry in features),
            families={entry["name"]: entry["family"] for entry in features},
            row_count=int(payload["row_count"]),
            unique_key_count=int(payload["unique_key_count"]),
            created_at=payload["created_at"],
            schema_version=payload.get("schema_version", MANIFEST_SCHEMA_VERSION),
        )


@dataclass(frozen=True)
class FeatureBlock:
    """A loaded feature matrix together with its verified manifest."""

    frame: pd.DataFrame
    manifest: BlockManifest

    @property
    def name(self) -> str:
        return self.manifest.name

    def select(self, families: str | Sequence[str]) -> pd.DataFrame:
        """Return the key column plus every feature in the requested families."""

        requested = (families,) if isinstance(families, str) else tuple(families)
        unknown = sorted(set(requested).difference(self.manifest.family_names))
        if unknown:
            raise KeyError(
                f"{self.name}: unknown families {unknown}; "
                f"available: {list(self.manifest.family_names)}"
            )
        columns = [
            name for name in self.manifest.feature_names if self.manifest.families[name] in requested
        ]
        return self.frame[[self.manifest.key_column, *columns]]


def block_paths(root: str | Path, name: str) -> tuple[Path, Path]:
    """Return the ``(parquet, manifest)`` paths for a block name."""

    directory = Path(root).expanduser()
    return directory / f"{name}.parquet", directory / f"{name}.manifest.json"


def save_block(
    frame: pd.DataFrame,
    name: str,
    *,
    root: str | Path,
    builder_version: str,
    families: Mapping[str, str] | None = None,
    key_column: str = "SK_ID_CURR",
) -> BlockManifest:
    """Write ``frame`` as a versioned feature block and return its manifest.

    ``families`` maps feature names to a semantic label; anything omitted is
    recorded as ``unassigned``. Labels for columns that do not exist are treated
    as an error rather than ignored, so a typo surfaces at write time instead of
    silently dropping a feature out of every later family selection.
    """

    if not builder_version:
        raise ValueError(f"{name}: builder_version must be a non-empty string.")
    if key_column not in frame.columns:
        raise ValueError(f"{name}: key column {key_column!r} is missing from the frame.")

    duplicated = frame.columns[frame.columns.duplicated()].unique().tolist()
    if duplicated:
        raise ValueError(f"{name}: duplicated column names: {sorted(duplicated)}")
    if not frame[key_column].is_unique:
        raise ValueError(f"{name}: key column {key_column!r} contains duplicate values.")
    if frame[key_column].isna().any():
        raise ValueError(f"{name}: key column {key_column!r} contains missing values.")

    feature_names = tuple(column for column in frame.columns if column != key_column)
    labels = dict(families or {})
    unknown = sorted(set(labels).difference(feature_names))
    if unknown:
        raise ValueError(f"{name}: family labels for unknown columns: {unknown}")

    manifest = BlockManifest(
        name=name,
        key_column=key_column,
        builder_version=builder_version,
        feature_names=feature_names,
        families={column: labels.get(column, UNASSIGNED_FAMILY) for column in feature_names},
        row_count=len(frame),
        unique_key_count=int(frame[key_column].nunique()),
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )

    parquet_path, manifest_path = block_paths(root, name)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(parquet_path, index=False)
    manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")
    return manifest


def load_block(
    name: str,
    *,
    root: str | Path,
    expected_builder_version: str | None = None,
) -> FeatureBlock:
    """Load a block and verify it still matches its manifest.

    Passing ``expected_builder_version`` turns a stale cache into a loud failure,
    which is the only reliable way to notice that a feature formula changed after
    the block was written.
    """

    parquet_path, manifest_path = block_paths(root, name)
    if not parquet_path.exists():
        raise FileNotFoundError(f"{name}: missing feature block at {parquet_path}")
    if not manifest_path.exists():
        raise FileNotFoundError(f"{name}: missing manifest at {manifest_path}")

    manifest = BlockManifest.from_dict(json.loads(manifest_path.read_text(encoding="utf-8")))
    if expected_builder_version is not None and manifest.builder_version != expected_builder_version:
        raise FeatureStoreError(
            f"{name}: stored builder_version {manifest.builder_version!r} does not match "
            f"expected {expected_builder_version!r}; rebuild the block."
        )

    frame = pd.read_parquet(parquet_path)
    expected_columns = [manifest.key_column, *manifest.feature_names]
    if list(frame.columns) != expected_columns:
        missing = sorted(set(expected_columns).difference(frame.columns))
        extra = sorted(set(frame.columns).difference(expected_columns))
        raise FeatureStoreError(
            f"{name}: stored columns do not match the manifest "
            f"(missing={missing}, unexpected={extra})."
        )
    if len(frame) != manifest.row_count:
        raise FeatureStoreError(
            f"{name}: expected {manifest.row_count} rows, found {len(frame)}."
        )
    if not frame[manifest.key_column].is_unique:
        raise FeatureStoreError(f"{name}: key column {manifest.key_column!r} is not unique.")

    return FeatureBlock(frame=frame, manifest=manifest)


def list_blocks(root: str | Path) -> list[str]:
    """Return the names of every block stored under ``root``, sorted."""

    directory = Path(root).expanduser()
    if not directory.exists():
        return []
    return sorted(path.name[: -len(".manifest.json")] for path in directory.glob("*.manifest.json"))


def merge_blocks(
    base: pd.DataFrame,
    blocks: Iterable[FeatureBlock],
    *,
    key_column: str = "SK_ID_CURR",
    families: Mapping[str, str | Sequence[str]] | None = None,
) -> pd.DataFrame:
    """Left-join feature blocks onto ``base`` and return the widened frame.

    ``families`` optionally restricts individual blocks to a subset of their
    families, keyed by block name. Column collisions are rejected outright: a
    silently suffixed ``_x``/``_y`` column would break the correspondence between
    the model matrix and the manifests that describe it.
    """

    if key_column not in base.columns:
        raise ValueError(f"Base frame is missing the key column {key_column!r}.")

    selection = dict(families or {})
    merged = base
    for block in blocks:
        if block.manifest.key_column != key_column:
            raise ValueError(
                f"{block.name}: block is keyed by {block.manifest.key_column!r}, "
                f"cannot join on {key_column!r}."
            )
        frame = block.select(selection[block.name]) if block.name in selection else block.frame
        collisions = sorted(set(frame.columns).intersection(merged.columns).difference({key_column}))
        if collisions:
            raise ValueError(f"{block.name}: column names already present: {collisions}")
        merged = merged.merge(frame, on=key_column, how="left")

    return merged
