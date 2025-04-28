import unittest
import tempfile, shutil
from pathlib import Path
from datetime import datetime, time
from unittest.mock import patch

import pandas as pd

import cdss_loinc
from cdss_loinc import CDSSDatabase


class TestHistory(unittest.TestCase):
    """Unit‑tests for CDSSDatabase.history using the built‑in unittest runner."""

    # ───────────────────────── helpers ──────────────────────────
    @staticmethod
    def _build_excel(path: Path):
        """Write a one‑row Excel file that CDSSDatabase can load."""
        df = pd.DataFrame({
            "First name": ["John"],
            "Last name" : ["Doe"],
            "LOINC-NUM" : ["1234-5"],
            "Value"     : [7.5],
            "Unit"      : ["g/dL"],
            "Valid start time": [pd.Timestamp("2025-04-20 10:00")],
            "Transaction time": [pd.Timestamp("2025-04-21 10:00")],
        })
        df.to_excel(path, index=False)

    # ───────────────────────── lifecycle ─────────────────────────
    def setUp(self):
        # 1. temp directory + excel
        self._tmpdir = Path(tempfile.mkdtemp())
        self._excel  = self._tmpdir / "db.xlsx"
        self._build_excel(self._excel)

        # 2. patch global lookup tables so no LOINC zip is needed
        self._p_loinc2name = patch.object(cdss_loinc, "LOINC2NAME",
                                          new=pd.Series({"1234-5": "Sample test"}))
        self._p_comp2code = patch.object(cdss_loinc, "COMP2CODE",
                                          new={"sample": "1234-5"})

        self._p_min_patients = patch.object(cdss_loinc, "MIN_PATIENTS", new=1)
        self._p_min_patients.start()

        self._p_loinc2name.start()
        self._p_comp2code.start()

        # 3. DB under test
        self.db = CDSSDatabase(excel=self._excel)

    def tearDown(self):
        # stop patches and clean tmp dir
        self._p_loinc2name.stop()
        self._p_comp2code.stop()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    # ───────────────────────── test‑cases ───────────────────────
    def test_history_loinc_code(self):
        """Exact LOINC code should return the row inside the date range."""
        res = self.db.history(
            patient="John Doe",
            code_or_cmp="1234-5",
            start=datetime(2025, 4, 19),
            end=datetime(2025, 4, 21, 23, 59),
            hh=None,
        )
        self.assertEqual(len(res), 1)
        self.assertEqual(res.iloc[0]["Value"], 7.5)
        self.assertEqual(res.iloc[0]["LOINC_NAME"], "Sample test")

    def test_history_component_alias(self):
        """Unique component alias should be resolved to the correct code."""
        res = self.db.history(
            patient="john doe",   # lower‑case → case‑insensitive match
            code_or_cmp="sample",
            start=datetime(2025, 4, 19),
            end=datetime(2025, 4, 21, 23, 59),
            hh=None,
        )
        self.assertEqual(len(res), 1)
        ts = pd.Timestamp("2025-04-20 10:00")
        self.assertEqual(res["Valid start time"].iloc[0], ts)

    def test_history_hour_filter(self):
        """`hh` parameter filters by exact clock‑time."""
        # 10:00 ➜ hit
        hit = self.db.history(
            "John Doe", "1234-5",
            datetime(2025, 4, 20), datetime(2025, 4, 20, 23, 59),
            hh=time(10, 0)
        )
        self.assertEqual(len(hit), 1)
        # 11:00 ➜ no rows
        miss = self.db.history(
            "John Doe", "1234-5",
            datetime(2025, 4, 20), datetime(2025, 4, 20, 23, 59),
            hh=time(11, 0)
        )
        self.assertTrue(miss.empty)


if __name__ == "__main__":
    unittest.main()
