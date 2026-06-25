import streamlit as st
from datetime import datetime

# 1. Set the configuration for the ENTIRE app here
st.set_page_config(page_title="MotoRater Suite", page_icon="📑", layout="wide")

# 2. Define your pages
# The file paths must now include your folder name so Streamlit can find them
intro_page = st.Page(
    page="scripts/intro.py", 
    title="Welcome", 
    icon="🏠", 
    default=True  # This is now your launch homepage
)

tutorial_page_time = st.Page(
    page="scripts/tutorial_time_series.py",
    title="Tutorial - Time Series",
    icon="❓",
)

tutorial_page_kine = st.Page(
    page="scripts/tutorial_kinematics.py",
    title="Tutorial - Kinematics Longitudinal Analyzer",
    icon="❓",
)

stat_info_page = st.Page(
    page="scripts/stat_info.py",
    title="Statistical Methodology",
    icon="🧮"
)

all_measurements_page = st.Page(
    page="scripts/time_series_analysis_excel.py", 
    title="Time-Series analysis - Excel Files", 
    icon="📈",
)

all_measurements_parquet = st.Page(
    page="scripts/time_series_analysis_parquet.py", 
    title="Time-Series analysis - Parquet & HDF5 Files", 
    icon="📈",
)

kinematics_analysis_page = st.Page(
    page="scripts/kinematic_analysis_optimized.py", 
    title="Kinematics Longitudinal Analysis", 
    icon="📊" 
)

converter_page = st.Page(
    page="scripts/convert_to_parquet.py", 
    title="Excel -> Parquet/HDF5 Converter", 
    icon="⚡"
)

# 3. Create the navigation menu
pg = st.navigation(
    {"Home": [intro_page, tutorial_page_time, tutorial_page_kine, stat_info_page],
     "MotoRater Tools": [all_measurements_page, all_measurements_parquet, kinematics_analysis_page, converter_page]}
)

# 4. Run the selected page
pg.run()

# --- NEW: Global Copyright in Sidebar ---
st.sidebar.text("")
st.sidebar.text("")
st.sidebar.text("")
# Using HTML to make the text a bit smaller and gray so it looks professional
current_year = datetime.now().year
st.sidebar.markdown(
    f"<div style='text-align: center; color: grey; font-size: 0.8em;'>© {current_year} Bernardo Estevam.<br>All rights reserved.</div>", 
    unsafe_allow_html=True
)