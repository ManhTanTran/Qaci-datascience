import csv
import io
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

from wardprice.database import active_wards, connect, import_legacy_targets, import_wards
from wardprice.gemini import make_listing_prompt
from wardprice.registry import Ward
from wardprice.target_registry import (
    REQUIRED_COLUMNS,
    TOP50_CSV_MEMBER,
    LegacyWardTarget,
    load_legacy_targets,
    target_summary,
)


def sample_rows():
    xã_ranks = {3, 4, 5, 17, 41}
    rows = []
    for rank in range(1, 51):
        mapped = rank <= 5
        category = "XÃ" if rank in xã_ranks else "PHƯỜNG"
        rows.append(
            {
                "rank": str(rank),
                "old_province": f"Province {rank}",
                "old_district": f"District {rank}",
                "old_ward": f"Ward {rank}",
                "category": category,
                "n_customers": "987654321" if rank == 1 else str(200 + rank),
                "pct": "0.987654321" if rank == 1 else "0.25",
                "batch": str((rank - 1) // 5 + 1),
                "current_province": f"New Province {rank}" if mapped else "",
                "current_ward": f"New Ward {rank}" if mapped else "",
                "current_ward_code": "" if rank == 1 else (f"CODE-{rank}" if mapped else ""),
                "status": "REVIEWED_RESOLUTION" if mapped else "PENDING_ADMIN_MAPPING",
                "mapping_note": "Reviewed sample mapping" if mapped else "Mapping pending",
                "source_url": "https://example.gov.vn/resolution" if mapped else "",
            }
        )
    return rows


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=sorted(REQUIRED_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)


class TestTop50TargetRegistry(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.path = Path(self.root.name)

    def test_reads_top50_zip_and_maps_blank_admin_code_to_null(self):
        archive_path = self.path / "top50.zip"
        payload = io.StringIO(newline="")
        rows = sample_rows()
        writer = csv.DictWriter(payload, fieldnames=sorted(REQUIRED_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)
        with ZipFile(archive_path, "w") as archive:
            archive.writestr(TOP50_CSV_MEMBER, payload.getvalue())

        targets = load_legacy_targets(archive_path)

        self.assertEqual(len(targets), 50)
        self.assertEqual([target.rank for target in targets], list(range(1, 51)))
        self.assertIsNone(targets[0].current_ward_code)
        self.assertEqual(targets[1].current_ward_code, "CODE-2")

    def test_import_is_idempotent_and_preserves_existing_database_rows(self):
        db = connect(self.path / "state.sqlite3")
        self.addCleanup(db.close)
        db.execute(
            "INSERT INTO run_log(run_id,started_at,details) VALUES(?,?,?)",
            ("existing-run", "2026-10-12T00:00:00+00:00", "preserve"),
        )
        original_ward = Ward("ACTIVE-1", "Active Ward", "Province", "", "District")
        import_wards(db, [original_ward])
        targets = [
            LegacyWardTarget(
                rank=int(item["rank"]),
                old_province=item["old_province"],
                old_district=item["old_district"],
                old_ward=item["old_ward"],
                category=item["category"],
                n_customers=int(item["n_customers"]),
                pct=float(item["pct"]),
                batch=int(item["batch"]),
                current_province=item["current_province"],
                current_ward=item["current_ward"],
                current_ward_code=item["current_ward_code"] or None,
                status=item["status"],
                mapping_note=item["mapping_note"],
                source_url=item["source_url"],
            )
            for item in sample_rows()
        ]

        import_legacy_targets(db, targets)
        import_legacy_targets(db, targets)

        self.assertEqual(db.execute("SELECT COUNT(*) FROM ward_target_legacy").fetchone()[0], 50)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM listings").fetchone()[0], 0)
        self.assertEqual(
            db.execute("SELECT COUNT(*) FROM run_log WHERE run_id='existing-run'").fetchone()[0], 1
        )
        self.assertEqual([ward.code for ward in active_wards(db)], ["ACTIVE-1"])

    def test_category_and_mapping_counts_match_source_shape(self):
        source = self.path / "targets.csv"
        write_csv(source, sample_rows())
        targets = load_legacy_targets(source)
        summary = target_summary(targets)

        self.assertEqual(Counter(target.category for target in targets), {"PHƯỜNG": 45, "XÃ": 5})
        self.assertEqual(
            summary["mapping_status_counts"],
            {"REVIEWED_RESOLUTION": 5, "PENDING_ADMIN_MAPPING": 45},
        )
        self.assertEqual(summary["target_count"], 50)

    def test_duplicate_original_location_is_rejected(self):
        rows = sample_rows()
        rows[1]["old_province"] = rows[0]["old_province"]
        rows[1]["old_district"] = rows[0]["old_district"]
        rows[1]["old_ward"] = rows[0]["old_ward"]
        source = self.path / "duplicate.csv"
        write_csv(source, rows)

        with self.assertRaisesRegex(ValueError, "duplicate original target location"):
            load_legacy_targets(source)

    def test_incomplete_or_duplicate_ranks_are_rejected(self):
        missing_rank = self.path / "missing.csv"
        write_csv(missing_rank, sample_rows()[:-1])
        with self.assertRaisesRegex(ValueError, "each rank from 1 through 50"):
            load_legacy_targets(missing_rank)

        duplicate_rank_rows = sample_rows()
        duplicate_rank_rows[1]["rank"] = "1"
        duplicate_rank = self.path / "duplicate-rank.csv"
        write_csv(duplicate_rank, duplicate_rank_rows)
        with self.assertRaisesRegex(ValueError, "duplicate target rank"):
            load_legacy_targets(duplicate_rank)

        wrong_batch_rows = sample_rows()
        wrong_batch_rows[0]["batch"] = "2"
        wrong_batch = self.path / "wrong-batch.csv"
        write_csv(wrong_batch, wrong_batch_rows)
        with self.assertRaisesRegex(ValueError, "batch does not match"):
            load_legacy_targets(wrong_batch)

    def test_customer_metrics_do_not_enter_gemini_prompt(self):
        source = self.path / "targets.csv"
        write_csv(source, sample_rows())
        target = load_legacy_targets(source)[0]
        ward = Ward("TOP50-001", target.old_ward, target.old_province, "", target.old_district)

        prompt = make_listing_prompt(ward, [], max_new_listings=5)

        self.assertNotIn("n_customers", prompt)
        self.assertNotIn("pct", prompt)
        self.assertNotIn("987654321", prompt)
        self.assertNotIn("0.987654321", prompt)


if __name__ == "__main__":
    unittest.main()
