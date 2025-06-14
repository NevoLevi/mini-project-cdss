# cdss_loinc.py — fully compliant
from __future__ import annotations
from pathlib import Path
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
import pandas as pd, zipfile, re
import json

ROOT         = Path(__file__).absolute().parent
EXCEL_PATH   = ROOT / "project_db.xlsx"
KB_PATH      = ROOT / "knowledge_base.json"
LOINC_ZIP    = ROOT / "Loinc_2.80.zip"
LOINC_TABLE  = "LoincTableCore/LoincTableCore.csv"
MIN_PATIENTS = 10
#_CODE_RGX    = re.compile(r"^\d{1,5}-\d$")
_CODE_RGX = re.compile(r"^\d{1,6}-\d$")
# define Israel timezone
IL_TZ = ZoneInfo("Asia/Jerusalem")

VALIDITY_PERIODS = {
    'Hemoglobin': {'Before-Good': timedelta(days=7), 'After-Good': timedelta(days=7)},
    'WBC': {'Before-Good': timedelta(days=3), 'After-Good': timedelta(days=3)},
    'Fever': {'Before-Good': timedelta(hours=12), 'After-Good': timedelta(hours=12)},
    'Chills': {'Before-Good': timedelta(hours=12), 'After-Good': timedelta(hours=12)},
    'Skin-look': {'Before-Good': timedelta(days=2), 'After-Good': timedelta(days=2)},
    'Allergic-state': {'Before-Good': timedelta(hours=12), 'After-Good': timedelta(hours=12)},
    'Therapy': {'Before-Good': timedelta(days=30), 'After-Good': timedelta(days=30)},
    'Gender': {'Before-Good': timedelta(days=365*100), 'After-Good': timedelta(days=365*100)},
}

class KnowledgeBase:
    """Editable Knowledge Base for medical classifications and treatments"""
    
    def __init__(self, kb_path: Path | str = KB_PATH):
        self.path = Path(kb_path)
        self.kb = self._load_or_create_kb()
    
    def _load_or_create_kb(self):
        """Load existing KB or create default one"""
        if self.path.exists():
            with open(self.path, 'r') as f:
                return json.load(f)
        else:
            return self._create_default_kb()
    
    def _create_default_kb(self):
        """Create default knowledge base with all classification tables"""
        kb = {
            "classification_tables": {
                "hemoglobin_state": {
                    "type": "1:1",
                    "inputs": ["Hemoglobin-level", "Gender"],
                    "output": "Hemoglobin-state",
                    "rules": {
                        "female": {
                            "ranges": [
                                {"min": 0, "max": 8, "state": "Severe Anemia"},
                                {"min": 8, "max": 10, "state": "Moderate Anemia"},
                                {"min": 10, "max": 12, "state": "Mild Anemia"},
                                {"min": 12, "max": 14, "state": "Normal Hemoglobin"},
                                {"min": 14, "max": 999, "state": "Polycytemia"}
                            ]
                        },
                        "male": {
                            "ranges": [
                                {"min": 0, "max": 9, "state": "Severe Anemia"},
                                {"min": 9, "max": 11, "state": "Moderate Anemia"},
                                {"min": 11, "max": 13, "state": "Mild Anemia"},
                                {"min": 13, "max": 16, "state": "Normal Hemoglobin"},
                                {"min": 16, "max": 999, "state": "Polyhemia"}
                            ]
                        }
                    }
                },
                "hematological_state": {
                    "type": "2:1_AND",
                    "inputs": ["Hemoglobin-level", "WBC-level", "Gender"],
                    "output": "Hematological-state",
                    "rules": {
                        "female": {
                            "matrix": [
                                {"hgb_range": [0, 12], "wbc_range": [0, 4000], "state": "Pancytopenia"},
                                {"hgb_range": [0, 12], "wbc_range": [4000, 10000], "state": "Anemia"},
                                {"hgb_range": [0, 12], "wbc_range": [10000, 999999], "state": "Suspected Leukemia"},
                                {"hgb_range": [12, 14], "wbc_range": [0, 4000], "state": "Leukopenia"},
                                {"hgb_range": [12, 14], "wbc_range": [4000, 10000], "state": "Normal"},
                                {"hgb_range": [12, 14], "wbc_range": [10000, 999999], "state": "Leukemoid reaction"},
                                {"hgb_range": [14, 999], "wbc_range": [0, 999999], "state": "Suspected Polycytemia Vera"}
                            ]
                        },
                        "male": {
                            "matrix": [
                                {"hgb_range": [0, 13], "wbc_range": [0, 4000], "state": "Pancytopenia"},
                                {"hgb_range": [0, 13], "wbc_range": [4000, 10000], "state": "Anemia"},
                                {"hgb_range": [0, 13], "wbc_range": [10000, 999999], "state": "Suspected Leukemia"},
                                {"hgb_range": [13, 16], "wbc_range": [0, 4000], "state": "Leukopenia"},
                                {"hgb_range": [13, 16], "wbc_range": [4000, 10000], "state": "Normal"},
                                {"hgb_range": [13, 16], "wbc_range": [10000, 999999], "state": "Leukemoid reaction"},
                                {"hgb_range": [16, 999], "wbc_range": [0, 999999], "state": "Suspected Polycytemia Vera"}
                            ]
                        }
                    }
                },
                "systemic_toxicity": {
                    "type": "4:1_MAXIMAL_OR",
                    "inputs": ["Fever", "Chills", "Skin-look", "Allergic-state"],
                    "output": "Systemic-Toxicity",
                    "rules": {
                        "fever": [
                            {"range": [0, 38.5], "grade": 1},
                            {"range": [38.5, 40.0], "grade": 2},
                            {"range": [40.0, 999], "grade": 3},
                            {"range": [40.0, 999], "grade": 4}
                        ],
                        "chills": [
                            {"value": "None", "grade": 1},
                            {"value": "Shaking", "grade": 2},
                            {"value": "Rigor", "grade": 3},
                            {"value": "Rigor", "grade": 4}
                        ],
                        "skin_look": [
                            {"value": "Erythema", "grade": 1},
                            {"value": "Vesiculation", "grade": 2},
                            {"value": "Desquamation", "grade": 3},
                            {"value": "Exfoliation", "grade": 4}
                        ],
                        "allergic_state": [
                            {"value": "Edema", "grade": 1},
                            {"value": "Bronchospasm", "grade": 2},
                            {"value": "Severe-Bronchospasm", "grade": 3},
                            {"value": "Anaphylactic-Shock", "grade": 4}
                        ]
                    }
                }
            },
            "treatments": {
                "male": {
                    "Severe Anemia + Pancytopenia + GRADE I": "Measure BP once a week",
                    "Moderate Anemia + Anemia + GRADE II": "Measure BP every 3 days\\nGive aspirin 5g twice a week",
                    "Mild Anemia + Suspected Leukemia + GRADE III": "Measure BP every day\\nGive aspirin 15g every day\\nDiet consultation",
                    "Normal Hemoglobin + Leukemoid reaction + GRADE IV": "Measure BP twice a day\\nGive aspirin 15g every day\\nExercise consultation\\nDiet consultation",
                    "Polyhemia + Suspected Polycytemia Vera + GRADE IV": "Measure BP every hour\\nGive 1 gr magnesium every hour\\nExercise consultation\\nCall family"
                },
                "female": {
                    "Severe Anemia + Pancytopenia + GRADE I": "Measure BP every 3 days",
                    "Moderate Anemia + Anemia + GRADE II": "Measure BP every 3 days\\nGive Celectone 2g twice a day for two days drug treatment",
                    "Mild Anemia + Suspected Leukemia + GRADE III": "Measure BP every day\\nGive 1 gr magnesium every 3 hours\\nDiet consultation",
                    "Normal Hemoglobin + Leukemoid reaction + GRADE IV": "Measure BP twice a day\\nGive 1 gr magnesium every hour\\nExercise consultation\\nDiet consultation",
                    "Polyhemia + Suspected Polycytemia Vera + GRADE IV": "Measure BP every hour\\nGive 1 gr magnesium every hour\\nExercise consultation\\nCall help"
                }
            },
            "validity_periods": VALIDITY_PERIODS
        }
        self._save_kb(kb)
        return kb
    
    def _save_kb(self, kb=None):
        """Save knowledge base to file"""
        if kb is None:
            kb = self.kb
        with open(self.path, 'w') as f:
            json.dump(kb, f, indent=2, default=str)
    
    def get_classification_table(self, table_name: str):
        """Get a specific classification table"""
        return self.kb["classification_tables"].get(table_name)
    
    def update_classification_table(self, table_name: str, table_data: dict):
        """Update a classification table"""
        self.kb["classification_tables"][table_name] = table_data
        self._save_kb()
    
    def get_treatments(self):
        """Get all treatment rules"""
        return self.kb["treatments"]
    
    def update_treatments(self, treatments: dict):
        """Update treatment rules"""
        self.kb["treatments"] = treatments
        self._save_kb()
    
    def get_validity_periods(self):
        """Get validity periods for all parameters"""
        return self.kb["validity_periods"]
    
    def update_validity_periods(self, periods: dict):
        """Update validity periods"""
        self.kb["validity_periods"] = periods
        self._save_kb()

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
    
    # Add essential medical parameters for Part 2
    essential_params = {
        'gender': '46098-0',
        'hemoglobin': '718-7', 
        'wbc': '6690-2',
        'fever': '8310-5',
        'chills': '427359001',
        'skin-look': '28214007',
        'allergic-state': '419199007',
        'therapy': '182836005'
    }
    
    # Merge with existing mappings
    comp2code.update(essential_params)
    
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
        self.kb   = KnowledgeBase()
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
                hh: time | None = None,
                query_time: datetime | None = None) -> pd.DataFrame:
        code = self._normalise_code(code_or_cmp)
        
        df = self.df
        if query_time:
            df = df[df["Transaction time"] <= query_time]

        m = (df["Patient"].str.casefold() == patient.casefold()) & \
            (df["LOINC-NUM"] == code) & \
            df["Valid start time"].between(start, end)

        if hh:
            m &= df["Valid start time"].dt.time == hh

        # keep only the newest version per (Patient, LOINC, Valid-time)
        key_cols = ["Patient", "LOINC-NUM", "Valid start time"]
        idx = (
            df.loc[m]
            .sort_values("Transaction time")
            .groupby(key_cols, as_index=False)
            .tail(1)
            .index
        )
        return self._with_name(
            df.loc[idx].sort_values("Valid start time").reset_index(drop=True)
        )

    def get_latest_value(self, patient: str, code_or_cmp: str, query_time: datetime | None = None):
        code = self._normalise_code(code_or_cmp)
        
        df = self.df
        if query_time:
            # Filter by transaction time
            df = df[df["Transaction time"] <= query_time]
        
        # Filter for the patient and code
        m_patient_code = (df["Patient"].str.casefold() == patient.casefold()) & \
                         (df["LOINC-NUM"] == code)
        
        df_patient = df[m_patient_code]

        if df_patient.empty:
            return None, None

        # For each valid time, find the latest transaction
        idx = df_patient.sort_values("Transaction time").groupby("Valid start time").tail(1).index

        # From these, find the one with the latest valid time
        latest_record = df.loc[idx].sort_values("Valid start time").tail(1)

        if not latest_record.empty:
            return latest_record["Value"].iloc[0], latest_record["Unit"].iloc[0]
        return None, None

    # ─────────── 2.2 Update ───────────
    def update(self, patient: str, code_or_cmp: str,
               valid_dt: datetime, new_val,
               now: datetime | None = None,
               transaction_time: datetime | None = None) -> pd.DataFrame:
        code = self._normalise_code(code_or_cmp)

        # now = now or datetime.now()

        # use Israel local time, rounded to minute
        now = (now or datetime.now(tz=IL_TZ)).replace(second=0, microsecond=0)
        # then drop tzinfo so Excel can handle it
        now_aware = now.replace(tzinfo=IL_TZ) if now.tzinfo is None else now
        now = now_aware.replace(tzinfo=None)

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
            timemask = (
                    (self.df["Patient"].str.casefold() == patient.casefold()) &
                    (self.df["LOINC-NUM"] == code) &
                    (self.df["Valid start time"] == target)
            )
            if timemask.sum() == 0:
                raise ValueError("No measurement at that date/time")

            # keep only the newest *Transaction* row for that Valid-time
            idx_last = self.df.loc[timemask, "Transaction time"].idxmax()
            mask = self.df.index == idx_last
        else:
            start = datetime.combine(day, time.min)
            stop = datetime.combine(day, time.max)
            daymask = (
                    (self.df["Patient"].str.casefold() == patient.casefold()) &
                    (self.df["LOINC-NUM"] == code) &
                    self.df["Valid start time"].between(start, stop)
            )
            if daymask.sum() == 0:
                raise ValueError("No measurement on that date")

            # pick row with **latest Transaction-time** (true "last edit")
            idx_last = (
                self.df.loc[daymask]
                .sort_values("Transaction time")
                .tail(1)
                .index
            )
            mask = self.df.index.isin(idx_last)

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

    def get_patient_states(self, patient: str, query_time: datetime | None = None) -> dict:
        states = {}
        # Gender
        gender, _ = self.get_latest_value(patient, 'Gender', query_time)
        states['Gender'] = gender

        # Hemoglobin
        hgb_level, _ = self.get_latest_value(patient, "Hemoglobin", query_time)
        states['Hemoglobin-level'] = hgb_level
        if hgb_level is not None:
             states['Hemoglobin-state'] = get_hemoglobin_state(hgb_level, gender)
        else:
             states['Hemoglobin-state'] = "N/A"
        
        # WBC
        wbc_level, _ = self.get_latest_value(patient, "WBC", query_time)
        states['WBC-level'] = wbc_level

        # Hematological-state
        states['Hematological-state'] = get_hematological_state(hgb_level, wbc_level, gender)

        # Systemic Toxicity
        states['Systemic-Toxicity'] = self.get_systemic_toxicity(patient, query_time)
        
        states['Recommendation'] = get_treatment_recommendation(
            states['Gender'],
            states['Hemoglobin-state'],
            states['Hematological-state'],
            states['Systemic-Toxicity']
        )

        return states

    def get_systemic_toxicity(self, patient: str, query_time: datetime | None = None) -> (str | None):
        # Check for Therapy=CCTG522
        try:
            therapy_val, _ = self.get_latest_value(patient, "Therapy", query_time)
            if therapy_val != "CCTG522":
                return "N/A (Therapy not CCTG522)"
        except ValueError: # If Therapy code is not found
            return "N/A (Therapy code not found)"

        try:
            fever_val, _ = self.get_latest_value(patient, "Fever", query_time)
            chills_val, _ = self.get_latest_value(patient, "Chills", query_time)
            skin_look_val, _ = self.get_latest_value(patient, "Skin-look", query_time)
            allergic_state_val, _ = self.get_latest_value(patient, "Allergic-state", query_time)
        except ValueError as e:
            return f"N/A (Component not found: {e})"

        grades = [
            get_fever_grade(fever_val),
            get_chills_grade(chills_val),
            get_skin_look_grade(skin_look_val),
            get_allergic_state_grade(allergic_state_val)
        ]
        
        max_grade = max(grades) if grades else 0
        
        if max_grade == 0:
            return "No toxicity data"
            
        grade_map = {1: 'I', 2: 'II', 3: 'III', 4: 'IV'}
        return f"Grade {grade_map.get(max_grade)}"

    # synth patients
    def _synth_patients(self):
        """Enhanced patient synthesis with comprehensive medical data for Part 2"""
        import random
        from datetime import datetime, timedelta
        
        # Define patient data
        males = [("David", "Cohen"), ("Michael", "Levi"), ("Daniel", "Katz"), ("Jonathan", "Ben-David"), ("Eli", "Goldberg")]
        females = [("Sarah", "Rosen"), ("Rachel", "Shapiro"), ("Miriam", "Klein"), ("Tamar", "Abraham"), ("Naomi", "Friedman")]
        
        # Get current available LOINC codes from data
        existing_codes = self.df["LOINC-NUM"].unique().tolist() if not self.df.empty else []
        
        # Add essential codes if not present (using common LOINC codes or placeholders)
        essential_codes = {
            'Gender': '46098-0',  # Gender LOINC code
            'Hemoglobin': '718-7',  # Hemoglobin LOINC code
            'WBC': '6690-2',  # WBC count LOINC code  
            'Fever': '8310-5',  # Body temperature LOINC code
            'Chills': '427359001',  # Chills SNOMED/custom code
            'Skin-look': '28214007',  # Skin appearance SNOMED/custom code
            'Allergic-state': '419199007',  # Allergic state SNOMED/custom code
            'Therapy': '182836005'  # Therapy SNOMED/custom code
        }
        
        # Test scenarios for different medical states
        test_scenarios = [
            # Scenario 1: Severe anemia with high toxicity (urgent)
            {
                'gender': 'Female',
                'hemoglobin': 7.5,  # Severe anemia
                'wbc': 3500,        # Low WBC -> Pancytopenia
                'fever': 40.5,      # High fever -> Grade III
                'chills': 'Rigor',
                'skin': 'Desquamation', 
                'allergic': 'Bronchospasm',
                'therapy': 'CCTG522'
            },
            # Scenario 2: Normal patient
            {
                'gender': 'Male', 
                'hemoglobin': 15.0,  # Normal
                'wbc': 6000,         # Normal
                'fever': 37.0,       # Normal
                'chills': 'None',
                'skin': 'Erythema',
                'allergic': 'Edema',
                'therapy': 'CCTG522'
            },
            # Scenario 3: Moderate anemia 
            {
                'gender': 'Female',
                'hemoglobin': 9.5,   # Moderate anemia
                'wbc': 5500,         # Normal -> Anemia state
                'fever': 39.0,       # Grade II
                'chills': 'Shaking',
                'skin': 'Vesiculation',
                'allergic': 'Edema', 
                'therapy': 'CCTG522'
            },
            # Scenario 4: Polycytemia with severe toxicity
            {
                'gender': 'Male',
                'hemoglobin': 18.0,  # Polyhemia  
                'wbc': 12000,        # High -> Suspected Polycytemia Vera
                'fever': 40.0,       # Grade IV
                'chills': 'Rigor',
                'skin': 'Exfoliation',
                'allergic': 'Anaphylactic-Shock',
                'therapy': 'CCTG522'
            },
            # Scenario 5: Suspected leukemia
            {
                'gender': 'Female',
                'hemoglobin': 11.0,  # Mild anemia
                'wbc': 15000,        # Very high -> Suspected Leukemia
                'fever': 38.8,       # Grade II
                'chills': 'Shaking',
                'skin': 'Desquamation',
                'allergic': 'Severe-Bronchospasm',
                'therapy': 'CCTG522'
            }
        ]
        
        # Generate data for enough patients
        all_patients = males + females
        base_date = datetime(2025, 4, 15)
        
        need = max(MIN_PATIENTS - self.df["Patient"].nunique(), 5)
        
        for i in range(need):
            if i < len(all_patients):
                first, last = all_patients[i]
            else:
                # Generate additional patients if needed
                first = f"Patient{i+1}"
                last = "Generated"
            
            patient_name = f"{first} {last}"
            
            # Choose a scenario (cycle through scenarios)
            scenario = test_scenarios[i % len(test_scenarios)]
            
            # Generate measurements over time with some variation
            for day_offset in range(0, 10, 2):  # Every 2 days for 10 days
                measurement_date = base_date + timedelta(days=day_offset)
                transaction_date = measurement_date + timedelta(hours=random.randint(1, 12))
                
                # Add some realistic variation to values
                variation = random.uniform(0.9, 1.1)
                
                # Generate all medical parameter measurements
                measurements = [
                    (essential_codes['Gender'], scenario['gender'], ''),
                    (essential_codes['Hemoglobin'], round(scenario['hemoglobin'] * variation, 1), 'g/dL'),
                    (essential_codes['WBC'], int(scenario['wbc'] * variation), 'cells/mL'),
                    (essential_codes['Fever'], round(scenario['fever'] * random.uniform(0.98, 1.02), 1), 'Celsius'),
                    (essential_codes['Chills'], scenario['chills'], ''),
                    (essential_codes['Skin-look'], scenario['skin'], ''),
                    (essential_codes['Allergic-state'], scenario['allergic'], ''),
                    (essential_codes['Therapy'], scenario['therapy'], '')
                ]
                
                # Add measurements to database
                for loinc_code, value, unit in measurements:
                    new_row = pd.DataFrame({
                        "First name": [first],
                        "Last name": [last],
                        "LOINC-NUM": [loinc_code],
                        "Value": [value],
                        "Unit": [unit],
                        "Valid start time": [measurement_date],
                        "Transaction time": [transaction_date],
                        "Patient": [patient_name],
                    })
                    
                    self.df = pd.concat([self.df, new_row], ignore_index=True)
        
        # Save to file
        self._flush()
        print(f"Enhanced database with comprehensive medical data for {need} patients")

    def get_state_intervals(self, patient: str, state_type: str, target_state: str):
        """Enhanced state interval calculation supporting all state types"""
        patient_df = self.df[self.df["Patient"].str.casefold() == patient.casefold()].copy()
        if patient_df.empty:
            return []

        validity_periods = self.kb.get_validity_periods()
        
        if state_type == "Hemoglobin-state":
            return self._get_hemoglobin_intervals(patient, target_state, validity_periods)
        elif state_type == "Hematological-state":
            return self._get_hematological_intervals(patient, target_state, validity_periods)
        elif state_type == "Systemic-Toxicity":
            return self._get_systemic_toxicity_intervals(patient, target_state, validity_periods)
        else:
            return []

    def _get_hemoglobin_intervals(self, patient: str, target_state: str, validity_periods: dict):
        """Calculate intervals for Hemoglobin-state"""
        gender, _ = self.get_latest_value(patient, 'Gender')
        if not gender:
            return []
            
        patient_df = self.df[self.df["Patient"].str.casefold() == patient.casefold()].copy()
        hgb_df = patient_df[patient_df['LOINC-NUM'] == COMP2CODE.get('hemoglobin')].copy()
        
        intervals = []
        for _, row in hgb_df.iterrows():
            hgb_level = row['Value']
            current_state = get_hemoglobin_state(hgb_level, gender)
            
            if current_state == target_state:
                validity = validity_periods.get('Hemoglobin', {'Before-Good': timedelta(0), 'After-Good': timedelta(0)})
                start_interval = row['Valid start time'] - validity['Before-Good']
                end_interval = row['Valid start time'] + validity['After-Good']
                intervals.append((start_interval, end_interval))
        
        return self._merge_intervals(intervals)

    def _get_hematological_intervals(self, patient: str, target_state: str, validity_periods: dict):
        """Calculate intervals for Hematological-state"""
        gender, _ = self.get_latest_value(patient, 'Gender')
        if not gender:
            return []
            
        # Get all hemoglobin and WBC measurements
        patient_df = self.df[self.df["Patient"].str.casefold() == patient.casefold()].copy()
        hgb_code = COMP2CODE.get('hemoglobin')
        wbc_code = COMP2CODE.get('wbc')
        
        if not hgb_code or not wbc_code:
            return []
            
        hgb_df = patient_df[patient_df['LOINC-NUM'] == hgb_code].copy()
        wbc_df = patient_df[patient_df['LOINC-NUM'] == wbc_code].copy()
        
        intervals = []
        
        # For each combination of HGB and WBC measurements, check if they create the target state
        for _, hgb_row in hgb_df.iterrows():
            for _, wbc_row in wbc_df.iterrows():
                hgb_level = hgb_row['Value']
                wbc_level = wbc_row['Value']
                
                current_state = get_hematological_state(hgb_level, wbc_level, gender)
                
                if current_state == target_state:
                    # Calculate overlapping validity period
                    hgb_validity = validity_periods.get('Hemoglobin', {'Before-Good': timedelta(0), 'After-Good': timedelta(0)})
                    wbc_validity = validity_periods.get('WBC', {'Before-Good': timedelta(0), 'After-Good': timedelta(0)})
                    
                    hgb_start = hgb_row['Valid start time'] - hgb_validity['Before-Good']
                    hgb_end = hgb_row['Valid start time'] + hgb_validity['After-Good']
                    wbc_start = wbc_row['Valid start time'] - wbc_validity['Before-Good']
                    wbc_end = wbc_row['Valid start time'] + wbc_validity['After-Good']
                    
                    # Intersection of validity periods
                    start_interval = max(hgb_start, wbc_start)
                    end_interval = min(hgb_end, wbc_end)
                    
                    if start_interval <= end_interval:
                        intervals.append((start_interval, end_interval))
        
        return self._merge_intervals(intervals)

    def _get_systemic_toxicity_intervals(self, patient: str, target_state: str, validity_periods: dict):
        """Calculate intervals for Systemic-Toxicity state"""
        # Check if therapy is CCTG522
        therapy_val, _ = self.get_latest_value(patient, "Therapy")
        if therapy_val != "CCTG522":
            return []
            
        patient_df = self.df[self.df["Patient"].str.casefold() == patient.casefold()].copy()
        
        # Get all required parameter measurements
        fever_code = COMP2CODE.get('fever')
        chills_code = COMP2CODE.get('chills')
        skin_code = COMP2CODE.get('skin-look')
        allergic_code = COMP2CODE.get('allergic-state')
        
        param_dfs = {}
        for param, code in [('fever', fever_code), ('chills', chills_code), 
                           ('skin', skin_code), ('allergic', allergic_code)]:
            if code:
                param_dfs[param] = patient_df[patient_df['LOINC-NUM'] == code].copy()
            else:
                param_dfs[param] = pd.DataFrame()
        
        intervals = []
        
        # For each combination of measurements, check if they create the target toxicity level
        for _, fever_row in param_dfs['fever'].iterrows():
            for _, chills_row in param_dfs['chills'].iterrows():
                for _, skin_row in param_dfs['skin'].iterrows():
                    for _, allergic_row in param_dfs['allergic'].iterrows():
                        
                        grades = [
                            get_fever_grade(fever_row['Value']),
                            get_chills_grade(chills_row['Value']),
                            get_skin_look_grade(skin_row['Value']),
                            get_allergic_state_grade(allergic_row['Value'])
                        ]
                        
                        max_grade = max(grades) if grades else 0
                        grade_map = {1: 'I', 2: 'II', 3: 'III', 4: 'IV'}
                        current_state = f"Grade {grade_map.get(max_grade)}" if max_grade > 0 else "No toxicity"
                        
                        if current_state == target_state:
                            # Calculate intersection of all validity periods
                            validities = [
                                (fever_row['Valid start time'], validity_periods.get('Fever', {'Before-Good': timedelta(0), 'After-Good': timedelta(0)})),
                                (chills_row['Valid start time'], validity_periods.get('Chills', {'Before-Good': timedelta(0), 'After-Good': timedelta(0)})),
                                (skin_row['Valid start time'], validity_periods.get('Skin-look', {'Before-Good': timedelta(0), 'After-Good': timedelta(0)})),
                                (allergic_row['Valid start time'], validity_periods.get('Allergic-state', {'Before-Good': timedelta(0), 'After-Good': timedelta(0)}))
                            ]
                            
                            starts = []
                            ends = []
                            for valid_time, validity in validities:
                                starts.append(valid_time - validity['Before-Good'])
                                ends.append(valid_time + validity['After-Good'])
                            
                            start_interval = max(starts)
                            end_interval = min(ends)
                            
                            if start_interval <= end_interval:
                                intervals.append((start_interval, end_interval))
        
        return self._merge_intervals(intervals)

    def _merge_intervals(self, intervals):
        """Merge overlapping intervals"""
        if not intervals:
            return []
            
        intervals.sort(key=lambda x: x[0])
        
        merged = [intervals[0]]
        for current_start, current_end in intervals[1:]:
            last_start, last_end = merged[-1]
            if current_start <= last_end:
                merged[-1] = (last_start, max(last_end, current_end))
            else:
                merged.append((current_start, current_end))
                
        return merged

    def get_all_patient_states_at_time(self, query_time: datetime) -> pd.DataFrame:
        """Get all patients' states at a specific time point"""
        patients = self.df["Patient"].unique()
        all_states = []
        
        for patient in patients:
            states = self.get_patient_states(patient, query_time)
            states["Patient"] = patient
            all_states.append(states)
        
        return pd.DataFrame(all_states) if all_states else pd.DataFrame()

    def get_context_based_query(self, context: str, query_params: dict) -> pd.DataFrame:
        """Execute context-based queries (medical context)"""
        if context.lower() == "systemic-toxicity":
            return self._query_systemic_toxicity_context(query_params)
        elif context.lower() == "hematological-state":
            return self._query_hematological_context(query_params)
        elif context.lower() == "hemoglobin-state":
            return self._query_hemoglobin_context(query_params)
        else:
            return pd.DataFrame()

    def _query_systemic_toxicity_context(self, params: dict) -> pd.DataFrame:
        """Query patients with specific systemic toxicity criteria"""
        results = []
        patients = self.df["Patient"].unique()
        
        for patient in patients:
            toxicity = self.get_systemic_toxicity(patient, params.get('query_time'))
            if params.get('target_grade') and toxicity == params['target_grade']:
                result = {
                    'Patient': patient,
                    'Systemic-Toxicity': toxicity,
                    'Query-Time': params.get('query_time', 'Latest')
                }
                results.append(result)
        
        return pd.DataFrame(results)

    def _query_hematological_context(self, params: dict) -> pd.DataFrame:
        """Query patients with specific hematological criteria"""
        results = []
        patients = self.df["Patient"].unique()
        
        for patient in patients:
            states = self.get_patient_states(patient, params.get('query_time'))
            if params.get('target_state') and states.get('Hematological-state') == params['target_state']:
                results.append({
                    'Patient': patient,
                    'Hematological-state': states.get('Hematological-state'),
                    'Hemoglobin-level': states.get('Hemoglobin-level'),
                    'WBC-level': states.get('WBC-level'),
                    'Query-Time': params.get('query_time', 'Latest')
                })
        
        return pd.DataFrame(results)

    def _query_hemoglobin_context(self, params: dict) -> pd.DataFrame:
        """Query patients with specific hemoglobin criteria"""
        results = []
        patients = self.df["Patient"].unique()
        
        for patient in patients:
            states = self.get_patient_states(patient, params.get('query_time'))
            if params.get('target_state') and states.get('Hemoglobin-state') == params['target_state']:
                results.append({
                    'Patient': patient,
                    'Hemoglobin-state': states.get('Hemoglobin-state'),
                    'Hemoglobin-level': states.get('Hemoglobin-level'),
                    'Gender': states.get('Gender'),
                    'Query-Time': params.get('query_time', 'Latest')
                })
        
        return pd.DataFrame(results)

def get_fever_grade(temp_val):
    if temp_val is None: return 0
    try:
        temp = float(temp_val)
        if temp >= 40.0: return 4  # Grade IV for 40.0+ Celsius
        if 38.5 < temp < 40.0: return 2
        if temp <= 38.5: return 1
    except (ValueError, TypeError):
        return 0
    return 0

def get_chills_grade(chills_val):
    if chills_val is None: return 0
    val = str(chills_val).lower()
    if val == 'rigor': return 4
    if val == 'shaking': return 2
    if val == 'none': return 1
    return 0

def get_skin_look_grade(skin_val):
    if skin_val is None: return 0
    val = str(skin_val).lower()
    if val == 'exfoliation': return 4
    if val == 'desquamation': return 3
    if val == 'vesiculation': return 2
    if val == 'erythema': return 1
    return 0

def get_allergic_state_grade(allergic_val):
    if allergic_val is None: return 0
    val = str(allergic_val).lower()
    if val == 'anaphylactic-shock': return 4
    if val == 'severe-bronchospasm': return 3
    if val == 'bronchospasm': return 2
    if val == 'edema': return 1
    return 0

def get_hemoglobin_state(hgb_level, gender):
    if hgb_level is None or gender is None:
        return "N/A"
    try:
        gender = str(gender).lower()
        hgb = float(hgb_level)
    except (ValueError, TypeError):
        return "N/A (Invalid Value)"

    if gender == 'female':
        if hgb < 8: return "Severe Anemia"
        if hgb < 10: return "Moderate Anemia"
        if hgb < 12: return "Mild Anemia"
        if hgb <= 14: return "Normal Hemoglobin"
        return "Polycytemia"
    elif gender == 'male':
        if hgb < 9: return "Severe Anemia"
        if hgb < 11: return "Moderate Anemia"
        if hgb < 13: return "Mild Anemia"
        if hgb <= 16: return "Normal Hemoglobin"
        return "Polyhemia"
    else:
        return "N/A (Unknown Gender)"

def get_hematological_state(hgb_level, wbc_level, gender):
    if hgb_level is None or wbc_level is None or gender is None:
        return "N/A"
    try:
        gender = str(gender).lower()
        hgb = float(hgb_level)
        wbc = float(wbc_level)
    except (ValueError, TypeError):
        return "N/A (Invalid Value)"

    if gender == 'male':
        if hgb < 13:
            if wbc < 4000: return "Pancytopenia"
            if wbc <= 10000: return "Anemia"
            return "Suspected Leukemia"
        elif hgb <= 16:
            if wbc < 4000: return "Leukopenia"
            if wbc <= 10000: return "Normal"
            return "Leukemoid reaction"
        else: # hgb > 16
            return "Suspected Polycytemia Vera"
    elif gender == 'female':
        if hgb < 12:
            if wbc < 4000: return "Pancytopenia"
            if wbc <= 10000: return "Anemia"
            return "Suspected Leukemia"
        elif hgb <= 14:
            if wbc < 4000: return "Leukopenia"
            if wbc <= 10000: return "Normal"
            return "Leukemoid reaction"
        else: # hgb > 14
            return "Suspected Polycytemia Vera"
    else:
        return "N/A (Unknown Gender)"

def get_treatment_recommendation(gender, hemoglobin_state, hematological_state, systemic_toxicity):
    if any(s is None or s.startswith("N/A") for s in [gender, hemoglobin_state, hematological_state, systemic_toxicity]):
        return "N/A"

    gender = gender.lower()

    # Normalize systemic_toxicity to GRADE X format
    if "Grade" in systemic_toxicity:
        systemic_toxicity = systemic_toxicity.replace("Grade ", "GRADE ")

    if gender == 'male':
        if hemoglobin_state == "Severe Anemia" and hematological_state == "Pancytopenia" and systemic_toxicity == "GRADE I":
            return "Measure BP once a week"
        if hemoglobin_state == "Moderate Anemia" and hematological_state == "Anemia" and systemic_toxicity == "GRADE II":
            return "Measure BP every 3 days\nGive aspirin 5g twice a week"
        if hemoglobin_state == "Mild Anemia" and hematological_state == "Suspected Leukemia" and systemic_toxicity == "GRADE III":
            return "Measure BP every day\nGive aspirin 15g every day\nDiet consultation"
        if hemoglobin_state == "Normal Hemoglobin" and hematological_state == "Leukemoid reaction" and systemic_toxicity == "GRADE IV":
            return "Measure BP twice a day\nGive aspirin 15g every day\nExercise consultation\nDiet consultation"
        if hemoglobin_state == "Polyhemia" and hematological_state == "Suspected Polycytemia Vera" and systemic_toxicity == "GRADE IV":
            return "Measure BP every hour\nGive 1 gr magnesium every hour\nExercise consultation\nCall family"
    
    elif gender == 'female':
        if hemoglobin_state == "Severe Anemia" and hematological_state == "Pancytopenia" and systemic_toxicity == "GRADE I":
            return "Measure BP every 3 days"
        if hemoglobin_state == "Moderate Anemia" and hematological_state == "Anemia" and systemic_toxicity == "GRADE II":
            return "Measure BP every 3 days\nGive Celectone 2g twice a day for two days drug treatment"
        if hemoglobin_state == "Mild Anemia" and hematological_state == "Suspected Leukemia" and systemic_toxicity == "GRADE III":
            return "Measure BP every day\nGive 1 gr magnesium every 3 hours\nDiet consultation"
        if hemoglobin_state == "Normal Hemoglobin" and hematological_state == "Leukemoid reaction" and systemic_toxicity == "GRADE IV":
            return "Measure BP twice a day\nGive 1 gr magnesium every hour\nExercise consultation\nDiet consultation"
        if hemoglobin_state == "Polyhemia" and hematological_state == "Suspected Polycytemia Vera" and systemic_toxicity == "GRADE IV":
            return "Measure BP every hour\nGive 1 gr magnesium every hour\nExercise consultation\nCall help"

    return "No specific recommendation"
