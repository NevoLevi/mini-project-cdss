import unittest
import tempfile, shutil
from pathlib import Path
from datetime import datetime, time, date
from unittest.mock import patch

import pandas as pd

import cdss_loinc
from cdss_loinc import CDSSDatabase


class TestHistory(unittest.TestCase):
    """Unit‑tests for CDSSDatabase.history."""

    # ───────────────────────── helpers ──────────────────────────
    @staticmethod
    def _build_excel(path: Path):
        """Create a tiny Excel DB with three patients & multiple timestamps."""
        rows = [
            # John Doe — two measurements, different hours
            ("John", "Doe", "1234-5", 7.5, "g/dL", "2025-04-20 10:00", "2025-04-21 10:00"),
            ("John", "Doe", "1234-5", 7.6, "g/dL", "2025-04-20 12:00", "2025-04-21 12:00"),
            ("John", "Doe", "1234-5", 7.7, "g/dL", "2025-04-20 12:00", "2025-04-21 12:00"),
            # John Doe2 — two measurements, different hours
            ("John", "Doe2", "1234-5", 7.5, "g/dL", "2025-04-20 10:00", "2025-04-21 10:00"),
            ("John", "Doe2", "1234-5", 7.6, "g/dL", "2025-04-20 11:00", "2025-04-21 12:00"),
            ("John", "Doe2", "1234-5", 7.7, "g/dL", "2025-04-20 12:00", "2025-04-21 12:00"),
            # Alice Roe — a different code
            ("Alice", "Roe", "67890-1", 42, "U/L", "2025-01-15 08:00", "2025-01-15 09:00"),
            # Bob Foo  — another code
            ("Bob", "Foo", "55555-5", 100, "%", "2025-04-18 06:30", "2025-04-18 07:00"),
        ]
        df = pd.DataFrame(rows, columns=[
            "First name", "Last name", "LOINC-NUM", "Value", "Unit",
            "Valid start time", "Transaction time"
        ])
        df.to_excel(path, index=False)

    # ───────────────────────── lifecycle ─────────────────────────
    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        self._excel  = self._tmpdir / "db.xlsx"
        self._build_excel(self._excel)

        # patch global lookups so no LOINC zip is needed
        dummy_loinc = {
            "1234-5": "Sample test",
            "67890-1": "ALT",
            "55555-5": "O2 Sat"
        }
        comp_map = {"sample": "1234-5", "alt": "67890-1", "o2": "55555-5"}

        self._p_loinc2name = patch.object(cdss_loinc, "LOINC2NAME", new=pd.Series(dummy_loinc))
        self._p_comp2code  = patch.object(cdss_loinc, "COMP2CODE",  new=comp_map)
        self._p_min        = patch.object(cdss_loinc, "MIN_PATIENTS", new=1)

        for p in (self._p_loinc2name, self._p_comp2code, self._p_min):
            p.start()

        self.db = CDSSDatabase(excel=self._excel)

    def tearDown(self):
        for p in (self._p_loinc2name, self._p_comp2code, self._p_min):
            p.stop()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    # ───────────────────────── HISTORY ───────────────────────
    def test_history_loinc_code(self):
        """Exact code returns both rows within date‑range."""
        res = self.db.history(
            "John Doe", "1234-5",
            datetime(2025, 4, 19), datetime(2025, 4, 21, 23, 59)
        )
        self.assertEqual(len(res), 2)

    def test_history_component_alias(self):
        """Component alias resolves to code (case‑insensitive patient)."""
        res = self.db.history(
            "john doe", "sample",
            datetime(2025, 4, 20), datetime(2025, 4, 20, 23, 59)
        )
        # should return the two rows at 10:00 and 12:00
        times = sorted(res["Valid start time"].dt.time)
        self.assertEqual(times, [time(10, 0), time(12, 0)])

    def test_history_wrong_patient(self):
        """Unknown patient → empty DataFrame (no exception)."""
        res = self.db.history(
            "Jane Smith", "1234-5",
            datetime(2025, 4, 20), datetime(2025, 4, 20, 23, 59)
        )
        self.assertTrue(res.empty)

    def test_history_wrong_code(self):
        """Invalid LOINC code should raise ValueError via _normalise_code."""
        with self.assertRaises(ValueError):
            self.db.history(
                "John Doe", "9999-9",     # not in dummy_loinc
                datetime(2025, 4, 20), datetime(2025, 4, 20, 23, 59)
            )

    def test_range_no_samples(self):
        """Hour-range with no matching measurements → empty result."""
        res = self.db.history(
            "John Doe", "1234-5",
            datetime(2025, 4, 20, 13, 0),  # 13:00
            datetime(2025, 4, 20, 15, 0)  # 15:00
        )
        self.assertTrue(res.empty)

    def test_range_two_sample(self):
        """Hour-range that captures exactly one measurement."""
        res = self.db.history(
            "John Doe", "1234-5",
            datetime(2025, 4, 20, 11, 0),  # 11:00
            datetime(2025, 4, 20, 12, 30)  # 12:30  → only 12:00 hit
        )
        self.assertEqual(len(res), 1)
        self.assertEqual(res.iloc[0]["Value"], 7.7)

    def test_range_multiple_samples(self):
        """Hour-range that captures both of John's measurements."""
        res = self.db.history(
            "John Doe", "1234-5",
            datetime(2025, 4, 20, 9, 0),  # 09:00
            datetime(2025, 4, 20, 12, 30)  # 12:30
        )
        self.assertEqual(len(res), 2)

    def test_illegal_time_range(self):
        """start > end should yield empty DataFrame (backend is tolerant)."""
        res = self.db.history(
            "John Doe", "1234-5",
            datetime(2025, 4, 20, 14, 0),  # 14:00
            datetime(2025, 4, 20, 10, 0)  # 10:00 (earlier)
        )
        self.assertTrue(res.empty)


    # ───────────────────────── UPDATE ───────────────────────
    def test_update_valid_changes_value(self):
        """A valid update appends a new row with the new value."""
        ts_valid = datetime(2025, 4, 20, 10, 0)
        res = self.db.update(
            patient="John Doe",
            code_or_cmp="1234-5",
            valid_dt=ts_valid,
            new_val=8.0,
            now=datetime(2025, 4, 22, 13, 0)
        )
        # update() returns the newly-appended row
        self.assertEqual(res.iloc[0]["Value"], 8.0)

    def test_update_wrong_time_raises(self):
        """Update on a non-existent (date,hour) raises ValueError."""
        with self.assertRaises(ValueError):
            self.db.update(
                "John Doe", "1234-5",
                datetime(2025, 4, 20, 17, 0),  # 17:00 not in DB
                new_val=9.0
            )

    def test_update_duplicate_latest_row(self):
        """
        When two rows share the same Valid-time, update should clone the one
        with the latest Transaction-time.
        """
        # Our fixture already has two rows at 10:00; verify which is 'latest'
        ts_valid = datetime(2025, 4, 20, 12, 0)
        before = (
            self.db.df[self.db.df["Valid start time"] == ts_valid]
            .sort_values("Transaction time")
        )
        idx_latest_before = before.index[-1]
        latest_value_before = before.loc[idx_latest_before, "Value"]

        # perform update
        res = self.db.update(
            "John Doe", "1234-5",
            ts_valid,
            new_val=latest_value_before + 1,  # e.g., bump by 1
            now=datetime(2025, 4, 22, 14, 0)
        )

        # returned row should be based on the previously-latest one
        self.assertEqual(
            res.iloc[0]["Transaction time"].tz_localize(None).time(),
            time(14, 0)
        )
        self.assertEqual(res.iloc[0]["Value"], latest_value_before + 1)

    def test_update_reflected_in_history(self):
        """After a successful update, history() should show the new value last."""
        ts_valid = datetime(2025, 4, 20, 12, 0)
        self.db.update(
            "John Doe", "1234-5",
            ts_valid, 9.9,
            now=datetime(2025, 4, 22, 15, 0)
        )
        hist = self.db.history(
            "John Doe", "1234-5",
            datetime(2025, 4, 20, 0, 0), datetime(2025, 4, 20, 23, 59)
        )
        # last row should be the one with Value == 9.9
        self.assertEqual(hist.iloc[-1]["Value"], 9.9)


    # ───────────────────── tests for DELETE ──────────────────────
    def test_delete_valid(self):
        """Exact (date,hour) delete removes that row."""
        day = datetime(2025, 4, 20).date()
        hh10 = time(10, 0)

        # ensure 10:00 exists first
        self.assertFalse(self.db.history("John Doe", "1234-5",
                                         datetime(2025, 4, 20, 10, 0),
                                         datetime(2025, 4, 20, 10, 0)).empty)

        self.db.delete("John Doe", "1234-5", day, hh10)

        # now it should be gone
        after = self.db.history("John Doe", "1234-5",
                                datetime(2025, 4, 20, 10, 0),
                                datetime(2025, 4, 20, 10, 0))
        self.assertTrue(after.empty)

    def test_delete_wrong_date_raises(self):
        """No measurement on that date => ValueError."""
        with self.assertRaises(ValueError):
            self.db.delete(
                "John Doe", "1234-5",
                date(2025, 4, 19)  # John has no rows on the 19th
            )

    def test_delete_wrong_patient_raises(self):
        """Unknown patient => ValueError."""
        with self.assertRaises(ValueError):
            self.db.delete(
                "Jane Smith", "1234-5",
                date(2025, 4, 20)
            )

    def test_update_then_delete(self):
        """After one update+delete cycle John Doe should still have 2 rows."""
        day_rows = lambda: self.db.history(
            "John Doe2", "1234-5",
            datetime(2025, 4, 20), datetime(2025, 4, 20, 23, 59)
        )

        initial_len = len(day_rows())  # should be 2 (10:00, 11:00 and 12:00)
        self.assertEqual(initial_len, 3)

        ts = datetime(2025, 4, 20, 12, 0)  # operate on 12:00 row
        self.db.update("John Doe2", "1234-5", ts, 9.9,
                       now=datetime(2025, 4, 22, 12, 0))
        self.db.delete("John Doe2", "1234-5", ts.date(), ts.time())

        self.assertEqual(len(day_rows()), 2)  # row-count unchanged

    def test_update_delete_twice(self):
        """
        Two successive update+delete cycles should ultimately leave
        exactly 1 row (only the 10:00 measurement survives).
        """
        day_rows = lambda: self.db.history(
            "John Doe2", "1234-5",
            datetime(2025, 4, 20), datetime(2025, 4, 20, 23, 59)
        )

        ts = datetime(2025, 4, 20, 12, 0)

        # cycle 1
        self.db.update("John Doe2", "1234-5", ts, 8.8,
                       now=datetime(2025, 4, 22, 13, 0))
        self.db.delete("John Doe2", "1234-5", ts.date(), ts.time())

        ts = datetime(2025, 4, 20, 11, 0)

        # cycle 2
        self.db.update("John Doe2", "1234-5", ts, 8.9,
                       now=datetime(2025, 4, 22, 14, 0))
        self.db.delete("John Doe2", "1234-5", ts.date(), ts.time())

        self.assertEqual(len(day_rows()), 1)  # only the 10:00 measurement left

    def test_delete_11_keeps_12(self):
        """
        Delete the 11:00 measurement; ensure 12:00 still present and row-count drops by 1.
        """
        ts11 = datetime(2025, 4, 20, 11, 0)
        ts12 = datetime(2025, 4, 20, 12, 0)

        # initial counts
        day_rows = lambda: self.db.history(
            "John Doe2", "1234-5",
            datetime(2025, 4, 20), datetime(2025, 4, 20, 23, 59)
        )
        self.assertEqual(len(day_rows()), 3)

        # delete 11:00
        self.db.delete("John Doe2", "1234-5", ts11.date(), ts11.time())

        remaining = day_rows()
        self.assertEqual(len(remaining), 2)  # row-count dropped by 1

        # 12:00 row still there
        times_left = set(remaining["Valid start time"].dt.time)
        self.assertIn(time(12, 0), times_left)


if __name__ == "__main__":
    unittest.main()
