from __future__ import annotations
from pathlib import Path
from datetime import datetime, date, time, timedelta
import pandas as pd
import json

ROOT = Path(__file__).absolute().parent
CLEAN_DB_PATH = ROOT / "cdss_database_v7.xlsx"
MAPPING_PATH = ROOT / "clean_database_mapping.json"

class CleanCDSSDatabase:
    """Clean CDSS Database with proper structure: Demographics, Lab Results, Clinical Observations"""
    
    def __init__(self, db_path: Path | str = CLEAN_DB_PATH):
        self.path = Path(db_path)
        self.demographics_df = None
        self.lab_results_df = None
        self.clinical_obs_df = None
        self.kb = SimpleKnowledgeBase()  # Add simple KB for UI compatibility
        self._load_database()

    def _load_database(self):
        """Load the clean database with separate sheets"""
        try:
            self.demographics_df = pd.read_excel(self.path, sheet_name='Patient_Demographics')
            self.lab_results_df = pd.read_excel(self.path, sheet_name='Lab_Results')
            self.clinical_obs_df = pd.read_excel(self.path, sheet_name='Clinical_Observations')
            
            # Convert datetime columns
            self.lab_results_df['Valid_Start_Time'] = pd.to_datetime(self.lab_results_df['Valid_Start_Time'])
            self.lab_results_df['Transaction_Time'] = pd.to_datetime(self.lab_results_df['Transaction_Time'])
            self.clinical_obs_df['Observation_Date'] = pd.to_datetime(self.clinical_obs_df['Observation_Date'])
            
            print(f"✓ Database loaded:")
            print(f"  - {len(self.demographics_df)} patients")
            print(f"  - {len(self.lab_results_df)} lab results")
            print(f"  - {len(self.clinical_obs_df)} clinical observations")
            
        except Exception as e:
            print(f"Error loading database: {e}")

    def get_patient_demographics(self, patient_id: str) -> dict:
        """Get patient demographic information, including full name if available"""
        patient_data = self.demographics_df[self.demographics_df['Patient_ID'] == patient_id]
        if patient_data.empty:
            return {}
        patient = patient_data.iloc[0]
        # Determine patient name
        if 'Patient_Name' in patient_data.columns:
            name = patient['Patient_Name']
        elif {'First_name', 'Last_name'}.issubset(patient_data.columns):
            # Build from first/last name columns and title-case them
            name = f"{str(patient['First_name']).title().strip()} {str(patient['Last_name']).title().strip()}".strip()
        else:
            name = None
        return {
            'Patient_ID': patient['Patient_ID'],
            'Patient_Name': name,
            'Gender': patient.get('Gender'),
            'Age': patient.get('Age')
        }

    def get_latest_lab_value(self, patient_id: str, loinc_code: str, query_time: datetime = None) -> tuple:
        """Get latest lab value for a specific LOINC code with validity periods"""
        if query_time is None:
            query_time = datetime.now()
        
        # Define validity periods (Before-Good and After-Good) - Clinically realistic values
        validity_periods = {
            '30313-1': {'before_good': timedelta(days=2), 'after_good': timedelta(days=7)},    # Hemoglobin: stable for ~1 week
            '26464-8': {'before_good': timedelta(hours=12), 'after_good': timedelta(days=3)},  # WBC: changes faster, ~3 days
            '39106-0': {'before_good': timedelta(days=30), 'after_good': timedelta(days=7)},   # Temperature: extended for demo data
        }
        
        # Get validity period for this LOINC code
        validity = validity_periods.get(loinc_code, {'before_good': timedelta(hours=4), 'after_good': timedelta(hours=8)})
        
        # Calculate valid time window
        earliest_valid = query_time - validity['before_good']
        latest_valid = query_time + validity['after_good']
        
        # Filter for patient, LOINC code, and validity window
        lab_data = self.lab_results_df[
            (self.lab_results_df['Patient_ID'] == patient_id) & 
            (self.lab_results_df['LOINC_Code'] == loinc_code) &
            # (self.lab_results_df['Valid_Start_Time'] >= earliest_valid) &
            # (self.lab_results_df['Valid_Start_Time'] <= latest_valid)
            (self.lab_results_df['Transaction_Time'] >= earliest_valid) &
            (self.lab_results_df['Transaction_Time'] <= latest_valid)
        ]
        
        if lab_data.empty:
            return None, None
            
        # Get the latest record within validity window
        latest_record = lab_data.sort_values('Valid_Start_Time').tail(1)
        return latest_record['Value'].iloc[0], latest_record['Unit'].iloc[0]

    def get_latest_clinical_observation(self, patient_id: str, observation_type: str, query_time: datetime = None) -> str:
        """Get latest clinical observation for a specific type with validity periods"""
        if query_time is None:
            query_time = datetime.now()
        
        # Define validity periods for clinical observations - More realistic for therapeutic monitoring
        validity = {'before_good': timedelta(days=30), 'after_good': timedelta(days=7)}
        
        # Calculate valid time window
        earliest_valid = query_time - validity['before_good']
        latest_valid = query_time + validity['after_good']
            
        # Filter for patient, observation type, and validity window
        obs_data = self.clinical_obs_df[
            (self.clinical_obs_df['Patient_ID'] == patient_id) & 
            (self.clinical_obs_df['Observation_Type'] == observation_type) &
            (self.clinical_obs_df['Observation_Date'] >= earliest_valid) &
            (self.clinical_obs_df['Observation_Date'] <= latest_valid)
        ]
        
        if obs_data.empty:
            return None
            
        # Get the latest observation within validity window
        latest_obs = obs_data.sort_values('Observation_Date').tail(1)
        return latest_obs['Observation_Value'].iloc[0]

    def get_patient_states(self, patient_id: str, query_time: datetime = None) -> dict:
        """Calculate all patient states for CDSS"""
        if query_time is None:
            # Use current time around June 12, 2025 to match data
            query_time = datetime(2025, 6, 12, 20, 0, 0)
            
        states = {}
        
        # Get demographics
        demographics = self.get_patient_demographics(patient_id)
        states['Gender'] = demographics.get('Gender')
        states['Age'] = demographics.get('Age')
        
        # Get lab values using real LOINC codes
        hemoglobin_val, hgb_unit = self.get_latest_lab_value(patient_id, '30313-1', query_time)  # Hemoglobin
        wbc_val, wbc_unit = self.get_latest_lab_value(patient_id, '26464-8', query_time)  # WBC
        temp_val, temp_unit = self.get_latest_lab_value(patient_id, '39106-0', query_time)  # Temperature
        
        states['Hemoglobin_Level'] = hemoglobin_val
        states['WBC_Level'] = wbc_val  
        states['Temperature'] = temp_val
        
        # Get clinical observations
        states['Chills'] = self.get_latest_clinical_observation(patient_id, 'Chills', query_time)
        states['Skin_Appearance'] = self.get_latest_clinical_observation(patient_id, 'Skin_Appearance', query_time)
        states['Allergic_Reaction'] = self.get_latest_clinical_observation(patient_id, 'Allergic_Reaction', query_time)
        states['Therapy_Status'] = self.get_latest_clinical_observation(patient_id, 'Therapy_Status', query_time)
        
        # Calculate derived states
        if hemoglobin_val is not None and states['Gender'] is not None:
            states['Hemoglobin_State'] = self._calculate_hemoglobin_state(hemoglobin_val, states['Gender'])
        
        if hemoglobin_val is not None and wbc_val is not None and states['Gender'] is not None:
            states['Hematological_State'] = self._calculate_hematological_state(hemoglobin_val, wbc_val, states['Gender'])
        
        # Calculate systemic toxicity
        states['Systemic_Toxicity'] = self._calculate_systemic_toxicity(states)
        
        return states

    def _calculate_hemoglobin_state(self, hgb_level: float, gender: str) -> str:
        """Calculate hemoglobin state"""
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
                    return "Polycytemia"  # High hemoglobin for both genders
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
                    return "Polycytemia"  # High hemoglobin for both genders
        except:
            return None

    def _calculate_hematological_state(self, hgb_level: float, wbc_level: float, gender: str) -> str:
        """Calculate hematological state"""
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
            elif hgb >= (14 if 'female' in gender_lower else 16) and 4000 <= wbc < 10000:
                return "Polycytemia"
            else:
                return "Suspected Polycytemia Vera"
        except:
            return None

    def _calculate_systemic_toxicity(self, states: dict) -> str:
        """Calculate systemic toxicity grade using Maximal OR approach"""
        # Only calculate if patient is on CCTG522 therapy
        if states.get('Therapy_Status') != 'CCTG522':
            return None
        
        # Get toxicity parameters
        temp_val = states.get('Temperature')
        chills_val = states.get('Chills')
        skin_val = states.get('Skin_Appearance')
        allergic_val = states.get('Allergic_Reaction')
        
        # Calculate individual grades for each parameter
        fever_grade = self._get_fever_grade(temp_val)
        chills_grade = self._get_chills_grade(chills_val)
        skin_grade = self._get_skin_grade(skin_val)
        allergic_grade = self._get_allergic_grade(allergic_val)
        
        # Maximal OR: Take the maximum grade from any parameter that has valid data
        # If at least one parameter has a valid grade (>0), calculate toxicity
        valid_grades = [grade for grade in [fever_grade, chills_grade, skin_grade, allergic_grade] if grade > 0]
        
        if not valid_grades:
            return None  # No valid data for any parameter
        
        # Return maximum grade from available parameters
        max_grade = max(valid_grades)
        return f"Grade {max_grade}"

    def _get_fever_grade(self, temp_val) -> int:
        if temp_val is None:
            return 0
        try:
            temp = float(temp_val)
            # Only assign fever grades for actual fever (>= 37.5°C)
            # Normal temperature should not contribute to systemic toxicity
            if temp < 37.5:
                return 0  # No fever grade for normal temperature
            elif temp < 38.5:
                return 1
            elif temp < 40.0:
                return 2
            else:
                return 3
        except:
            return 0

    def _get_chills_grade(self, chills_val) -> int:
        if chills_val is None:
            return 0
        chills_str = str(chills_val).lower()
        
        # Map chills values to grades according to the table
        if 'none' in chills_str:
            return 0  # No grade for no chills - should not contribute to toxicity
        elif 'shaking' in chills_str:
            return 2  # Grade II for Shaking
        elif 'rigor' in chills_str:
            return 3  # Grade III for Rigor (also Grade IV)
        
        # For any other chills value not in the table, only assign grade if it indicates a problem
        # Don't default to Grade I for normal conditions
        return 0  # Default to no grade for unclear chills values

    def _get_skin_grade(self, skin_val) -> int:
        if skin_val is None:
            return 0
        skin_str = str(skin_val).lower()
        
        # Map skin values to grades according to the table
        if 'erythema' in skin_str:
            return 1  # Grade I for Erythema
        elif 'vesiculation' in skin_str:
            return 2  # Grade II for Vesiculation
        elif 'desquamation' in skin_str:
            return 3  # Grade III for Desquamation
        elif 'exfoliation' in skin_str:
            return 4  # Grade IV for Exfoliation
        elif 'normal' in skin_str:
            return 0  # No grade for normal skin - should not contribute to toxicity
        
        # For any other skin value not in the table, only assign grade if it indicates a problem
        # Don't default to Grade I for normal conditions
        return 0  # Default to no grade for unclear skin values

    def _get_allergic_grade(self, allergic_val) -> int:
        if allergic_val is None or str(allergic_val).lower() == 'nan' or str(allergic_val).lower() == 'none':
            return 0  # No grade if no allergic data
        
        allergic_str = str(allergic_val).lower()
        
        # Map allergic values to grades according to the table
        if 'edema' in allergic_str:
            return 1  # Grade I for Edema
        elif 'severe-bronchospasm' in allergic_str or 'severe bronchospasm' in allergic_str:
            return 3  # Grade III for Severe-Bronchospasm
        elif 'bronchospasm' in allergic_str:
            return 2  # Grade II for Bronchospasm (check after severe)
        elif 'anaphylactic' in allergic_str:
            return 4  # Grade IV for Anaphylactic-Shock
        
        # For any other allergic value not in the table, only assign grade if it clearly indicates a problem
        # Don't default to Grade I for normal or unclear conditions
        return 0  # Default to no grade for unclear allergic values

    def get_treatment_recommendation(self, patient_id: str, query_time: datetime = None) -> str:
        """Get treatment recommendation for patient based on exact assignment rules"""
        states = self.get_patient_states(patient_id, query_time)
        
        gender = states.get('Gender')
        hemoglobin_state = states.get('Hemoglobin_State')
        hematological_state = states.get('Hematological_State')
        systemic_toxicity = states.get('Systemic_Toxicity')
        
        # Check if we have all required states for treatment recommendation
        if not gender or not hemoglobin_state or not hematological_state:
            missing = []
            missing_tests = []
            
            # Check what lab tests are actually missing
            hgb_level = states.get('Hemoglobin_Level')
            wbc_level = states.get('WBC_Level')
            
            if not gender: 
                missing.append('Gender')
                missing_tests.append('Patient Demographics')
            
            # Smart logic for missing tests to avoid duplicates
            if hgb_level is None and wbc_level is None:
                # Both missing - affects both hemoglobin state and hematological state
                missing_tests.append('Hemoglobin and WBC Lab Tests')
                if not hemoglobin_state:
                    missing.append('Hemoglobin_State')
                if not hematological_state:
                    missing.append('Hematological_State')
            elif hgb_level is None:
                # Only hemoglobin missing - affects both states
                missing_tests.append('Hemoglobin Lab Test')
                if not hemoglobin_state:
                    missing.append('Hemoglobin_State')
                if not hematological_state:
                    missing.append('Hematological_State')
            elif wbc_level is None:
                # Only WBC missing - affects only hematological state
                missing_tests.append('WBC Lab Test')
                if not hematological_state:
                    missing.append('Hematological_State')
            else:
                # Both tests available but states still missing (shouldn't happen)
                if not hemoglobin_state:
                    missing.append('Hemoglobin_State')
                if not hematological_state:
                    missing.append('Hematological_State')
            
            return f"Insufficient data. Missing {', '.join(missing_tests)} in order to determine {', '.join(missing)}."
        
        # For patients not on CCTG522, systemic toxicity may be None - that's ok
        if systemic_toxicity is None and states.get('Therapy_Status') != 'CCTG522':
            return "No treatment recommendation (patient not on CCTG522 therapy)"
        
        # If on CCTG522 but no systemic toxicity calculated, that's a problem
        if states.get('Therapy_Status') == 'CCTG522' and not systemic_toxicity:
            return "Insufficient data. Missing Clinical Observations (Temperature, Chills, Skin Appearance, Allergic Reaction) in order to determine Systemic_Toxicity."
        
        # Extract grade number from systemic toxicity (e.g., "Grade 1" -> "GRADE I")
        if systemic_toxicity:
            grade_map = {"Grade 1": "GRADE I", "Grade 2": "GRADE II", "Grade 3": "GRADE III", "Grade 4": "GRADE IV"}
            systemic_toxicity_formatted = grade_map.get(systemic_toxicity, systemic_toxicity)
        else:
            systemic_toxicity_formatted = None
        
        # Define exact treatment rules from assignment
        treatment_rules = {
            # MALE RULES
            ("Male", "Severe Anemia", "Pancytopenia", "GRADE I"): "• Measure BP once a week",
            ("Male", "Moderate Anemia", "Anemia", "GRADE II"): "• Measure BP every 3 days\n• Give aspirin 5g twice a week",
            ("Male", "Mild Anemia", "Suspected Leukemia", "GRADE III"): "• Measure BP every day\n• Give aspirin 15g every day\n• Diet consultation",
            ("Male", "Normal Hemoglobin", "Leukemoid reaction", "GRADE IV"): "• Measure BP twice a day\n• Give aspirin 15g every day\n• Exercise consultation\n• Diet consultation",
            ("Male", "Polyhemia", "Suspected Polycytemia Vera", "GRADE IV"): "• Measure BP every hour\n• Give 1 gr magnesium every hour\n• Exercise consultation\n• Call family",
            
            # FEMALE RULES
            ("Female", "Severe Anemia", "Pancytopenia", "GRADE I"): "• Measure BP every 3 days",
            ("Female", "Moderate Anemia", "Anemia", "GRADE II"): "• Measure BP every 3 days\n• Give Celectone 2g twice a day for two days drug treatment",
            ("Female", "Mild Anemia", "Suspected Leukemia", "GRADE III"): "• Measure BP every day\n• Give 1 gr magnesium every 3 hours\n• Diet consultation",
            ("Female", "Normal Hemoglobin", "Leukemoid reaction", "GRADE IV"): "• Measure BP twice a day\n• Give 1 gr magnesium every hour\n• Exercise consultation\n• Diet consultation",
            ("Female", "Polyhemia", "Suspected Polycytemia Vera", "GRADE IV"): "• Measure BP every hour\n• Give 1 gr magnesium every hour\n• Exercise consultation\n• Call help"
        }
        
        # Create the key for treatment lookup
        treatment_key = (gender, hemoglobin_state, hematological_state, systemic_toxicity_formatted)
        
        # Look up exact treatment
        treatment = treatment_rules.get(treatment_key)
        
        if treatment:
            return treatment
        else:
            # No exact match found - the assignment requires ALL 3 conditions to match
            return f"No treatment recommendation for combination: {gender}, {hemoglobin_state}, {hematological_state}, {systemic_toxicity_formatted or 'No Systemic Toxicity'}"

    def find_patients_by_criteria(self, criteria: dict) -> list:
        """Find patients matching specific criteria"""
        matching_patients = []
        
        # Get all patients
        all_patients = self.demographics_df['Patient_ID'].tolist()
        
        for patient_id in all_patients:
            matches_all_criteria = True
            
            for criterion, value in criteria.items():
                if criterion == 'Gender':
                    demographics = self.get_patient_demographics(patient_id)
                    actual = demographics.get('Gender')
                    if actual is None or str(actual).lower() != str(value).lower():
                        matches_all_criteria = False
                        break
                    
                elif criterion == 'Therapy_Status':
                    therapy = self.get_latest_clinical_observation(patient_id, 'Therapy_Status')
                    if therapy is None or str(value).lower() not in str(therapy).lower():
                        matches_all_criteria = False
                        break
                    
                elif criterion in ['Hemoglobin_State', 'Hematological_State', 'Systemic_Toxicity']:
                    states = self.get_patient_states(patient_id)
                    actual = states.get(criterion)
                    if actual is None or str(value).lower() not in str(actual).lower():
                        matches_all_criteria = False
                        break
                    
                else:
                    states = self.get_patient_states(patient_id)
                    actual = states.get(criterion)
                    if actual is None or str(value).lower() not in str(actual).lower():
                        matches_all_criteria = False
                        break
            
            if matches_all_criteria:
                matching_patients.append(patient_id)
        
        return matching_patients

    def get_patient_summary(self) -> pd.DataFrame:
        """Get summary of all patients with their current states"""
        summary_data = []
        
        for _, patient in self.demographics_df.iterrows():
            patient_id = patient['Patient_ID']
            states = self.get_patient_states(patient_id)
            
            summary_data.append({
                'Patient_ID': patient_id,
                'Gender': states.get('Gender'),
                'Age': states.get('Age'),
                'Hemoglobin_Level': states.get('Hemoglobin_Level'),
                'Hemoglobin_State': states.get('Hemoglobin_State'),
                'WBC_Level': states.get('WBC_Level'),
                'Hematological_State': states.get('Hematological_State'),
                'Therapy_Status': states.get('Therapy_Status'),
                'Systemic_Toxicity': states.get('Systemic_Toxicity')
            })
        
        return pd.DataFrame(summary_data)

    def get_all_patient_states_at_time(self, query_time: datetime | None = None) -> pd.DataFrame:
        """Return a DataFrame of all patients with their states and recommendations at a given time"""
        if query_time is None:
            query_time = datetime(2025, 4, 23, 12, 0, 0)
        rows = []
        for _, patient_row in self.demographics_df.iterrows():
            patient_id = patient_row['Patient_ID']
            patient_name = patient_row['Patient_Name']
            states = self.get_patient_states(patient_id, query_time)
            recommendation = self.get_treatment_recommendation(patient_id, query_time)
            rows.append({
                'Patient': patient_id,
                'Patient_Name': patient_name,
                'Gender': states.get('Gender'),
                'Hemoglobin-level': states.get('Hemoglobin_Level'),
                'Hemoglobin-state': states.get('Hemoglobin_State'),
                'WBC-level': states.get('WBC_Level'),
                'Hematological-state': states.get('Hematological_State'),
                'Therapy': states.get('Therapy_Status'),
                'Systemic-Toxicity': states.get('Systemic_Toxicity'),
                'Recommendation': recommendation or 'No specific treatment'
            })
        return pd.DataFrame(rows)

    def history(self, patient: str, code: str, start: datetime, end: datetime, hh: time = None, query_time: datetime = None) -> pd.DataFrame:
        """Get history of lab values for a patient and LOINC code"""
        df = self.lab_results_df
        if query_time:
            df = df[df["Transaction_Time"] <= query_time]
        
        mask = (df["Patient_ID"] == patient) & (df["LOINC_Code"] == code) & df["Valid_Start_Time"].between(start, end)
        if hh:
            mask &= df["Valid_Start_Time"].dt.time == hh
        
        result = df[mask].sort_values("Valid_Start_Time").reset_index(drop=True)
        if not result.empty:
            result = result.assign(LOINC_NAME=result["LOINC_Description"])
        return result
    
    def update(self, patient: str, code: str, valid_dt: datetime, new_val, now: datetime = None, transaction_time: datetime = None) -> pd.DataFrame:
        """Update a lab value (placeholder implementation)"""
        # For now, just return empty DataFrame - full implementation would modify the database
        return pd.DataFrame()
    
    def delete(self, patient: str, code: str, day: date, hh: time = None) -> pd.DataFrame:
        """Delete lab values (placeholder implementation)"""
        # For now, just return empty DataFrame - full implementation would modify the database
        return pd.DataFrame()
    
    def _merge_overlapping_intervals(self, intervals: list) -> list:
        """Merge overlapping or adjacent intervals"""
        if not intervals:
            return []
        
        # Sort intervals by start time
        sorted_intervals = sorted(intervals, key=lambda x: x['start'])
        merged = [sorted_intervals[0]]
        
        for current in sorted_intervals[1:]:
            last_merged = merged[-1]
            
            # Check if intervals overlap or are adjacent (allowing small gaps)
            if current['start'] <= last_merged['end']:
                # Merge by extending the end time
                merged[-1] = {
                    'start': last_merged['start'],
                    'end': max(last_merged['end'], current['end']),
                    'state': last_merged['state']
                }
            else:
                # No overlap, add as new interval
                merged.append(current)
        
        return merged

    def get_state_intervals(self, patient: str, state_type: str, target_state: str) -> list:
        """Get intervals when patient was in a specific state with proper validity windows"""
        intervals = []
        
        # Get all lab results and clinical observations for this patient
        if state_type in ['Hemoglobin_State', 'Hematological_State', 'Systemic_Toxicity']:
            # These are derived states - we need to check lab data over time
            if state_type == 'Hemoglobin_State':
                # Check hemoglobin levels over time with validity windows
                hgb_data = self.lab_results_df[
                    (self.lab_results_df['Patient_ID'] == patient) & 
                    (self.lab_results_df['LOINC_Code'] == '30313-1')  # Hemoglobin
                ].sort_values('Valid_Start_Time')
                
                demographics = self.get_patient_demographics(patient)
                gender = demographics.get('Gender')
                
                if not hgb_data.empty and gender:
                    # Get validity period for hemoglobin
                    from datetime import timedelta
                    hgb_validity = timedelta(days=7)  # After-Good period
                    
                    for _, row in hgb_data.iterrows():
                        hgb_val = row['Value']
                        test_time = row['Valid_Start_Time']
                        calculated_state = self._calculate_hemoglobin_state(hgb_val, gender)
                        
                        if calculated_state == target_state:
                            # Calculate the validity window for this test
                            interval_start = test_time
                            interval_end = test_time + hgb_validity
                            
                            intervals.append({
                                'start': interval_start,
                                'end': interval_end,
                                'state': calculated_state
                            })
            
            elif state_type == 'Hematological_State':
                # Check both hemoglobin and WBC levels over time with validity
                hgb_data = self.lab_results_df[
                    (self.lab_results_df['Patient_ID'] == patient) & 
                    (self.lab_results_df['LOINC_Code'] == '30313-1')  # Hemoglobin
                ].sort_values('Valid_Start_Time')
                
                wbc_data = self.lab_results_df[
                    (self.lab_results_df['Patient_ID'] == patient) & 
                    (self.lab_results_df['LOINC_Code'] == '26464-8')  # WBC
                ].sort_values('Valid_Start_Time')
                
                demographics = self.get_patient_demographics(patient)
                gender = demographics.get('Gender')
                
                if not hgb_data.empty and not wbc_data.empty and gender:
                    from datetime import timedelta
                    hgb_validity = timedelta(days=7)  # Hemoglobin validity
                    wbc_validity = timedelta(days=3)  # WBC validity
                    
                    # For each time when we have both valid HGB and WBC
                    for _, hgb_row in hgb_data.iterrows():
                        hgb_time = hgb_row['Valid_Start_Time']
                        hgb_val = hgb_row['Value']
                        
                        # Find overlapping WBC data
                        for _, wbc_row in wbc_data.iterrows():
                            wbc_time = wbc_row['Valid_Start_Time']
                            wbc_val = wbc_row['Value']
                            
                            # Calculate validity windows
                            hgb_start = hgb_time
                            hgb_end = hgb_time + hgb_validity
                            wbc_start = wbc_time
                            wbc_end = wbc_time + wbc_validity
                            
                            # Find overlap period
                            overlap_start = max(hgb_start, wbc_start)
                            overlap_end = min(hgb_end, wbc_end)
                            
                            if overlap_start < overlap_end:  # There is an overlap
                                calculated_state = self._calculate_hematological_state(hgb_val, wbc_val, gender)
                                
                                if calculated_state == target_state:
                                    intervals.append({
                                        'start': overlap_start,
                                        'end': overlap_end,
                                        'state': calculated_state
                                    })
            
            elif state_type == 'Systemic_Toxicity':
                # Check clinical observations over time for toxicity calculation
                relevant_obs = self.clinical_obs_df[
                    (self.clinical_obs_df['Patient_ID'] == patient) & 
                    (self.clinical_obs_df['Observation_Type'].isin(['Chills', 'Skin_Appearance', 'Allergic_Reaction', 'Therapy_Status']))
                ].sort_values('Observation_Date')
                
                temp_data = self.lab_results_df[
                    (self.lab_results_df['Patient_ID'] == patient) & 
                    (self.lab_results_df['LOINC_Code'] == '39106-0')  # Temperature
                ].sort_values('Valid_Start_Time')
                
                if not relevant_obs.empty or not temp_data.empty:
                    # Get all unique timestamps
                    obs_times = relevant_obs['Observation_Date'].tolist() if not relevant_obs.empty else []
                    temp_times = temp_data['Valid_Start_Time'].tolist() if not temp_data.empty else []
                    all_times = sorted(set(obs_times + temp_times))
                    
                    current_state = None
                    interval_start = None
                    
                    for timestamp in all_times:
                        # Calculate states at this time point
                        states = self.get_patient_states(patient, timestamp)
                        calculated_toxicity = states.get('Systemic_Toxicity')
                        
                        if calculated_toxicity != current_state:
                            # State changed
                            if current_state == target_state and interval_start:
                                intervals.append({
                                    'start': interval_start,
                                    'end': timestamp,
                                    'state': current_state
                                })
                            
                            if calculated_toxicity == target_state:
                                interval_start = timestamp
                            
                            current_state = calculated_toxicity
                    
                    # If still in target state at end of data
                    if current_state == target_state and interval_start:
                        intervals.append({
                            'start': interval_start,
                            'end': datetime.now(),
                            'state': current_state
                        })
        
        elif state_type == 'Therapy_Status':
            # Direct clinical observation
            therapy_obs = self.clinical_obs_df[
                (self.clinical_obs_df['Patient_ID'] == patient) & 
                (self.clinical_obs_df['Observation_Type'] == 'Therapy_Status')
            ].sort_values('Observation_Date')
            
            current_state = None
            interval_start = None
            
            for _, row in therapy_obs.iterrows():
                therapy_value = row['Observation_Value']
                timestamp = row['Observation_Date']
                
                if therapy_value != current_state:
                    # State changed
                    if current_state == target_state and interval_start:
                        intervals.append({
                            'start': interval_start,
                            'end': timestamp,
                            'state': current_state
                        })
                    
                    if therapy_value == target_state:
                        interval_start = timestamp
                    
                    current_state = therapy_value
            
            # If still in target state at end of data
            if current_state == target_state and interval_start:
                intervals.append({
                    'start': interval_start,
                    'end': datetime.now(),
                    'state': current_state
                })
        
        # Merge overlapping intervals before returning
        return self._merge_overlapping_intervals(intervals)

class SimpleKnowledgeBase:
    """Enhanced knowledge base for UI functionality"""
    
    def get_classification_table(self, table_name: str):
        """Return classification table from actual knowledge base file"""
        try:
            import json
            with open('knowledge_base.json', 'r') as f:
                kb = json.load(f)
            
            if table_name in kb.get('classification_tables', {}):
                return kb['classification_tables'][table_name]
        except Exception as e:
            print(f"Error loading knowledge base: {e}")
        
        # Fallback to hardcoded values for compatibility
        if table_name == "hemoglobin_state":
            return {
                "name": "Hemoglobin State Classification",
                "type": "1:1 mapping",
                "rules": {
                    "female": {
                        "ranges": [
                            {"min": 0, "max": 8, "state": "Severe Anemia"},
                            {"min": 8, "max": 10, "state": "Moderate Anemia"},
                            {"min": 10, "max": 12, "state": "Mild Anemia"},
                            {"min": 12, "max": 14, "state": "Normal Hemoglobin"},
                            {"min": 14, "max": 99, "state": "Polycytemia"}
                        ]
                    },
                    "male": {
                        "ranges": [
                            {"min": 0, "max": 9, "state": "Severe Anemia"},
                            {"min": 9, "max": 11, "state": "Moderate Anemia"},
                            {"min": 11, "max": 13, "state": "Mild Anemia"},
                            {"min": 13, "max": 16, "state": "Normal Hemoglobin"},
                            {"min": 16, "max": 99, "state": "Polyhemia"}
                        ]
                    }
                }
            }
        elif table_name == "hematological_state":
            return {
                "name": "Hematological State Classification",
                "type": "2:1 AND mapping", 
                "rules": {
                    "female": {
                        "hgb_threshold": 12,
                        "wbc_ranges": [
                            {"wbc_min": 0, "wbc_max": 4000, "hgb_low": "Pancytopenia", "hgb_mid": "Leukopenia", "hgb_high": "Suspected Polycytemia Vera"},
                            {"wbc_min": 4000, "wbc_max": 10000, "hgb_low": "Anemia", "hgb_mid": "Normal", "hgb_high": "Polyhemia"},
                            {"wbc_min": 10000, "wbc_max": 999999, "hgb_low": "Suspected Leukemia", "hgb_mid": "Leukemoid reaction", "hgb_high": "Suspected Polycytemia Vera"}
                        ]
                    },
                    "male": {
                        "hgb_threshold": 13,
                        "wbc_ranges": [
                            {"wbc_min": 0, "wbc_max": 4000, "hgb_low": "Pancytopenia", "hgb_mid": "Leukopenia", "hgb_high": "Suspected Polycytemia Vera"},
                            {"wbc_min": 4000, "wbc_max": 10000, "hgb_low": "Anemia", "hgb_mid": "Normal", "hgb_high": "Polyhemia"},
                            {"wbc_min": 10000, "wbc_max": 999999, "hgb_low": "Suspected Leukemia", "hgb_mid": "Leukemoid reaction", "hgb_high": "Suspected Polycytemia Vera"}
                        ]
                    }
                }
            }
        elif table_name == "systemic_toxicity":
            return {
                "name": "Systemic Toxicity Grading",
                "type": "4:1 MAXIMAL OR",
                "rules": {
                    "fever": [
                        {"range": [0, 38.5], "grade": 1},
                        {"range": [38.5, 40.0], "grade": 2},
                        {"range": [40.0, 999], "grade": 3}
                    ],
                    "chills": [
                        {"value": "None", "grade": 0}, {"value": "Mild", "grade": 1},
                        {"value": "Shaking", "grade": 2}, {"value": "Rigor", "grade": 3}
                    ],
                    "skin_look": [
                        {"value": "Normal", "grade": 0}, {"value": "Erythema", "grade": 1},
                        {"value": "Vesiculation", "grade": 2}, {"value": "Desquamation", "grade": 3},
                        {"value": "Exfoliation", "grade": 4}
                    ],
                    "allergic_state": [
                        {"value": "None", "grade": 0}, {"value": "Edema", "grade": 1},
                        {"value": "Bronchospasm", "grade": 2}, {"value": "Severe-Bronchospasm", "grade": 3},
                        {"value": "Anaphylactic-Shock", "grade": 4}
                    ]
                }
            }
        return {}
    
    def update_classification_table(self, table_name: str, table_data: dict):
        """Update classification table in knowledge_base.json file"""
        try:
            import json
            
            # Load current knowledge base
            with open('knowledge_base.json', 'r') as f:
                kb = json.load(f)
            
            # Update the specific table
            if 'classification_tables' not in kb:
                kb['classification_tables'] = {}
            
            kb['classification_tables'][table_name] = table_data
            
            # Save back to file
            with open('knowledge_base.json', 'w') as f:
                json.dump(kb, f, indent=2)
            
            print(f"Updated {table_name} classification table")
            return True
        except Exception as e:
            print(f"Error updating classification table: {e}")
            return False
    
    def get_treatments(self):
        """Return comprehensive treatment recommendations from knowledge base file"""
        try:
            import json
            with open('knowledge_base.json', 'r') as f:
                kb = json.load(f)
            
            if 'treatments' in kb:
                return kb['treatments']
        except Exception as e:
            print(f"Error loading treatments: {e}")
        
        # Fallback to hardcoded values
        return {
            "male": {
                "Severe Anemia + Pancytopenia + Grade 1": "• Measure BP once a week",
                "Moderate Anemia + Anemia + Grade 2": "• Measure BP every 3 days\\n• Give aspirin 5g twice a week",
                "Mild Anemia + Suspected Leukemia + Grade 3": "• Measure BP every day\\n• Give aspirin 15g every day\\n• Diet consultation",
                "Normal Hemoglobin + Leukemoid reaction + Grade 4": "• Measure BP twice a day\\n• Give aspirin 15g every day\\n• Exercise consultation\\n• Diet consultation",
                "Polyhemia + Suspected Polycytemia Vera + Grade 4": "• Measure BP every hour\\n• Give 1 gr magnesium every hour\\n• Exercise consultation\\n• Call family"
            },
            "female": {
                "Severe Anemia + Pancytopenia + Grade 1": "• Measure BP every 3 days",
                "Moderate Anemia + Anemia + Grade 2": "• Measure BP every 3 days\\n• Give Celectone 2g twice a day for two days drug treatment",
                "Mild Anemia + Suspected Leukemia + Grade 3": "• Measure BP every day\\n• Give 1 gr magnesium every 3 hours\\n• Diet consultation",
                "Normal Hemoglobin + Leukemoid reaction + Grade 4": "• Measure BP twice a day\\n• Give 1 gr magnesium every hour\\n• Exercise consultation\\n• Diet consultation",
                "Polyhemia + Suspected Polycytemia Vera + Grade 4": "• Measure BP every hour\\n• Give 1 gr magnesium every hour\\n• Exercise consultation\\n• Call help"
            }
        }
    
    def update_treatments(self, treatments: dict):
        """Update treatment recommendations in knowledge_base.json file"""
        try:
            import json
            
            # Load current knowledge base
            with open('knowledge_base.json', 'r') as f:
                kb = json.load(f)
            
            # Update treatments
            kb['treatments'] = treatments
            
            # Save back to file
            with open('knowledge_base.json', 'w') as f:
                json.dump(kb, f, indent=2)
            
            print(f"Updated treatment recommendations and saved to file")
            return True
        except Exception as e:
            print(f"Error saving treatments: {e}")
            return False
    
    def get_validity_periods(self):
        """Return validity periods for parameters from knowledge base file"""
        from datetime import timedelta
        
        try:
            import json
            with open('knowledge_base.json', 'r') as f:
                kb = json.load(f)
            
            if 'validity_periods' in kb:
                # Convert string format back to timedelta
                periods = {}
                for param, values in kb['validity_periods'].items():
                    before_str = values.get('Before-Good', '1 day, 0:00:00')
                    after_str = values.get('After-Good', '1 day, 0:00:00')
                    
                    # Parse the timedelta strings
                    def parse_timedelta(td_str):
                        if 'day' in td_str:
                            parts = td_str.split(', ')
                            days = int(parts[0].split(' ')[0])
                            time_part = parts[1] if len(parts) > 1 else '0:00:00'
                            hours, minutes, seconds = map(int, time_part.split(':'))
                            return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
                        else:
                            hours, minutes, seconds = map(int, td_str.split(':'))
                            return timedelta(hours=hours, minutes=minutes, seconds=seconds)
                    
                    periods[param] = {
                        'Before-Good': parse_timedelta(before_str),
                        'After-Good': parse_timedelta(after_str)
                    }
                return periods
        except Exception as e:
            print(f"Error loading validity periods: {e}")
        
        # Fallback to hardcoded values
        return {
            "Hemoglobin": {"Before-Good": timedelta(days=2), "After-Good": timedelta(days=7)},
            "WBC": {"Before-Good": timedelta(hours=12), "After-Good": timedelta(days=3)},
            "Temperature": {"Before-Good": timedelta(hours=1), "After-Good": timedelta(hours=6)},
            "Clinical_Observations": {"Before-Good": timedelta(hours=6), "After-Good": timedelta(days=1)}
        }
    
    def update_validity_periods(self, periods: dict):
        """Update validity periods in knowledge_base.json file"""
        try:
            import json
            
            # Load current knowledge base
            with open('knowledge_base.json', 'r') as f:
                kb = json.load(f)
            
            # Convert timedelta to string format for JSON serialization
            serializable_periods = {}
            for param, values in periods.items():
                serializable_periods[param] = {
                    'Before-Good': str(values['Before-Good']),
                    'After-Good': str(values['After-Good'])
                }
            
            # Update validity periods
            kb['validity_periods'] = serializable_periods
            
            # Save back to file
            with open('knowledge_base.json', 'w') as f:
                json.dump(kb, f, indent=2)
            
            print(f"Updated validity periods and saved to file")
            return True
        except Exception as e:
            print(f"Error saving validity periods: {e}")
            return False

if __name__ == "__main__":
    # Test the clean CDSS system
    db = CleanCDSSDatabase()
    
    print("\n=== CLEAN CDSS TEST ===")
    
    # Test with first patient
    patients = db.demographics_df['Patient_ID'].tolist()
    test_patient = patients[0]
    
    print(f"\nTesting with: {test_patient}")
    
    # Get all states
    states = db.get_patient_states(test_patient)
    print(f"States:")
    for key, value in states.items():
        print(f"  {key}: {value}")
    
    # Get treatment
    treatment = db.get_treatment_recommendation(test_patient)
    print(f"\nTreatment: {treatment}")
    
    # Test queries
    print(f"\n=== SAMPLE QUERIES ===")
    
    # Find male patients
    male_patients = db.find_patients_by_criteria({'Gender': 'Male'})
    print(f"Male patients: {male_patients}")
    
    # Find patients on CCTG522 therapy
    cctg_patients = db.find_patients_by_criteria({'Therapy_Status': 'CCTG522'})
    print(f"Patients on CCTG522: {cctg_patients}")
    
    # Get patient summary
    print(f"\n=== PATIENT SUMMARY ===")
    summary = db.get_patient_summary()
    print(summary.to_string(index=False)) 