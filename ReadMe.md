# Clinical Decision Support System (CDSS)

A comprehensive web-based Clinical Decision Support System built with Streamlit for medical decision-making and patient monitoring.

## 🌐 Live Application

**Link to app:** https://mini-project-cdss-5emu7rmb69u8baejhznzw2.streamlit.app/

## 📋 Overview

This CDSS provides healthcare professionals with:
- **Patient Status Monitoring**: Real-time patient state analysis with priority-based organization
- **Treatment Recommendations**: Evidence-based treatment protocols based on clinical states
- **Knowledge Base Management**: Comprehensive editor for medical classification tables and treatment rules
- **Temporal Analysis**: Historical patient state tracking and interval analysis
- **Interactive Dashboard**: Modern, user-friendly interface for clinical workflow

## 🏗️ System Architecture

### Core Components

1. **Frontend (`ui_streamlit.py`)**
   - Multi-tab Streamlit interface
   - Patient dashboard with priority-based sorting
   - Treatment recommendation board
   - Temporal analysis tools
   - Knowledge base editor integration

2. **Backend (`cdss_clean.py`)**
   - Clean database architecture with proper separation
   - Patient state calculation engine
   - Treatment recommendation logic
   - Temporal validity management
   - CRUD operations for all data types

3. **Knowledge Base Editor (`kb_editor.py`)**
   - Classification table management (1:1, 2:1_AND, 4:1_MAXIMAL_OR)
   - Treatment rule configuration
   - Validity period settings
   - Import/export functionality

4. **Legacy Support (`cdss_loinc.py`)**
   - Original LOINC-based implementation
   - Backward compatibility
   - Alternative data processing methods

## 📊 Data Structure

### Database (`cdss_database_v7.xlsx`)
- **Patient_Demographics**: Patient information (ID, Name, Gender, Age)
- **Lab_Results**: Laboratory test results with LOINC codes and validity periods
- **Clinical_Observations**: Clinical assessments and therapy status

### Knowledge Base (`knowledge_base.json`)
- **Classification Tables**: Medical parameter classification rules
- **Treatment Rules**: Gender-specific treatment protocols
- **Validity Periods**: Test result validity timeframes

## 🚀 Features

### 1. Patient Dashboard
- **Priority-based patient listing** with color-coded toxicity levels
- **Real-time measurements** with validity checking
- **Clinical state visualization** (Hemoglobin, Hematological, Systemic Toxicity)
- **Treatment status indicators** with expandable details

### 2. Recommendation Board
- **Comprehensive treatment overview** organized by priority
- **Active treatment protocols** vs. standard monitoring
- **Time-specific snapshots** with configurable timestamps
- **Patient name display** with fallback to ID

### 3. Temporal Analysis
- **State interval tracking** for specific medical conditions
- **Historical pattern analysis** with validity windows
- **Time-based queries** for patient state evolution

### 4. Knowledge Base Management
- **Interactive classification table editor** supporting multiple table types
- **Treatment rule management** with gender-specific protocols
- **Validity period configuration** with simplified day-based inputs
- **JSON import/export** for knowledge base backup/restore

## 🛠️ Installation & Setup

### Prerequisites
- Python 3.8+
- pip package manager

### Installation Steps

1. **Clone the repository:**
   ```bash
   git clone https://github.com/NevoLevi/mini-project-cdss.git
   cd mini-project-cdss
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application:**
   ```bash
   streamlit run ui_streamlit.py
   ```

4. **Access the application:**
   - Local: http://localhost:8501
   - Live: https://mini-project-cdss-5emu7rmb69u8baejhznzw2.streamlit.app/

## 📦 Dependencies

```
streamlit>=1.28.0
pandas>=2.0.0
altair>=5.0.0
openpyxl>=3.1.0
```

## 🗂️ File Structure

```
mini-project-cdss/
├── ui_streamlit.py              # Main Streamlit application
├── cdss_clean.py               # Core CDSS backend logic
├── kb_editor.py                # Knowledge base editor
├── cdss_loinc.py               # Legacy LOINC implementation
├── cdss_database_v7.xlsx       # Current patient database
├── knowledge_base.json         # Medical knowledge base
├── clean_database_mapping.json # Database structure mapping
├── project_db.xlsx             # Original database
├── requirements.txt            # Python dependencies
├── Mini-Project.Part 1.pdf     # Part 1 instructions
├── Mini-Project- part 2.pdf    # Part 2 instructions
├── Loinc_2.80.zip             # LOINC terminology reference
└── archive/                    # Archived development files
```

## 🎯 Usage Guide

### 1. Patient Monitoring
- Navigate to the **Clinical Dashboard** tab
- Select date/time for patient state snapshot
- Review patient list with priority-based sorting
- Expand patient cards for detailed information

### 2. Treatment Recommendations
- Go to the **Recommendation Board** tab
- Set the desired timestamp for recommendations
- Click "Generate Recommendations" to process all patients
- Review active treatment protocols vs. monitoring patients

### 3. Temporal Analysis
- Use the **State Analysis & Intervals** tab
- Select patient and clinical state type
- Choose target state to analyze
- View time intervals when patient was in specific states

### 4. Knowledge Base Management
- Access the **Knowledge Base Editor** tab
- Edit classification tables, treatment rules, or validity periods
- Use import/export for backup and sharing
- Preview changes before applying

## 🔧 Configuration

### Medical Classification Tables
- **1:1 Mapping**: Simple parameter-to-state classification
- **2:1_AND**: Matrix-based classification using two parameters
- **4:1_MAXIMAL_OR**: Multi-parameter toxicity grading

### Treatment Rules
- Gender-specific protocols
- State-based recommendations
- Toxicity grade considerations

### Validity Periods
- Lab test result validity windows
- Clinical observation timeframes
- Configurable before/after periods

## 🧪 Testing

The system includes comprehensive test coverage:
- Patient state calculation validation
- Treatment recommendation accuracy
- Database integrity checks
- Knowledge base consistency

## 📚 Documentation

- **Part 1 Instructions**: `Mini-Project.Part 1.pdf`
- **Part 2 Instructions**: `Mini-Project- part 2.pdf`
- **LOINC Reference**: `Loinc_2.80.zip`
- **Database Mapping**: `clean_database_mapping.json`

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project is developed for academic purposes as part of a Clinical Decision Support Systems course.

## 👥 Authors

- **Nevo Levi** - [@NevoLevi](https://github.com/NevoLevi)
- **Yonatan Diga** - [@yonatandiga12](https://github.com/yonatandiga12)

## 🔗 Links

- **Live Application**: https://mini-project-cdss-5emu7rmb69u8baejhznzw2.streamlit.app/
- **GitHub Repository**: https://github.com/NevoLevi/mini-project-cdss.git

---

*Built with ❤️ for healthcare professionals* 