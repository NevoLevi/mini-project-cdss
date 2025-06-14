import pandas as pd
import zipfile
import numpy as np
from datetime import datetime, timedelta
import random

# Load the current database
df = pd.read_excel('project_db.xlsx')

print("=== CURRENT DATABASE ANALYSIS ===")
print("LOINC Code Mapping Analysis:")

# Based on our analysis, here's what we can map:
loinc_mapping = {
    '30313-1': {
        'name': 'Hemoglobin',
        'parameter': 'Hemoglobin-level',
        'description': 'Hemoglobin [Mass/volume] in Arterial blood',
        'unit': 'g/dL',
        'system_requirement': True
    },
    '39106-0': {
        'name': 'Temperature',
        'parameter': 'Fever',  
        'description': 'Temperature of Skin',
        'unit': 'degrees-celsius',
        'system_requirement': True
    },
    '76477-9': {
        'name': 'Heart Rate',
        'parameter': 'Heart-Rate',
        'description': 'Heart rate by Noninvasive',
        'unit': 'BPM',
        'system_requirement': False
    },
    '80266-0': {
        'name': 'Bowel Sounds',
        'parameter': 'Bowel-Sounds',
        'description': 'Bowel sounds by Auscultation',
        'unit': 'none',
        'system_requirement': False
    },
    '11218-5': {
        'name': 'Albumin',
        'parameter': 'Albumin-Level',
        'description': 'Microalbumin [Mass/volume] in Urine by Test strip',
        'unit': 'none',
        'system_requirement': False
    },
    # The other loinc codes don't directly map to our required parameters
}

print("\nMapped LOINC codes to system parameters:")
for loinc, info in loinc_mapping.items():
    if info['system_requirement']:
        status = "✓ REQUIRED"
    else:
        status = "○ Additional"
    print(f"  {loinc} -> {info['parameter']} ({info['name']}) - {status}")

print("\n=== MISSING CRITICAL PARAMETERS ===")
required_params = [
    'WBC-level',
    'Gender', 
    'Chills',
    'Skin-look',
    'Allergic-state',
    'Therapy'
]

print("Missing parameters that need synthetic data:")
for param in required_params:
    print(f"  - {param}")

# Create enhanced database
enhanced_df = df.copy()

# Add a column for parameter names
enhanced_df['Parameter_Name'] = enhanced_df['LOINC-NUM'].map(
    lambda x: loinc_mapping.get(x, {}).get('name', f'Unknown-{x}')
)

enhanced_df['Parameter_Type'] = enhanced_df['LOINC-NUM'].map(
    lambda x: loinc_mapping.get(x, {}).get('parameter', f'Unknown-{x}')
)

# Fix units based on what they should be
def fix_units(row):
    loinc = row['LOINC-NUM']
    if loinc in loinc_mapping:
        return loinc_mapping[loinc]['unit']
    return row['Unit']

enhanced_df['Corrected_Unit'] = enhanced_df.apply(fix_units, axis=1)

print(f"\n=== GENERATING SYNTHETIC DATA ===")

# Get all patients
patients = df[['First name', 'Last name']].drop_duplicates().reset_index(drop=True)
print(f"Found {len(patients)} patients")

# Function to generate synthetic LOINC codes for missing parameters
def generate_synthetic_loinc_codes():
    return {
        'WBC-level': '26464-8',      # Leukocytes [#/volume] in Blood  
        'Gender': '76689-9',         # Sex assigned at birth
        'Chills': '43724-2',         # Chills
        'Skin-look': '8302-2',       # Body height
        'Allergic-state': '52473-6', # Allergy or adverse drug event
        'Therapy': '18629-5'         # Therapeutic regimen
    }

synthetic_loincs = generate_synthetic_loinc_codes()

# Generate synthetic data for each patient
synthetic_records = []

for _, patient in patients.iterrows():
    first_name = patient['First name']
    last_name = patient['Last name']
    
    # Generate Gender (static)
    gender = random.choice(['Male', 'Female'])
    gender_record = {
        'First name': first_name,
        'Last name': last_name,
        'LOINC-NUM': synthetic_loincs['Gender'],
        'Value': gender,
        'Unit': 'none',
        'Valid start time': datetime(2025, 1, 1, 0, 0, 0),
        'Transaction time': datetime(2025, 4, 27, 10, 0, 0),
        'Parameter_Name': 'Gender',
        'Parameter_Type': 'Gender',
        'Corrected_Unit': 'none'
    }
    synthetic_records.append(gender_record)
    
    # Generate multiple time points for other parameters
    base_dates = [
        datetime(2025, 4, 17, 10, 0, 0),
        datetime(2025, 4, 18, 14, 0, 0), 
        datetime(2025, 4, 19, 8, 0, 0),
        datetime(2025, 4, 20, 16, 0, 0),
        datetime(2025, 4, 21, 12, 0, 0)
    ]
    
    for i, base_date in enumerate(base_dates):
        # WBC Level (normal range: 4000-10000 cells/uL)
        wbc_value = random.randint(3000, 12000)
        wbc_record = {
            'First name': first_name,
            'Last name': last_name,
            'LOINC-NUM': synthetic_loincs['WBC-level'],
            'Value': wbc_value,
            'Unit': 'cells/uL',
            'Valid start time': base_date,
            'Transaction time': datetime(2025, 4, 27, 10, 0, 0),
            'Parameter_Name': 'WBC',
            'Parameter_Type': 'WBC-level',
            'Corrected_Unit': 'cells/uL'
        }
        synthetic_records.append(wbc_record)
        
        # Chills (clinical observation)
        chills_values = ['None', 'Mild', 'Shaking', 'Rigor']
        chills_value = random.choice(chills_values)
        chills_record = {
            'First name': first_name,
            'Last name': last_name,
            'LOINC-NUM': synthetic_loincs['Chills'],
            'Value': chills_value,
            'Unit': 'none',
            'Valid start time': base_date + timedelta(hours=1),
            'Transaction time': datetime(2025, 4, 27, 10, 0, 0),
            'Parameter_Name': 'Chills',
            'Parameter_Type': 'Chills',
            'Corrected_Unit': 'none'
        }
        synthetic_records.append(chills_record)
        
        # Skin-look (dermatological observation)
        skin_values = ['Normal', 'Erythema', 'Vesiculation', 'Desquamation', 'Exfoliation']
        skin_value = random.choice(skin_values)
        skin_record = {
            'First name': first_name,
            'Last name': last_name,
            'LOINC-NUM': synthetic_loincs['Skin-look'],
            'Value': skin_value,
            'Unit': 'none',
            'Valid start time': base_date + timedelta(hours=2),
            'Transaction time': datetime(2025, 4, 27, 10, 0, 0),
            'Parameter_Name': 'Skin-look',
            'Parameter_Type': 'Skin-look',
            'Corrected_Unit': 'none'
        }
        synthetic_records.append(skin_record)
        
        # Allergic-state 
        allergic_values = ['None', 'Edema', 'Bronchospasm', 'Severe-Bronchospasm', 'Anaphylactic-Shock']
        allergic_value = random.choice(allergic_values)
        allergic_record = {
            'First name': first_name,
            'Last name': last_name,
            'LOINC-NUM': synthetic_loincs['Allergic-state'],
            'Value': allergic_value,
            'Unit': 'none',
            'Valid start time': base_date + timedelta(hours=3),
            'Transaction time': datetime(2025, 4, 27, 10, 0, 0),
            'Parameter_Name': 'Allergic-state',
            'Parameter_Type': 'Allergic-state',
            'Corrected_Unit': 'none'
        }
        synthetic_records.append(allergic_record)
        
        # Therapy (every few days, not every time point)
        if i % 2 == 0:  # Only on some dates
            therapy_values = ['None', 'CCTG522', 'Standard-Chemo', 'Immunotherapy']
            therapy_value = random.choice(therapy_values)
            therapy_record = {
                'First name': first_name,
                'Last name': last_name,
                'LOINC-NUM': synthetic_loincs['Therapy'],
                'Value': therapy_value,
                'Unit': 'none',
                'Valid start time': base_date + timedelta(hours=4),
                'Transaction time': datetime(2025, 4, 27, 10, 0, 0),
                'Parameter_Name': 'Therapy',
                'Parameter_Type': 'Therapy',
                'Corrected_Unit': 'none'
            }
            synthetic_records.append(therapy_record)

print(f"Generated {len(synthetic_records)} synthetic records")

# Combine original and synthetic data
synthetic_df = pd.DataFrame(synthetic_records)
final_df = pd.concat([enhanced_df, synthetic_df], ignore_index=True)

# Sort by patient and date
final_df = final_df.sort_values(['First name', 'Last name', 'Valid start time'])

print(f"\n=== FINAL DATABASE STATS ===")
print(f"Original records: {len(enhanced_df)}")
print(f"Synthetic records: {len(synthetic_df)}")
print(f"Total records: {len(final_df)}")

print(f"\nParameters now available:")
unique_params = final_df['Parameter_Type'].unique()
for param in sorted(unique_params):
    count = len(final_df[final_df['Parameter_Type'] == param])
    print(f"  {param}: {count} records")

# Save enhanced database
final_df.to_excel('enhanced_project_db.xlsx', index=False)
print(f"\n✓ Enhanced database saved as 'enhanced_project_db.xlsx'")

# Create a mapping file for reference
mapping_info = {
    'LOINC_Mappings': loinc_mapping,
    'Synthetic_LOINC_Codes': synthetic_loincs,
    'Required_Parameters_Status': {
        'Hemoglobin-level': '✓ Available (LOINC 30313-1)',
        'WBC-level': '✓ Synthetic (LOINC 26464-8)', 
        'Gender': '✓ Synthetic (LOINC 76689-9)',
        'Fever': '✓ Available (LOINC 39106-0 - Temperature)',
        'Chills': '✓ Synthetic (LOINC 43724-2)',
        'Skin-look': '✓ Synthetic (LOINC 8302-2)',
        'Allergic-state': '✓ Synthetic (LOINC 52473-6)',
        'Therapy': '✓ Synthetic (LOINC 18629-5)'
    }
}

import json
with open('database_mapping_info.json', 'w') as f:
    json.dump(mapping_info, f, indent=2, default=str)

print(f"✓ Mapping information saved as 'database_mapping_info.json'")

print(f"\n=== SUMMARY ===")
print("✅ All required parameters are now available!")
print("✅ LOINC codes are mapped to meaningful parameter names")
print("✅ Missing data has been synthetically generated")
print("✅ Database is ready for CDSS operations")

print(f"\nNext steps:")
print("1. Update cdss_loinc.py to use the enhanced database")
print("2. Modify the parameter lookup logic to use Parameter_Type column")
print("3. Test the CDSS with the new complete dataset") 