"""Download a small, reproducible row sample from the public Hugging Face viewer."""

from __future__ import annotations

import argparse
import email.utils
import hashlib
import io
import json
import math
import os
import random
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DATASET_ID = "tinixai/vietnam-real-estates"
DATASET_URL = f"https://huggingface.co/datasets/{DATASET_ID}"
LICENSE_ID = "cc-by-nc-4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by-nc/4.0/"
HF_API = "https://huggingface.co/api/datasets/"
ROWS_API = "https://datasets-server.huggingface.co/rows"
PARQUET_API = "https://datasets-server.huggingface.co/parquet"
SIZE_API = "https://datasets-server.huggingface.co/size"
PAGE_SIZE = 100
ROW_REQUEST_INTERVAL_SECONDS = 1.0
ROW_RATE_LIMIT_RETRIES = 4
MAX_SAMPLE_ROWS = 5_000
MAX_TOTAL_SAMPLE_ROWS = 10_000
SAMPLE_STRATA = 100
USER_AGENT = "WardPriceDaily-Historical-Research/1.0"
EXPECTED_SPLIT_ROWS = 3_500_744
SAMPLE_COLUMNS = (
    "name",
    "property_type_name",
    "province_name",
    "district_name",
    "ward_name",
    "street_name",
    "project_name",
    "price",
    "area",
    "published_at",
)


def _get_json(url: str) -> dict:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=60) as response:
        if response.status != 200:
            raise RuntimeError(f"Unexpected HTTP status {response.status} for Hugging Face API")
        return json.loads(response.read())


def _revision_metadata() -> dict:
    metadata = _get_json(HF_API + DATASET_ID)
    card = metadata.get("cardData") or {}
    if metadata.get("id") != DATASET_ID:
        raise RuntimeError("Hugging Face returned a different dataset id")
    if card.get("license") != LICENSE_ID:
        raise RuntimeError(
            f"Dataset license changed: expected {LICENSE_ID}, received {card.get('license')!r}"
        )
    if metadata.get("private") or metadata.get("gated"):
        raise RuntimeError("Dataset is not publicly accessible; refusing authenticated access")
    return {
        "dataset_id": metadata["id"],
        "revision": metadata.get("sha"),
        "last_modified": metadata.get("lastModified"),
        "license_id": card.get("license"),
        "private": metadata.get("private"),
        "gated": metadata.get("gated"),
    }


def _row_page(offset: int, length: int) -> dict:
    query = urlencode(
        {
            "dataset": DATASET_ID,
            "config": "default",
            "split": "train",
            "offset": offset,
            "length": length,
        }
    )
    url = f"{ROWS_API}?{query}"
    for attempt in range(ROW_RATE_LIMIT_RETRIES + 1):
        if attempt == 0:
            time.sleep(ROW_REQUEST_INTERVAL_SECONDS)
        try:
            return _get_json(url)
        except HTTPError as exc:
            if exc.code != 429 or attempt >= ROW_RATE_LIMIT_RETRIES:
                raise RuntimeError(
                    f"Hugging Face row sample request failed at offset {offset}: {exc}"
                ) from exc
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            try:
                delay_seconds = max(0.0, float(retry_after)) if retry_after else None
            except ValueError:
                try:
                    retry_at = email.utils.parsedate_to_datetime(retry_after)
                    delay_seconds = max(0.0, retry_at.timestamp() - time.time())
                except (TypeError, ValueError, OverflowError):
                    delay_seconds = None
            if delay_seconds is None:
                delay_seconds = min(120.0, 30.0 * (2**attempt))
            print(
                f"Hugging Face rate limited /rows at offset {offset}; "
                f"waiting {delay_seconds:g}s before retry {attempt + 1}/{ROW_RATE_LIMIT_RETRIES}",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(delay_seconds)
        except (URLError, TimeoutError) as exc:
            raise RuntimeError(
                f"Hugging Face row sample request failed at offset {offset}: {exc}"
            ) from exc
    raise AssertionError("unreachable rate-limit retry loop exit")


class _ParquetRangeReader(io.RawIOBase):
    """Read only byte ranges from a remote Parquet footer; never fetch a full shard."""

    def __init__(self, url: str, size: int) -> None:
        self.url = url
        self.size = size
        self.position = 0
        self.bytes_read = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.position

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            self.position = offset
        elif whence == io.SEEK_CUR:
            self.position += offset
        elif whence == io.SEEK_END:
            self.position = self.size + offset
        else:
            raise ValueError(f"Unsupported seek mode: {whence}")
        if not 0 <= self.position <= self.size:
            raise ValueError("Parquet footer reader attempted to seek outside the shard")
        return self.position

    def read(self, length: int = -1) -> bytes:
        if length is None or length < 0:
            length = self.size - self.position
        length = min(length, self.size - self.position)
        if length <= 0:
            return b""
        end = self.position + length - 1
        request = Request(
            self.url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/octet-stream",
                "Range": f"bytes={self.position}-{end}",
            },
        )
        with urlopen(request, timeout=60) as response:
            if response.status != 206:
                raise RuntimeError(
                    "Remote Parquet source did not honor byte-range access; "
                    "refusing to download a complete shard"
                )
            data = response.read()
        if len(data) != length:
            raise RuntimeError("Remote Parquet byte-range response had an unexpected length")
        self.position += length
        self.bytes_read += length
        if self.bytes_read > 1_000_000:
            raise RuntimeError("Parquet footer metadata exceeded the 1 MB safety ceiling")
        return data


def _parquet_manifest(expected_rows: int) -> tuple[list[dict], int]:
    """Inspect shard row counts through footer ranges and map global row indexes."""
    parquet_payload = _get_json(f"{PARQUET_API}?{urlencode({'dataset': DATASET_ID})}")
    size_payload = _get_json(f"{SIZE_API}?{urlencode({'dataset': DATASET_ID})}")
    if parquet_payload.get("partial") or size_payload.get("partial"):
        raise RuntimeError("Hugging Face returned partial Parquet or split metadata")
    files = parquet_payload.get("parquet_files") or []
    if not files:
        raise RuntimeError("Dataset Viewer did not list any Parquet shards")
    split_rows = int(
        size_payload.get("size", {}).get("splits", [{}])[0].get("num_rows") or 0
    )
    if split_rows != expected_rows:
        raise RuntimeError(
            f"Dataset split size changed: expected {expected_rows:,}, received {split_rows:,}"
        )
    try:
        from pyarrow import parquet
    except ImportError as exc:
        raise RuntimeError(
            "Reading Parquet footer row counts requires pyarrow; install the historical extra"
        ) from exc

    manifest: list[dict] = []
    row_start = 0
    bytes_read = 0
    for item in sorted(files, key=lambda row: row.get("filename", "")):
        url = item.get("url", "")
        filename = item.get("filename", "")
        size = int(item.get("size") or 0)
        if not url.startswith("https://huggingface.co/datasets/") or not filename.endswith(".parquet"):
            raise RuntimeError("Unexpected Parquet file URL or filename")
        if size <= 8:
            raise RuntimeError(f"Invalid Parquet file size for {filename}")
        reader = _ParquetRangeReader(url, size)
        parquet_file = parquet.ParquetFile(reader)
        row_count = int(parquet_file.metadata.num_rows)
        if row_count <= 0:
            raise RuntimeError(f"Parquet shard {filename} has no rows")
        manifest.append(
            {
                "filename": filename,
                "file_bytes": size,
                "row_count": row_count,
                "row_start": row_start,
                "row_end_exclusive": row_start + row_count,
                "row_groups": int(parquet_file.metadata.num_row_groups),
                "footer_bytes_read": reader.bytes_read,
            }
        )
        row_start += row_count
        bytes_read += reader.bytes_read
    if row_start != split_rows:
        raise RuntimeError(
            f"Parquet footer rows total {row_start:,}, split reports {split_rows:,}"
        )
    return manifest, bytes_read


def _identity_for_index(index: int, shards: list[dict]) -> tuple[str, int]:
    for shard in shards:
        if shard["row_start"] <= index < shard["row_end_exclusive"]:
            return shard["filename"], index - shard["row_start"]
    raise ValueError(f"Source row index {index} is outside the pinned Parquet manifest")


def _choose_non_overlapping_offset(
    start: int, end: int, length: int, blocked_indices: set[int], seed: str
) -> int:
    """Choose a deterministic, uniform valid start for a row slice in one stratum."""
    max_start = end - length
    if length <= 0 or max_start < start:
        raise ValueError("A sampling stratum cannot fit the requested page")
    start_count = max_start - start + 1
    forbidden: list[tuple[int, int]] = []
    for index in sorted(index for index in blocked_indices if start <= index < end):
        low = max(start, index - length + 1)
        high = min(max_start, index)
        if low <= high:
            forbidden.append((low, high))
    merged: list[list[int]] = []
    for low, high in forbidden:
        if merged and low <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], high)
        else:
            merged.append([low, high])
    forbidden_count = sum(high - low + 1 for low, high in merged)
    allowed_count = start_count - forbidden_count
    if allowed_count <= 0:
        raise ValueError("No non-overlapping row slice fits this sampling stratum")
    selected = random.Random(seed).randrange(allowed_count)
    cursor = start
    for low, high in merged:
        available = low - cursor
        if selected < available:
            return cursor + selected
        selected -= available
        cursor = high + 1
    return cursor + selected


def _stratum_for_index(index: int, total_rows: int, strata: int) -> int:
    return min(strata - 1, index * strata // total_rows)


def _read_sample_checkpoint(sample_path: Path, metadata_path: Path, identity: dict) -> tuple[list[dict], dict]:
    if not sample_path.exists() and not metadata_path.exists():
        sample_path.parent.mkdir(parents=True, exist_ok=True)
        sample_path.write_bytes(b"")
        state = {
            **identity,
            "completed_strata": {},
            "checkpoint_rows": 0,
            "committed_bytes": 0,
            "checkpoint_sha256": hashlib.sha256(b"").hexdigest(),
        }
        temporary = metadata_path.with_suffix(metadata_path.suffix + ".tmp")
        temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
        temporary.replace(metadata_path)
        return [], state
    if not sample_path.is_file() or not metadata_path.is_file():
        raise RuntimeError("Sampling checkpoint is incomplete; refusing to discard partial progress")
    state = json.loads(metadata_path.read_text(encoding="utf-8"))
    if any(state.get(key) != value for key, value in identity.items()):
        raise RuntimeError("Sampling checkpoint belongs to a different dataset revision or sample size")
    committed_bytes = int(state.get("committed_bytes", -1))
    actual_bytes = sample_path.stat().st_size
    if committed_bytes < 0 or actual_bytes < committed_bytes:
        raise RuntimeError("Sampling checkpoint file is shorter than its committed metadata")
    with sample_path.open("r+b") as handle:
        content = handle.read(committed_bytes)
        if actual_bytes > committed_bytes:
            handle.truncate(committed_bytes)
    if hashlib.sha256(content).hexdigest() != state.get("checkpoint_sha256"):
        raise RuntimeError("Sampling checkpoint SHA-256 mismatch")
    rows = [json.loads(line) for line in content.decode("utf-8").splitlines() if line.strip()]
    if len(rows) != int(state.get("checkpoint_rows", -1)):
        raise RuntimeError("Sampling checkpoint row count differs from its metadata")
    return rows, state


def _commit_sample_checkpoint(
    sample_path: Path,
    metadata_path: Path,
    identity: dict,
    rows: list[dict],
    state: dict,
    stratum: int,
    block: dict,
) -> dict:
    appended = [row for row in rows if _stratum_for_index(int(row["source_row_index"]), EXPECTED_SPLIT_ROWS, SAMPLE_STRATA) == stratum]
    with sample_path.open("ab") as handle:
        for row in appended:
            handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n")
        handle.flush()
        os.fsync(handle.fileno())
    all_rows = state.get("checkpoint_rows", 0) + len(appended)
    state = {
        **state,
        **identity,
        "checkpoint_rows": all_rows,
        "committed_bytes": sample_path.stat().st_size,
        "checkpoint_sha256": hashlib.sha256(sample_path.read_bytes()).hexdigest(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    completed = dict(state.get("completed_strata") or {})
    completed[stratum] = {
        "new_offset": block.get("new_offset"),
        "new_rows": block["new_rows"],
        "new_row_indexes": [int(row["source_row_index"]) for row in appended],
    }
    state["completed_strata"] = completed
    temporary = metadata_path.with_suffix(metadata_path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(metadata_path)
    return state


def extend_sample(
    total_sample_rows: int,
    existing_sample: Path,
    existing_metadata: Path,
    output: Path,
) -> dict:
    """Reuse E2 rows and sample new rows until a bounded total is reached."""
    if not 1_000 <= total_sample_rows <= MAX_TOTAL_SAMPLE_ROWS:
        raise ValueError(f"total_sample_rows must be between 1,000 and {MAX_TOTAL_SAMPLE_ROWS}")
    if total_sample_rows % SAMPLE_STRATA:
        raise ValueError(f"total_sample_rows must be divisible by {SAMPLE_STRATA}")
    before = _revision_metadata()
    previous_metadata = json.loads(existing_metadata.read_text(encoding="utf-8"))
    if previous_metadata.get("dataset_id") != DATASET_ID or previous_metadata.get("revision") != before.get("revision"):
        raise RuntimeError("Existing E2 sample revision differs from current dataset revision")
    prior_sample_digest = hashlib.sha256(existing_sample.read_bytes()).hexdigest()
    if previous_metadata.get("sample_sha256") and previous_metadata["sample_sha256"] != prior_sample_digest:
        raise RuntimeError("Existing E2 sample digest differs from its metadata")
    prior_rows: list[dict] = []
    with existing_sample.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if line.strip():
                prior = json.loads(line)
                if not isinstance(prior, dict) or not isinstance(prior.get("source_row_index"), int):
                    raise ValueError(f"Invalid existing sample row at line {line_number}")
                prior_rows.append(prior)
    expected_prior = int(previous_metadata.get("sample_rows") or 0)
    if len(prior_rows) != expected_prior or len(prior_rows) != len(
        {row["source_row_index"] for row in prior_rows}
    ):
        raise ValueError("Existing E2 sample row count or source identities are inconsistent")
    if len(prior_rows) > total_sample_rows:
        raise ValueError("Existing sample already exceeds requested total sample size")

    shards, footer_bytes = _parquet_manifest(EXPECTED_SPLIT_ROWS)
    target_per_stratum = total_sample_rows // SAMPLE_STRATA
    existing_by_stratum: dict[int, list[int]] = {i: [] for i in range(SAMPLE_STRATA)}
    for row in prior_rows:
        index = int(row["source_row_index"])
        if not 0 <= index < EXPECTED_SPLIT_ROWS:
            raise ValueError(f"Existing row index {index} falls outside the current split")
        existing_by_stratum[_stratum_for_index(index, EXPECTED_SPLIT_ROWS, SAMPLE_STRATA)].append(index)
    for stratum, indexes in existing_by_stratum.items():
        if len(indexes) > target_per_stratum:
            raise ValueError(
                f"E2 already has {len(indexes)} rows in stratum {stratum}; "
                f"target is {target_per_stratum}"
            )

    combined = []
    for row in prior_rows:
        row = dict(row)
        shard_name, local_index = _identity_for_index(int(row["source_row_index"]), shards)
        row["source_shard"] = shard_name
        row["source_row_in_shard"] = local_index
        combined.append(row)

    output.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_sample = output.with_suffix(".checkpoint.jsonl")
    checkpoint_metadata = output.with_suffix(".checkpoint.metadata.json")
    checkpoint_identity = {
        "dataset_id": DATASET_ID,
        "revision": before["revision"],
        "total_sample_rows": total_sample_rows,
        "expected_split_rows": EXPECTED_SPLIT_ROWS,
        "previous_sample_sha256": prior_sample_digest,
    }
    checkpoint_rows, checkpoint_state = _read_sample_checkpoint(
        checkpoint_sample, checkpoint_metadata, checkpoint_identity
    )
    completed_strata = {
        int(stratum): value
        for stratum, value in (checkpoint_state.get("completed_strata") or {}).items()
    }
    checkpoint_by_stratum: dict[int, list[dict]] = {i: [] for i in range(SAMPLE_STRATA)}
    checkpoint_indexes: set[int] = set()
    prior_indexes = {int(row["source_row_index"]) for row in prior_rows}
    for row in checkpoint_rows:
        index = int(row["source_row_index"])
        stratum = _stratum_for_index(index, EXPECTED_SPLIT_ROWS, SAMPLE_STRATA)
        if index in checkpoint_indexes or index in prior_indexes:
            raise RuntimeError("Sampling checkpoint contains duplicate or reused source indexes")
        checkpoint_indexes.add(index)
        checkpoint_by_stratum[stratum].append(row)
    if not set(completed_strata).issubset(set(range(SAMPLE_STRATA))):
        raise RuntimeError("Sampling checkpoint contains an invalid stratum id")

    blocks: list[dict] = []
    feature_schema: list[dict] | None = previous_metadata.get("schema") or None
    for stratum in range(SAMPLE_STRATA):
        stratum_start = math.floor(stratum * EXPECTED_SPLIT_ROWS / SAMPLE_STRATA)
        stratum_end = math.floor((stratum + 1) * EXPECTED_SPLIT_ROWS / SAMPLE_STRATA)
        old_indexes = set(existing_by_stratum[stratum])
        new_length = target_per_stratum - len(old_indexes)
        block: dict = {
            "stratum": stratum,
            "row_start": stratum_start,
            "row_end_exclusive": stratum_end,
            "reused_rows": len(old_indexes),
            "new_rows": new_length,
        }
        completed = completed_strata.get(stratum)
        if completed is not None:
            saved_rows = checkpoint_by_stratum[stratum]
            saved_indexes = sorted(int(row["source_row_index"]) for row in saved_rows)
            if int(completed.get("new_rows", -1)) != new_length or len(saved_rows) != new_length:
                raise RuntimeError(f"Checkpoint row count is inconsistent for stratum {stratum}")
            saved_offset = completed.get("new_offset")
            if new_length and saved_indexes != list(range(int(saved_offset), int(saved_offset) + new_length)):
                raise RuntimeError(f"Checkpoint indexes are inconsistent for stratum {stratum}")
            if not new_length and saved_offset is not None:
                raise RuntimeError(f"Checkpoint offset is inconsistent for stratum {stratum}")
            combined.extend(saved_rows)
            block.update(
                {
                    "new_offset": saved_offset,
                    "shard_names": sorted({str(row["source_shard"]) for row in saved_rows}),
                    "resumed_from_checkpoint": True,
                }
            )
        elif new_length:
            offset = _choose_non_overlapping_offset(
                stratum_start,
                stratum_end,
                new_length,
                old_indexes,
                f"{before.get('revision')}:{total_sample_rows}:{stratum}",
            )
            payload = _row_page(offset, new_length)
            page_total = int(payload.get("num_rows_total") or 0)
            if page_total != EXPECTED_SPLIT_ROWS or payload.get("partial"):
                raise RuntimeError("Dataset Viewer returned a changed or partial split")
            page_schema = payload.get("features") or []
            if feature_schema is None:
                feature_schema = page_schema
            elif feature_schema != page_schema:
                raise RuntimeError("Dataset schema changed during incremental sampling")
            schema_names = {feature.get("name") for feature in page_schema}
            if not set(SAMPLE_COLUMNS).issubset(schema_names):
                raise RuntimeError("Dataset Viewer schema is missing a required sample field")
            rows = payload.get("rows") or []
            if len(rows) != new_length:
                raise RuntimeError(
                    f"Expected {new_length} rows in stratum {stratum}, received {len(rows)}"
                )
            page_indexes = [int(item["row_idx"]) for item in rows]
            if page_indexes != list(range(offset, offset + new_length)):
                raise RuntimeError("Dataset Viewer returned non-contiguous or unexpected row indexes")
            if old_indexes.intersection(page_indexes):
                raise RuntimeError("Incremental sample overlaps an existing E2 source row")
            new_rows = []
            for item in rows:
                source_index = int(item["row_idx"])
                shard_name, local_index = _identity_for_index(source_index, shards)
                raw_values = item["row"]
                new_rows.append(
                    {
                        "source_row_index": source_index,
                        "source_shard": shard_name,
                        "source_row_in_shard": local_index,
                        "sampling_stratum": stratum,
                        **{key: raw_values.get(key) for key in SAMPLE_COLUMNS},
                    }
                )
            combined.extend(new_rows)
            block.update({"new_offset": offset, "shard_names": sorted({
                _identity_for_index(index, shards)[0] for index in page_indexes
            })})
            checkpoint_state = _commit_sample_checkpoint(
                checkpoint_sample,
                checkpoint_metadata,
                checkpoint_identity,
                new_rows,
                checkpoint_state,
                stratum,
                block,
            )
            completed_strata[stratum] = checkpoint_state["completed_strata"][stratum]
        else:
            block["new_offset"] = None
            block["shard_names"] = []
            checkpoint_state = _commit_sample_checkpoint(
                checkpoint_sample,
                checkpoint_metadata,
                checkpoint_identity,
                [],
                checkpoint_state,
                stratum,
                block,
            )
            completed_strata[stratum] = checkpoint_state["completed_strata"][stratum]
        blocks.append(block)
        if (stratum + 1) % 10 == 0:
            print(
                f"Sampling progress: {stratum + 1}/{SAMPLE_STRATA} strata checkpointed",
                file=sys.stderr,
                flush=True,
            )

    if len(completed_strata) != SAMPLE_STRATA:
        raise RuntimeError("Sampling checkpoint is incomplete after retrieval")
    after = _revision_metadata()
    if before.get("revision") != after.get("revision"):
        raise RuntimeError("Dataset revision changed during sample retrieval; refusing to save")
    combined.sort(key=lambda row: int(row["source_row_index"]))
    indexes = [int(row["source_row_index"]) for row in combined]
    if len(combined) != total_sample_rows or len(set(indexes)) != total_sample_rows:
        raise RuntimeError("Combined sample is not the requested size of unique source rows")
    stratum_counts = Counter(
        _stratum_for_index(index, EXPECTED_SPLIT_ROWS, SAMPLE_STRATA) for index in indexes
    )
    if any(stratum_counts[i] != target_per_stratum for i in range(SAMPLE_STRATA)):
        raise RuntimeError("Combined sample does not meet the per-stratum row target")

    output.parent.mkdir(parents=True, exist_ok=True)
    sample_path = output.with_suffix(".jsonl")
    metadata_path = output.with_suffix(".metadata.json")
    temporary_sample = sample_path.with_suffix(sample_path.suffix + ".tmp")
    with temporary_sample.open("w", encoding="utf-8", newline="\n") as handle:
        for row in combined:
            handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    temporary_sample.replace(sample_path)
    sample_digest = hashlib.sha256(sample_path.read_bytes()).hexdigest()
    batch_id = f"tinix-e3-{total_sample_rows}-{before['revision'][:12]}"
    province_counts: dict[str, int] = {}
    month_counts: dict[str, int] = {}
    shard_counts: dict[str, int] = {}
    for row in combined:
        province = str(row.get("province_name") or "<NULL>")
        month = str(row.get("published_at") or "<NULL>")[:7]
        shard = str(row.get("source_shard") or "<UNKNOWN>")
        province_counts[province] = province_counts.get(province, 0) + 1
        month_counts[month] = month_counts.get(month, 0) + 1
        shard_counts[shard] = shard_counts.get(shard, 0) + 1
    metadata = {
        **before,
        "dataset_url": DATASET_URL,
        "license_url": LICENSE_URL,
        "attribution": "TiniX AI, Tinix Vietnam Real Estate Listings 2025-2026",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "config": "default",
        "split": "train",
        "split_rows_reported": EXPECTED_SPLIT_ROWS,
        "sample_rows": len(combined),
        "sample_sha256": sample_digest,
        "batch_id": batch_id,
        "batch_new_rows": len(combined) - len(prior_rows),
        "reused_e2_rows": len(prior_rows),
        "previous_batch": {
            "batch_id": f"tinix-e2-{len(prior_rows)}-{before['revision'][:12]}",
            "sample_rows": len(prior_rows),
            "sample_sha256": prior_sample_digest,
            "sample_method": previous_metadata.get("sample_method"),
            "retrieved_at": previous_metadata.get("retrieved_at"),
            "sample_offsets": previous_metadata.get("sample_offsets"),
        },
        "sample_method": (
            "deterministic stratified cluster sample: exactly 100 rows per each of 100 equal "
            "global row-index strata; retains all distinct E2 rows and fills each stratum with "
            "a revision-seeded non-overlapping /rows slice; not a probability-representative sample"
        ),
        "sampling_is_statistically_representative": False,
        "sampling_strata": blocks,
        "sample_offsets": [block["new_offset"] for block in blocks if block["new_offset"] is not None],
        "page_size": PAGE_SIZE,
        "sample_columns": list(SAMPLE_COLUMNS),
        "schema": feature_schema or previous_metadata.get("schema", []),
        "source_row_identity": (
            "dataset revision + Dataset Viewer global row_idx; source_shard and "
            "source_row_in_shard derived from cumulative row counts in the ordered Parquet manifest"
        ),
        "parquet_manifest": shards,
        "parquet_footer_bytes_fetched": footer_bytes,
        "sample_distribution": {
            "province_counts": dict(sorted(province_counts.items())),
            "published_month_counts": dict(sorted(month_counts.items())),
            "parquet_shard_counts": dict(sorted(shard_counts.items())),
        },
        "listing_detail_url_field_present": False,
        "listing_id_field_present": False,
        "transaction_type_field_present": False,
        "commercial_use": False,
        "full_dataset_downloaded": False,
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "sample_file": str(sample_path),
        "metadata_file": str(metadata_path),
        "sample_rows": len(combined),
        "new_rows": metadata["batch_new_rows"],
        "reused_e2_rows": len(prior_rows),
        "revision": before.get("revision"),
        "batch_id": batch_id,
        "split_rows": EXPECTED_SPLIT_ROWS,
        "shards": len(shards),
        "parquet_footer_bytes_fetched": footer_bytes,
        "full_dataset_downloaded": False,
        "sample_sha256": sample_digest,
    }


def download_sample(sample_rows: int, output: Path) -> dict:
    if not 1 <= sample_rows <= MAX_SAMPLE_ROWS:
        raise ValueError(f"sample_rows must be between 1 and {MAX_SAMPLE_ROWS}")

    before = _revision_metadata()
    page_count = math.ceil(sample_rows / PAGE_SIZE)
    sample: list[dict] = []
    offsets: list[int] = []
    feature_schema: list[dict] | None = None
    total_rows: int | None = None

    for page_index in range(page_count):
        length = min(PAGE_SIZE, sample_rows - len(sample))
        stratum_start = math.floor(page_index * EXPECTED_SPLIT_ROWS / page_count)
        stratum_end = math.floor((page_index + 1) * EXPECTED_SPLIT_ROWS / page_count)
        max_start = max(stratum_start, stratum_end - length)
        offset_rng = random.Random(f"{before.get('revision')}:{sample_rows}:{page_index}")
        offset = offset_rng.randint(stratum_start, max_start)
        payload = _row_page(offset, length)
        # The official dataset-viewer /rows endpoint does not echo dataset/config/split
        # in its response. The request URL is pinned above; validate the returned
        # schema and cardinality instead of requiring absent response properties.
        if payload.get("dataset") not in (None, DATASET_ID) or payload.get("split") not in (None, "train"):
            raise RuntimeError("Hugging Face returned rows for an unexpected dataset/split")
        if payload.get("partial"):
            raise RuntimeError("Hugging Face marked the dataset sample partial; refusing pilot import")
        page_total = int(payload.get("num_rows_total") or 0)
        if page_total <= 0:
            raise RuntimeError("Hugging Face did not report a valid split size")
        if total_rows is None:
            total_rows = page_total
        elif page_total != total_rows:
            raise RuntimeError("Dataset row count changed during sample retrieval")
        page_schema = payload.get("features") or []
        schema_names = {feature.get("name") for feature in page_schema}
        missing_columns = set(SAMPLE_COLUMNS) - schema_names
        if missing_columns:
            raise RuntimeError(
                "Dataset schema is missing required sample fields: "
                + ", ".join(sorted(missing_columns))
            )
        if feature_schema is None:
            feature_schema = page_schema
        elif page_schema != feature_schema:
            raise RuntimeError("Dataset schema changed during sample retrieval")
        rows = payload.get("rows") or []
        if len(rows) != length:
            raise RuntimeError(
                f"Expected {length} rows at offset {offset}, received {len(rows)}"
            )
        for row in rows:
            index = int(row["row_idx"])
            raw_values = row["row"]
            sample_row = {key: raw_values.get(key) for key in SAMPLE_COLUMNS}
            sample.append({"source_row_index": index, **sample_row})
        offsets.append(offset)

    if total_rows != EXPECTED_SPLIT_ROWS:
        raise RuntimeError(
            f"Dataset size changed: expected {EXPECTED_SPLIT_ROWS:,} rows, received {total_rows}"
        )
    after = _revision_metadata()
    if before.get("revision") != after.get("revision"):
        raise RuntimeError("Dataset revision changed during retrieval; sample was not saved")

    output.parent.mkdir(parents=True, exist_ok=True)
    sample_path = output.with_suffix(".jsonl")
    metadata_path = output.with_suffix(".metadata.json")
    with sample_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in sample:
            handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")

    metadata = {
        **before,
        "dataset_url": DATASET_URL,
        "license_url": LICENSE_URL,
        "attribution": "TiniX AI, Tinix Vietnam Real Estate Listings 2025-2026",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "config": "default",
        "split": "train",
        "split_rows_reported": total_rows,
        "sample_rows": len(sample),
        "sample_method": (
            "deterministic stratified row-index sample: evenly spaced index segments, "
            "with reproducible offsets using Hugging Face dataset-viewer /rows endpoint"
        ),
        "sample_offsets": offsets,
        "page_size": PAGE_SIZE,
        "schema": feature_schema,
        "sample_columns": list(SAMPLE_COLUMNS),
        "listing_detail_url_field_present": any(
            feature.get("name") in {"url", "source_url", "listing_url"}
            for feature in (feature_schema or [])
        ),
        "listing_id_field_present": any(
            feature.get("name") in {"id", "listing_id", "source_id"}
            for feature in (feature_schema or [])
        ),
        "transaction_type_field_present": any(
            feature.get("name") in {"transaction_type", "listing_type", "deal_type", "intent"}
            for feature in (feature_schema or [])
        ),
        "commercial_use": False,
        "full_dataset_downloaded": False,
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "sample_file": str(sample_path),
        "metadata_file": str(metadata_path),
        "sample_rows": len(sample),
        "split_rows": total_rows,
        "revision": before.get("revision"),
        "fields": [feature.get("name") for feature in (feature_schema or [])],
        "full_dataset_downloaded": False,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-rows", type=int, default=1_000)
    parser.add_argument("--extend-existing", action="store_true")
    parser.add_argument("--total-sample-rows", type=int)
    parser.add_argument(
        "--existing-sample",
        type=Path,
        default=Path("data/historical_pilot/tinix_sample.jsonl"),
    )
    parser.add_argument(
        "--existing-metadata",
        type=Path,
        default=Path("data/historical_pilot/tinix_sample.metadata.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output stem; .jsonl and .metadata.json are appended",
    )
    args = parser.parse_args()
    try:
        if args.extend_existing:
            if args.total_sample_rows is None:
                parser.error("--extend-existing requires --total-sample-rows")
            output = args.output or Path(
                f"data/historical_pilot/tinix_sample_{args.total_sample_rows}"
            )
            result = extend_sample(
                args.total_sample_rows,
                args.existing_sample,
                args.existing_metadata,
                output,
            )
        else:
            if args.output is None:
                args.output = Path("data/historical_pilot/tinix_sample")
            result = download_sample(args.sample_rows, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc


if __name__ == "__main__":
    main()
