import unittest
import tempfile, shutil
from pathlib import Path
from datetime import datetime, time
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

    def test_history_hour_single_filter(self):
        """Hour filter isolates a single measurement."""
        hit = self.db.history(
            "John Doe", "1234-5",
            datetime(2025, 4, 20), datetime(2025, 4, 20, 23, 59),
            hh=time(12, 0)
        )
        self.assertEqual(len(hit), 1)
        self.assertEqual(hit.iloc[0]["Value"], 7.6)

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

    def test_range_single_sample(self):
        """Hour-range that captures exactly one measurement."""
        res = self.db.history(
            "John Doe", "1234-5",
            datetime(2025, 4, 20, 11, 0),  # 11:00
            datetime(2025, 4, 20, 12, 30)  # 12:30  → only 12:00 hit
        )
        self.assertEqual(len(res), 1)
        self.assertEqual(res.iloc[0]["Value"], 7.6)

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


if __name__ == "__main__":
    unittest.main()
