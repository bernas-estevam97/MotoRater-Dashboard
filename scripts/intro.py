import streamlit as st

st.title("📑 MotoRater Suite")
st.caption("Processing, statistics and visualization for MotoRater kinematics and time-series data.")

st.markdown("#### Tools")
c1, c2 = st.columns(2)
with c1:
    with st.container(border=True):
        st.page_link("scripts/kinematic_analysis_optimized.py", label="Kinematics Longitudinal Analysis", icon="📊")
        st.caption("Group comparisons over time with Prism-style test selection (t-tests, ANOVA, RM ANOVA, "
                   "mixed-effects, GEE, non-parametric), post-hoc corrections, radar profiles and batch export.")
    with st.container(border=True):
        st.page_link("scripts/convert_to_parquet.py", label="Excel → Parquet/HDF5 Converter", icon="⚡")
        st.caption("Convert filtered .xlsx files once — Parquet loads up to 50x faster.")
with c2:
    with st.container(border=True):
        st.page_link("scripts/time_series_analysis_excel.py", label="Time-Series Analysis — Excel", icon="📈")
        st.caption("Visualize and compare time-series data across measurements and runs.")
    with st.container(border=True):
        st.page_link("scripts/time_series_analysis_parquet.py", label="Time-Series Analysis — Parquet & HDF5",
                     icon="📈")
        st.caption("Same dashboard, much faster loading for large datasets.")

st.markdown("#### Help")
h1, h2, h3 = st.columns(3)
h1.page_link("scripts/tutorial_kinematics.py", label="Kinematics tutorial", icon="❓")
h2.page_link("scripts/tutorial_time_series.py", label="Time-series tutorial", icon="❓")
h3.page_link("scripts/stat_info.py", label="Statistical methodology", icon="🧮")

st.info("💡 Working with large datasets? Run your **filtered** Excel files through the Parquet converter first.")

with st.expander("Before you start", expanded=False):
    st.markdown("""
- Use **already filtered** MotoRater files with the time-series dashboards. Raw MotoRater output contains noise and
  filler data that can cause problems.
- The **Kinematics Longitudinal Analysis** tool uses one file built from all filtered files of your experiment (one
  row per trial or session, one sheet per statistic). Groups, timepoints and sex are extracted inside the tool; the
  filtering and merging scripts that build the file are not yet part of the app — ask the developer for them.
- The full user manual is `docs/MotoRater Suite - User Manual.md` in the project's GitHub repository.
""")
