# cdss_loinc.py — fully compliant
from __future__ import annotations
from pathlib import Path
from datetime import datetime, date, time
import pandas as pd, zipfile, re

ROOT         = Path(__file__).absolute().parent
EXCEL_PATH   = ROOT / "project_db.xlsx"
LOINC_ZIP    = ROOT / "Loinc_2.80.zip"
LOINC_TABLE  = "LoincTableCore/LoincTableCore.csv"
MIN_PATIENTS = 10
_CODE_RGX    = re.compile(r"^\d{1,5}-\d$")

# ── load full LOINC release
def _load_loinc():
    with zipfile.ZipFile(LOINC_ZIP) as z, z.open(LOINC_TABLE) as fh:
        df = pd.read_csv(
            fh, low_memory=False,
            usecols=["LOINC_NUM", "COMPONENT", "LONG_COMMON_NAME"]
        )
    loinc2name = df.set_index("LOINC_NUM")["LONG_COMMON_NAME"]
    counts = df.groupby("COMPONENT")["LOINC_NUM"].nunique()
    uniques = counts[counts == 1].index
    comp2code = (
        df[df["COMPONENT"].isin(uniques)]
        .set_index("COMPONENT")["LOINC_NUM"]
        .str.upper()
        .to_dict()
    )
    comp2code = {k.casefold(): v for k, v in comp2code.items()}
    return loinc2name, comp2code

LOINC2NAME, COMP2CODE = _load_loinc()

# ── helpers
def parse_dt(tok: str, *, date_only=False):
    tok = tok.strip()
    if date_only:
        return datetime.now().date() if tok.lower() == "today" else date.fromisoformat(tok)
    return datetime.now() if tok.lower() == "now" else datetime.fromisoformat(tok)

class CDSSDatabase:
    _PAT = ("First name", "Last name")

    def __init__(self, excel: Path | str = EXCEL_PATH):
        self.path = Path(excel)
        self.df   = self._load_excel()
        if self.df["Patient"].nunique() < MIN_PATIENTS:
            self._synth_patients()

    # persistence
    def _load_excel(self):
        #df = pd.read_excel(self.path)
        df = pd.read_excel(self.path, engine="openpyxl")
        df["Valid start time"] = pd.to_datetime(df["Valid start time"])
        df["Transaction time"] = pd.to_datetime(df["Transaction time"])
        df["Patient"] = (
            df["First name"].str.title().str.strip() + " " +
            df["Last name"].str.title().str.strip()
        )
        return df

    def _flush(self):
        cols = list(self._PAT) + ["LOINC-NUM", "Value", "Unit",
                                  "Valid start time", "Transaction time"]
        self.df[cols].to_excel(self.path, index=False)

    # LOINC
    @staticmethod
    def _is_code(t: str) -> bool:
        return bool(_CODE_RGX.match(t))

    def _normalise_code(self, token: str) -> str:
        if self._is_code(token):
            if token not in LOINC2NAME.index:
                raise ValueError("Unknown LOINC code")
            return token
        code = COMP2CODE.get(token.casefold())
        if not code:
            raise ValueError("Component ambiguous or not unique")
        return code

    def _with_name(self, df: pd.DataFrame) -> pd.DataFrame:
        return df.assign(LOINC_NAME=lambda d: d["LOINC-NUM"].map(LOINC2NAME))

    # ─────────── 2.1 History ───────────
    def history(self, patient: str, code_or_cmp: str,
                start: datetime, end: datetime,
                hh: time | None = None) -> pd.DataFrame:
        code = self._normalise_code(code_or_cmp)
        m = (self.df["Patient"].str.casefold() == patient.casefold()) & \
            (self.df["LOINC-NUM"] == code) & \
            self.df["Valid start time"].between(start, end)

        if hh:
            m &= self.df["Valid start time"].dt.time == hh

        # keep only the newest version per (Patient, LOINC, Valid-time)
        key_cols = ["Patient", "LOINC-NUM", "Valid start time"]
        idx = (
            self.df.loc[m]
            .sort_values("Transaction time")
            .groupby(key_cols, as_index=False)
            .tail(1)
            .index
        )
        return self._with_name(
            self.df.loc[idx].sort_values("Valid start time").reset_index(drop=True)
        )

    # ─────────── 2.2 Update ───────────
    def update(self, patient: str, code_or_cmp: str,
               valid_dt: datetime, new_val,
               now: datetime | None = None) -> pd.DataFrame:
        code = self._normalise_code(code_or_cmp)
        now = now or datetime.now()
        m = (self.df["Patient"].str.casefold() == patient.casefold()) & \
            (self.df["LOINC-NUM"] == code) & \
            (self.df["Valid start time"] == valid_dt)
        if m.sum() == 0:
            raise ValueError("No matching measurement")

        idx_last = self.df.loc[m, "Transaction time"].idxmax()
        row = self.df.loc[[idx_last]].copy()
        row["Value"] = new_val
        row["Transaction time"] = now

        self.df = pd.concat([self.df, row], ignore_index=True)
        self._flush()
        return self._with_name(row)

    # ─────────── 2.3 Delete ───────────
    def delete(self, patient: str, code_or_cmp: str,
               day: date, hh: time | None = None) -> pd.DataFrame:
        code = self._normalise_code(code_or_cmp)

        if hh:
            target = datetime.combine(day, hh)
            mask = (self.df["Patient"].str.casefold() == patient.casefold()) & \
                   (self.df["LOINC-NUM"] == code) & \
                   (self.df["Valid start time"] == target)
        else:
            start = datetime.combine(day, time.min)
            stop  = datetime.combine(day, time.max)
            daymask = (self.df["Patient"].str.casefold() == patient.casefold()) & \
                      (self.df["LOINC-NUM"] == code) & \
                      self.df["Valid start time"].between(start, stop)
            if daymask.sum() == 0:
                raise ValueError("No measurement on that date")
            idx_last = self.df.loc[daymask, "Valid start time"].idxmax()
            mask = self.df.index == idx_last

        deleted = self.df.loc[mask]
        self.df.drop(index=deleted.index, inplace=True)
        self._flush()
        return self._with_name(deleted)

    # ─────────── Dashboard ───────────
    def status(self) -> pd.DataFrame:
        idx = (self.df.sort_values("Valid start time")
                     .groupby(["Patient", "LOINC-NUM"])
                     .tail(1).index)
        return self._with_name(self.df.loc[idx]
                               .sort_values(["Patient", "LOINC-NUM"])
                               .reset_index(drop=True))

    # synth patients
    def _synth_patients(self):
        males   = [("Avi", "Cohen"), ("Moshe", "Dayan"), ("Yossi", "Katz")]
        females = [("Ruth", "Bar"), ("Noa", "Shalev"), ("Dana", "Ziv")]
        codes   = list(LOINC2NAME.index[:3])
        unit    = self.df["Unit"].dropna().iloc[0] if not self.df["Unit"].isna().all() else "unit"

        need = MIN_PATIENTS - self.df["Patient"].nunique()
        for first, last in (males + females) * 2[:need]:
            p = f"{first} {last}"
            for c in codes:
                self.df = pd.concat([self.df, pd.DataFrame({
                    "First name": [first],
                    "Last name" : [last],
                    "LOINC-NUM" : [c],
                    "Value"     : [pd.NA],
                    "Unit"      : [unit],
                    "Valid start time": [pd.Timestamp("2018-01-01")],
                    "Transaction time": [pd.Timestamp("2018-01-02")],
                    "Patient"   : [p],
                })], ignore_index=True)
        self._flush()
