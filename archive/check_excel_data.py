import pandas as pd

print("🔍 Checking Excel data...")

# Read the Excel file
excel_path = "clean_cdss_database_enhanced.xlsx"

# Read Clinical Observations sheet
clinical_obs_df = pd.read_excel(excel_path, sheet_name='Clinical_Observations')

print(f"Clinical observations from Excel: {len(clinical_obs_df)} records")
print(f"Columns: {clinical_obs_df.columns.tolist()}")

# Check allergic data
allergic_data = clinical_obs_df[clinical_obs_df['Observation_Type'] == 'Allergic_Reaction']
print(f"\nAllergic reaction observations in Excel: {len(allergic_data)}")

print("\nSample allergic observations from Excel:")
print(allergic_data[['Patient_ID', 'Observation_Value']].head(10))

print("\nUnique allergic values in Excel:")
print(allergic_data['Observation_Value'].value_counts())

# Check for a specific patient
test_patient_data = clinical_obs_df[
    (clinical_obs_df['Patient_ID'] == 'Male_Mild_Leukemia_G3') & 
    (clinical_obs_df['Observation_Type'] == 'Allergic_Reaction')
]
print(f"\nAllergic data for Male_Mild_Leukemia_G3:")
print(test_patient_data[['Observation_Value', 'Observation_Date']])

# Also check the SQLite for comparison
import sqlite3
print("\n=== Comparison with SQLite ===")
conn = sqlite3.connect('clean_cdss.db')
sqlite_allergic = pd.read_sql(
    "SELECT Patient_ID, Observation_Value FROM Clinical_Observations WHERE Observation_Type='Allergic_Reaction' AND Patient_ID='Male_Mild_Leukemia_G3' LIMIT 5", 
    conn
)
print("SQLite allergic data for Male_Mild_Leukemia_G3:")
print(sqlite_allergic)
conn.close() 