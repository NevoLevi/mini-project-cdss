from __future__ import annotations
from pathlib import Path
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
import pandas as pd, zipfile, re
import json

ROOT         = Path(__file__).absolute().parent
EXCEL_PATH   = ROOT / "enhanced_project_db.xlsx"  # Use enhanced database
KB_PATH      = ROOT / "knowledge_base.json"
LOINC_ZIP    = ROOT / "Loinc_2.80.zip"
LOINC_TABLE  = "LoincTableCore/LoincTableCore.csv"
MAPPING_PATH = ROOT / "database_mapping_info.json"
MIN_PATIENTS = 10
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

# Load parameter mappings
try:
    with open(MAPPING_PATH, 'r') as f:
        MAPPING_INFO = json.load(f)
        
    # Create reverse mapping from parameter type to LOINC codes
    PARAM_TO_LOINC = {}
    for loinc, info in MAPPING_INFO['LOINC_Mappings'].items():
        PARAM_TO_LOINC[info['parameter']] = loinc
    for param, loinc in MAPPING_INFO['Synthetic_LOINC_Codes'].items():
        PARAM_TO_LOINC[param] = loinc
        
except Exception as e:
    print(f"Warning: Could not load mapping info: {e}")
    MAPPING_INFO = {}
    PARAM_TO_LOINC = {}

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
    comp2code = {}
    for comp in uniques:
        loinc = df[df["COMPONENT"] == comp]["LOINC_NUM"].iloc[0]
        comp2code[comp.casefold()] = loinc
    return loinc2name, comp2code

LOINC2NAME, COMP2CODE = _load_loinc()

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

def parse_dt(tok: str, *, date_only=False):
    # ... (keep original implementation)
    pass

class EnhancedCDSSDatabase:
    """Enhanced CDSS Database with parameter mapping support"""
    _PAT = ("First name", "Last name")

    def __init__(self, excel: Path | str = EXCEL_PATH):
        self.path = Path(excel)
        self.df   = self._load_excel()
        self.kb   = KnowledgeBase()

    def _load_excel(self):
        """Load enhanced database with parameter mappings"""
        df = pd.read_excel(self.path, engine="openpyxl")
        df["Valid start time"] = pd.to_datetime(df["Valid start time"])
        df["Transaction time"] = pd.to_datetime(df["Transaction time"])
        df["Patient"] = (
            df["First name"].str.title().str.strip() + " " +
            df["Last name"].str.title().str.strip()
        )
        return df

    def _flush(self):
        """Save database to Excel"""
        cols = list(self._PAT) + ["LOINC-NUM", "Value", "Unit",
                                  "Valid start time", "Transaction time"]
        # If we have the enhanced columns, include them
        if "Parameter_Name" in self.df.columns:
            cols.extend(["Parameter_Name", "Parameter_Type", "Corrected_Unit"])
        self.df[cols].to_excel(self.path, index=False)

    def get_latest_value_by_parameter(self, patient: str, parameter_type: str, query_time: datetime | None = None):
        """Get latest value for a parameter type (e.g., 'Gender', 'Hemoglobin-level')"""
        if 'Parameter_Type' not in self.df.columns:
            # Fallback to LOINC code if parameter mapping not available
            loinc_code = PARAM_TO_LOINC.get(parameter_type)
            if loinc_code:
                return self.get_latest_value_by_loinc(patient, loinc_code, query_time)
            return None, None
        
        df = self.df
        if query_time:
            df = df[df["Transaction time"] <= query_time]
        
        # Filter for the patient and parameter type
        m_patient_param = (df["Patient"].str.casefold() == patient.casefold()) & \
                         (df["Parameter_Type"] == parameter_type)
        
        df_patient = df[m_patient_param]
        
        if df_patient.empty:
            return None, None

        # For each valid time, find the latest transaction
        idx = df_patient.sort_values("Transaction time").groupby("Valid start time").tail(1).index

        # From these, find the one with the latest valid time
        latest_record = df.loc[idx].sort_values("Valid start time").tail(1)

        if not latest_record.empty:
            return latest_record["Value"].iloc[0], latest_record["Unit"].iloc[0]
        return None, None

    def get_latest_value_by_loinc(self, patient: str, loinc_code: str, query_time: datetime | None = None):
        """Get latest value for a LOINC code"""
        df = self.df
        if query_time:
            df = df[df["Transaction time"] <= query_time]
        
        # Filter for the patient and LOINC code
        m_patient_code = (df["Patient"].str.casefold() == patient.casefold()) & \
                         (df["LOINC-NUM"] == loinc_code)
        
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

    def get_patient_states(self, patient: str, query_time: datetime | None = None) -> dict:
        """Get all current patient states using parameter mapping"""
        states = {}
        
        # Gender
        gender, _ = self.get_latest_value_by_parameter(patient, 'Gender', query_time)
        states['Gender'] = gender

        # Hemoglobin
        hgb_level, _ = self.get_latest_value_by_parameter(patient, "Hemoglobin-level", query_time)
        states['Hemoglobin-level'] = hgb_level
        if hgb_level is not None and gender is not None:
            states['Hemoglobin-state'] = get_hemoglobin_state(hgb_level, gender)

        # WBC
        wbc_level, _ = self.get_latest_value_by_parameter(patient, "WBC-level", query_time)
        states['WBC-level'] = wbc_level

        # Hematological state
        if hgb_level is not None and wbc_level is not None and gender is not None:
            states['Hematological-state'] = get_hematological_state(hgb_level, wbc_level, gender)

        # Fever (Temperature)
        temp_val, _ = self.get_latest_value_by_parameter(patient, "Fever", query_time)
        states['Fever'] = temp_val

        # Chills  
        chills_val, _ = self.get_latest_value_by_parameter(patient, "Chills", query_time)
        states['Chills'] = chills_val

        # Skin-look
        skin_val, _ = self.get_latest_value_by_parameter(patient, "Skin-look", query_time)
        states['Skin-look'] = skin_val

        # Allergic-state
        allergic_val, _ = self.get_latest_value_by_parameter(patient, "Allergic-state", query_time)
        states['Allergic-state'] = allergic_val

        # Therapy
        therapy_val, _ = self.get_latest_value_by_parameter(patient, "Therapy", query_time)
        states['Therapy'] = therapy_val

        # Systemic toxicity
        systemic_toxicity = self.get_systemic_toxicity(patient, query_time)
        if systemic_toxicity:
            states['Systemic-Toxicity'] = systemic_toxicity

        return states

    def get_systemic_toxicity(self, patient: str, query_time: datetime | None = None) -> (str | None):
        """Calculate systemic toxicity grade"""
        # Check for Therapy=CCTG522
        therapy_val, _ = self.get_latest_value_by_parameter(patient, "Therapy", query_time)
        if therapy_val != "CCTG522":
            return None

        # Get all toxicity parameters
        temp_val, _ = self.get_latest_value_by_parameter(patient, "Fever", query_time)
        chills_val, _ = self.get_latest_value_by_parameter(patient, "Chills", query_time)
        skin_val, _ = self.get_latest_value_by_parameter(patient, "Skin-look", query_time)
        allergic_val, _ = self.get_latest_value_by_parameter(patient, "Allergic-state", query_time)

        # Calculate individual grades
        fever_grade = get_fever_grade(temp_val) if temp_val is not None else 0
        chills_grade = get_chills_grade(chills_val) if chills_val is not None else 0
        skin_grade = get_skin_look_grade(skin_val) if skin_val is not None else 0
        allergic_grade = get_allergic_state_grade(allergic_val) if allergic_val is not None else 0

        # Return maximum grade
        max_grade = max(fever_grade, chills_grade, skin_grade, allergic_grade)
        return f"GRADE {max_grade}" if max_grade > 0 else None

    def get_treatment_recommendation(self, patient: str, query_time: datetime | None = None) -> str:
        """Get treatment recommendation for patient"""
        states = self.get_patient_states(patient, query_time)
        
        gender = states.get('Gender')
        hemoglobin_state = states.get('Hemoglobin-state')
        hematological_state = states.get('Hematological-state')
        systemic_toxicity = states.get('Systemic-Toxicity')
        
        return get_treatment_recommendation(gender, hemoglobin_state, hematological_state, systemic_toxicity)

    def status(self) -> pd.DataFrame:
        """Get current status of all patients"""
        if 'Parameter_Type' in self.df.columns:
            idx = (self.df.sort_values("Valid start time")
                          .groupby(["Patient", "Parameter_Type"])
                          .tail(1).index)
            return self.df.loc[idx].sort_values(["Patient", "Parameter_Type"]).reset_index(drop=True)
        else:
            # Fallback to LOINC-based grouping
            idx = (self.df.sort_values("Valid start time")
                          .groupby(["Patient", "LOINC-NUM"])
                          .tail(1).index)
            return self.df.loc[idx].sort_values(["Patient", "LOINC-NUM"]).reset_index(drop=True)

# Helper functions for grade calculations
def get_fever_grade(temp_val):
    """Calculate fever grade from temperature"""
    if temp_val is None:
        return 0
    try:
        temp = float(temp_val)
        if temp < 38.5:
            return 1
        elif temp < 40.0:
            return 2
        else:
            return 3
    except:
        return 0

def get_chills_grade(chills_val):
    """Calculate chills grade"""
    if chills_val is None:
        return 0
    chills_str = str(chills_val).lower()
    if 'none' in chills_str:
        return 1
    elif 'shaking' in chills_str:
        return 2
    elif 'rigor' in chills_str:
        return 3
    return 0

def get_skin_look_grade(skin_val):
    """Calculate skin look grade"""
    if skin_val is None:
        return 0
    skin_str = str(skin_val).lower()
    if 'erythema' in skin_str:
        return 1
    elif 'vesiculation' in skin_str:
        return 2
    elif 'desquamation' in skin_str:
        return 3
    elif 'exfoliation' in skin_str:
        return 4
    return 0

def get_allergic_state_grade(allergic_val):
    """Calculate allergic state grade"""
    if allergic_val is None:
        return 0
    allergic_str = str(allergic_val).lower()
    if 'edema' in allergic_str:
        return 1
    elif 'bronchospasm' in allergic_str and 'severe' not in allergic_str:
        return 2
    elif 'severe-bronchospasm' in allergic_str:
        return 3
    elif 'anaphylactic' in allergic_str:
        return 4
    return 0

def get_hemoglobin_state(hgb_level, gender):
    """Calculate hemoglobin state based on level and gender"""
    if hgb_level is None or gender is None:
        return None
    
    try:
        hgb = float(hgb_level)
        gender_lower = str(gender).lower()
        
        if 'female' in gender_lower:
            if hgb < 8:
                return "Severe Anemia"
            elif hgb < 10:
                return "Moderate Anemia"
            elif hgb < 12:
                return "Mild Anemia"
            elif hgb < 14:
                return "Normal Hemoglobin"
            else:
                return "Polycytemia"
        else:  # male
            if hgb < 9:
                return "Severe Anemia"
            elif hgb < 11:
                return "Moderate Anemia"
            elif hgb < 13:
                return "Mild Anemia"
            elif hgb < 16:
                return "Normal Hemoglobin"
            else:
                return "Polyhemia"
    except:
        return None

def get_hematological_state(hgb_level, wbc_level, gender):
    """Calculate hematological state based on hemoglobin, WBC, and gender"""
    if hgb_level is None or wbc_level is None or gender is None:
        return None
    
    try:
        hgb = float(hgb_level)
        wbc = float(wbc_level)
        gender_lower = str(gender).lower()
        
        if 'female' in gender_lower:
            hgb_threshold = 12
        else:
            hgb_threshold = 13
            
        if hgb < hgb_threshold and wbc < 4000:
            return "Pancytopenia"
        elif hgb < hgb_threshold and 4000 <= wbc < 10000:
            return "Anemia"
        elif hgb < hgb_threshold and wbc >= 10000:
            return "Suspected Leukemia"
        elif hgb_threshold <= hgb < (14 if 'female' in gender_lower else 16) and wbc < 4000:
            return "Leukopenia"
        elif hgb_threshold <= hgb < (14 if 'female' in gender_lower else 16) and 4000 <= wbc < 10000:
            return "Normal"
        elif hgb_threshold <= hgb < (14 if 'female' in gender_lower else 16) and wbc >= 10000:
            return "Leukemoid reaction"
        else:
            return "Suspected Polycytemia Vera"
    except:
        return None

def get_treatment_recommendation(gender, hemoglobin_state, hematological_state, systemic_toxicity):
    """Get treatment recommendation based on states"""
    if not all([gender, hemoglobin_state, hematological_state, systemic_toxicity]):
        return "Insufficient data for treatment recommendation"
    
    # Treatment mappings
    treatments = {
        "male": {
            "Severe Anemia + Pancytopenia + GRADE 1": "Measure BP once a week",
            "Moderate Anemia + Anemia + GRADE 2": "Measure BP every 3 days\nGive aspirin 5g twice a week",
            "Mild Anemia + Suspected Leukemia + GRADE 3": "Measure BP every day\nGive aspirin 15g every day\nDiet consultation",
            "Normal Hemoglobin + Leukemoid reaction + GRADE 4": "Measure BP twice a day\nGive aspirin 15g every day\nExercise consultation\nDiet consultation",
            "Polyhemia + Suspected Polycytemia Vera + GRADE 4": "Measure BP every hour\nGive 1 gr magnesium every hour\nExercise consultation\nCall family"
        },
        "female": {
            "Severe Anemia + Pancytopenia + GRADE 1": "Measure BP every 3 days",
            "Moderate Anemia + Anemia + GRADE 2": "Measure BP every 3 days\nGive Celectone 2g twice a day for two days drug treatment",
            "Mild Anemia + Suspected Leukemia + GRADE 3": "Measure BP every day\nGive 1 gr magnesium every 3 hours\nDiet consultation",
            "Normal Hemoglobin + Leukemoid reaction + GRADE 4": "Measure BP twice a day\nGive 1 gr magnesium every hour\nExercise consultation\nDiet consultation",
            "Polyhemia + Suspected Polycytemia Vera + GRADE 4": "Measure BP every hour\nGive 1 gr magnesium every hour\nExercise consultation\nCall help"
        }
    }
    
    # Create treatment key
    treatment_key = f"{hemoglobin_state} + {hematological_state} + {systemic_toxicity}"
    
    gender_lower = str(gender).lower()
    gender_key = 'female' if 'female' in gender_lower else 'male'
    
    return treatments.get(gender_key, {}).get(treatment_key, "No specific treatment found")

if __name__ == "__main__":
    # Test the enhanced system
    db = EnhancedCDSSDatabase()
    
    print("=== Enhanced CDSS Database Test ===")
    print(f"Database loaded with {len(db.df)} records")
    
    # Test with a patient
    test_patient = "Eyal Rothman"
    states = db.get_patient_states(test_patient)
    print(f"\nPatient states for {test_patient}:")
    for key, value in states.items():
        print(f"  {key}: {value}")
    
    # Get treatment recommendation
    treatment = db.get_treatment_recommendation(test_patient)
    print(f"\nTreatment recommendation: {treatment}") 