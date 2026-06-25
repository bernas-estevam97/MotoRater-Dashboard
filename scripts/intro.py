import streamlit as st

# --- Landing Page Content ---
st.title("📑 Welcome to the MotoRater Suite")
st.markdown("---")

st.markdown("""
### Your centralized hub for Kinematics and Time-Series Analysis.

This suite is designed to process, analyze, and visualize your MotoRater data efficiently. 

👈 **Please select a tool from the sidebar to get started:**

* **📈 Time-Series Dashboard:** Visualize and compare standard time-series data across multiple measurements and test runs. This is available for both excel and parquet files (a faster data file format).
                   
* **📊 Kinematics Longitudinal Analyser:** Dive deep into specific kinematic behaviors and metrics over time.
            
* **⚡ Excel -> Parquet Converter:** Start here if you have raw `.xlsx` files. Converting them to Parquet will make your dashboards run up to 50x faster.
""")

st.info("💡 Tip: If you are analyzing a large dataset, always run it through the Parquet Converter first!")

st.markdown("""
### Additional Information ℹ️
            
- It is highly recommended that when using the time series dashboard functionality that you are working with already filtered files of your motorater files. Why? Because original files that come out of
  motorater processing algorithms present a lot of noise, filler data, among other data sections that might present problems in most cases.
            
- If you want faster speeds on your analysis, convert your **filetered** excel files to parquet using the tool: ⚡ Excel -> Parquet Converter
            
- The tool **Kinematics Longitudinal Analyser** uses a file that was obtained from all the filtered files of your data. To obtain this file make sure to ask the developer for it. The algorithm that creates
  these files is not available to the user yet. In time, there will be an app to use these algorithms allowing the user to independently filter and group the data files.

""")