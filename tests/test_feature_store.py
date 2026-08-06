from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from credit_scoring.feature_store import (
    UNASSIGNED_FAMILY,
    FeatureStoreError,
    block_paths,
    list_blocks,
    load_block,
    merge_blocks,
    save_block,
)

FAMILIES = {
    "BUREAU_LOAN_COUNT": "counts",
    "BUREAU_ACTIVE_COUNT": "counts",
    "BUREAU_DEBT_SUM": "amounts",
    "BUREAU_DAYS_CREDIT_MAX": "recency",
}


def make_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "SK_ID_CURR": [100001, 100002, 100003],
            "BUREAU_LOAN_COUNT": [3, 0, 7],
            "BUREAU_ACTIVE_COUNT": [1, 0, 4],
            "BUREAU_DEBT_SUM": [1500.0, np.nan, 90210.5],
            "BUREAU_DAYS_CREDIT_MAX": [-120, np.nan, -7],
        }
    )


def save_default(tmp_path, frame=None, **overrides):
    kwargs = {
        "root": tmp_path,
        "builder_version": "bureau-v1",
        "families": FAMILIES,
    }
    kwargs.update(overrides)
    return save_block(make_frame() if frame is None else frame, "bureau", **kwargs)


def test_round_trip_preserves_values_dtypes_and_missingness(tmp_path) -> None:
    original = make_frame()
    save_default(tmp_path, original)
    block = load_block("bureau", root=tmp_path)

    pd.testing.assert_frame_equal(block.frame, original)
    assert block.frame["BUREAU_DEBT_SUM"].isna().tolist() == [False, True, False]
    assert block.frame["BUREAU_LOAN_COUNT"].dtype == original["BUREAU_LOAN_COUNT"].dtype


def test_manifest_records_families_and_cardinality(tmp_path) -> None:
    manifest = save_default(tmp_path)

    assert manifest.row_count == 3
    assert manifest.unique_key_count == 3
    assert manifest.family_names == ("counts", "amounts", "recency")
    assert manifest.features_in_family("counts") == (
        "BUREAU_LOAN_COUNT",
        "BUREAU_ACTIVE_COUNT",
    )


def test_unlabelled_features_are_recorded_as_unassigned(tmp_path) -> None:
    manifest = save_default(tmp_path, families={"BUREAU_LOAN_COUNT": "counts"})

    assert manifest.families["BUREAU_DEBT_SUM"] == UNASSIGNED_FAMILY
    assert manifest.features_in_family(UNASSIGNED_FAMILY) == (
        "BUREAU_ACTIVE_COUNT",
        "BUREAU_DEBT_SUM",
        "BUREAU_DAYS_CREDIT_MAX",
    )


def test_family_label_for_unknown_column_is_rejected(tmp_path) -> None:
    with pytest.raises(ValueError, match="unknown columns"):
        save_default(tmp_path, families={**FAMILIES, "BUREAU_TYPO_COUNT": "counts"})


def test_duplicate_keys_are_rejected(tmp_path) -> None:
    frame = make_frame()
    frame.loc[2, "SK_ID_CURR"] = 100001
    with pytest.raises(ValueError, match="duplicate values"):
        save_default(tmp_path, frame)


def test_missing_key_column_is_rejected(tmp_path) -> None:
    with pytest.raises(ValueError, match="missing from the frame"):
        save_default(tmp_path, make_frame().drop(columns=["SK_ID_CURR"]))


def test_empty_builder_version_is_rejected(tmp_path) -> None:
    with pytest.raises(ValueError, match="builder_version"):
        save_default(tmp_path, builder_version="")


def test_stale_builder_version_fails_loudly(tmp_path) -> None:
    save_default(tmp_path, builder_version="bureau-v1")

    loaded = load_block("bureau", root=tmp_path, expected_builder_version="bureau-v1")
    assert loaded.manifest.builder_version == "bureau-v1"

    with pytest.raises(FeatureStoreError, match="does not match expected"):
        load_block("bureau", root=tmp_path, expected_builder_version="bureau-v2")


def test_load_detects_parquet_diverging_from_manifest(tmp_path) -> None:
    save_default(tmp_path)
    parquet_path, _ = block_paths(tmp_path, "bureau")
    make_frame().drop(columns=["BUREAU_DEBT_SUM"]).to_parquet(parquet_path, index=False)

    with pytest.raises(FeatureStoreError, match="do not match the manifest"):
        load_block("bureau", root=tmp_path)


def test_load_detects_row_count_drift(tmp_path) -> None:
    save_default(tmp_path)
    parquet_path, _ = block_paths(tmp_path, "bureau")
    make_frame().iloc[:2].to_parquet(parquet_path, index=False)

    with pytest.raises(FeatureStoreError, match="expected 3 rows"):
        load_block("bureau", root=tmp_path)


def test_missing_block_raises_file_not_found(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="missing feature block"):
        load_block("bureau", root=tmp_path)


def test_manifest_is_human_readable_json(tmp_path) -> None:
    save_default(tmp_path)
    _, manifest_path = block_paths(tmp_path, "bureau")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert payload["name"] == "bureau"
    assert payload["key_column"] == "SK_ID_CURR"
    assert {"name": "BUREAU_DEBT_SUM", "family": "amounts"} in payload["features"]


def test_list_blocks_reports_saved_names(tmp_path) -> None:
    assert list_blocks(tmp_path) == []
    save_default(tmp_path)
    save_block(
        make_frame().rename(columns=lambda c: c.replace("BUREAU", "POS")),
        "pos_cash",
        root=tmp_path,
        builder_version="pos-v1",
    )
    assert list_blocks(tmp_path) == ["bureau", "pos_cash"]


def test_select_returns_key_plus_requested_families(tmp_path) -> None:
    save_default(tmp_path)
    block = load_block("bureau", root=tmp_path)

    selected = block.select(["counts", "amounts"])
    assert list(selected.columns) == [
        "SK_ID_CURR",
        "BUREAU_LOAN_COUNT",
        "BUREAU_ACTIVE_COUNT",
        "BUREAU_DEBT_SUM",
    ]

    with pytest.raises(KeyError, match="unknown families"):
        block.select("delinquency")


def test_merge_blocks_left_joins_and_preserves_base_rows(tmp_path) -> None:
    save_default(tmp_path)
    block = load_block("bureau", root=tmp_path)
    base = pd.DataFrame({"SK_ID_CURR": [100001, 100002, 100003, 100004]})

    merged = merge_blocks(base, [block])

    assert len(merged) == 4
    assert merged.loc[merged["SK_ID_CURR"] == 100004, "BUREAU_LOAN_COUNT"].isna().all()


def test_merge_blocks_can_restrict_to_families(tmp_path) -> None:
    save_default(tmp_path)
    block = load_block("bureau", root=tmp_path)
    base = pd.DataFrame({"SK_ID_CURR": [100001, 100002, 100003]})

    merged = merge_blocks(base, [block], families={"bureau": "counts"})

    assert list(merged.columns) == [
        "SK_ID_CURR",
        "BUREAU_LOAN_COUNT",
        "BUREAU_ACTIVE_COUNT",
    ]


def test_merge_blocks_rejects_colliding_column_names(tmp_path) -> None:
    save_default(tmp_path)
    block = load_block("bureau", root=tmp_path)
    base = pd.DataFrame({"SK_ID_CURR": [100001], "BUREAU_LOAN_COUNT": [99]})

    with pytest.raises(ValueError, match="already present"):
        merge_blocks(base, [block])
