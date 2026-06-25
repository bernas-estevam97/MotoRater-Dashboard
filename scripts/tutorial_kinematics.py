import streamlit as st

# --- Landing Page Content ---
st.title("❓ MotoRater Suite - Tutorial and help")
st.markdown("---")

st.markdown("""
        # 🐁 Kinematics Longitudinal Analyzer: User Guide & Tutorial
        
        Welcome to the **Kinematics Longitudinal Analyzer**! This application is designed to help researchers quickly process, visualize, and run robust statistical analyses on longitudinal behavioral and kinematic data. 
        
        This guide will walk you through how to format your data, navigate the tabs, customize your plots, and understand the automated statistical engine.
        
        ---
        
        ## 📋 1. Prerequisites: Data Formatting
        For the app to process your data automatically, your file must follow a few specific rules:
        
        1. **Supported File Types**: You can upload Excel (`.xlsx`), HDF5 (`.h5`), single Parquet (`.parquet`), or a ZIP archive containing multiple Parquet files.
        2. **The "Ids" Column**: **This is mandatory.** At least one of the columns in your dataset must be named exactly `Ids`.
        3. **ID Naming Convention**: The app uses your `Ids` to automatically figure out the subject, their group, and the timepoint. Your IDs should ideally look something like this:
            * `SubjectNumber_GroupTag_Timepoint`
            * *Example*: `Mouse123_WT_M_10W` or `Subject45_TG_T2`
            * **Important**: The app specifically looks for numbers followed by "W/w" (Weeks) or "T/t" (Timepoints) to extract the time (e.g., `10W` becomes `10`). It takes everything before the first recognized time/group tag as the unique Subject ID.
        
        ---
        
        ## 🚀 2. Step-by-Step Tutorial
        
        ### Step 1: Upload Your Data & Set Global Colors
        * Drag and drop your data file into the upload box.
        * **🎨 Sidebar Settings**: Once data is loaded and groups are extracted, use the left sidebar to assign custom colors to your specific experimental groups. You can also change the color of the significance asterisks (useful if you are using dark mode).
        
        ### Step 2: Verify Your Data (Tabs 1 & 2)
        * **📊 Data Viewer**: Use this tab to check that your data loaded correctly. You can switch between different statistics (sheets) using the dropdown.
        * **🆔 ID Overview**: This tab lists all the unique identifiers the app found in your `Ids` column. Scroll through to ensure no rows are missing.
        
        ### Step 3: Define Your Groups (Tab 3 - ⚠️ CRITICAL STEP)
        *You must complete this step before you can plot data or run statistics.*
        
        1. Go to the **🧪 Experimental Groups Setup** tab.
        2. You will see a table with "Group Name" and "Tag in ID".
        3. **Edit the table** to match your experiment. 
            * *Group Name* is what will show up on your graphs (e.g., "Wildtype Males").
            * *Tag in ID* is the exact text the app should search for in your IDs (e.g., "WT_M").
        4. Click the **"Extract Variables from IDs"** button.
        5. **Exclude Subjects**: If you have outliers or dropouts, you can now use the dropdown to completely exclude specific subjects from all downstream analysis.
        6. A summary table will appear showing you how many unique subjects were assigned to each group. 
        
        ### Step 4: 2-Group Analysis & Longitudinal Plotting (Tab 4)
        * Go to the **🧮 2-Group Analysis ➡️ Longitudinal Plotting 📈** tab.
        * Select the measurement, exactly **2 groups**, and the timepoints you want to analyze.
        * **Automated Stats Engine**: The app will automatically test your data's assumptions (Normality via D'Agostino-Pearson, Design Balance) and select the most mathematically appropriate pipeline:
            * *Cross-Sectional (1 Timepoint)*: Welch's T-Test or Mann-Whitney U.
            * *Longitudinal (Balanced)*: 2-Way Mixed ANOVA.
            * *Longitudinal (Missing Data)*: Linear Mixed-Effects Model (LMM).
            * *Non-Normal Longitudinal*: Generalized Estimating Equations (GEE).
        * **Interactive Plotting**: Scroll down to see your data visualized with significance brackets drawn directly on the chart.
        * **📦 Batch Export**: Click the "Generate All Plots (ZIP)" button at the bottom to automatically render and download high-resolution PNGs of *every single measurement* in your current sheet.
        
        ### Step 5: Multi-Group Omnibus Analysis (Tab 5)
        * Go to the **🌐 Multi-Group Omnibus Analysis** tab to compare **3 or more groups**.
        * Select your groups and timepoints. The app will generate a clean overview plot.
        * **Post-Hoc Heatmap**: Below the plot, the app runs comprehensive pairwise comparisons for every group combination at every timepoint, automatically applying False Discovery Rate (FDR) corrections to prevent false positives. Significant differences are highlighted in green.
        
        ### Step 6: Multivariate Profiling (Tab 6)
        * Go to the **🕸️ Radar Plots** tab to see how groups differ across *multiple* kinematic variables at a single moment in time.
        * Select at least 3 measurements, your groups, and a single timepoint.
        * **Normalize Data**: Highly recommended! Because angles (degrees) and distances (meters) are on completely different scales, normalizing them plots everything proportionally (0 to 1.0) without squashing smaller variables.
        * ❗**Important**: Every time you change a color, group, or metric, you must manually click the **Generate Radar Plot** button to update the visual.
        
        ---
        
        ## 🛠️ Troubleshooting & FAQ
        
        **Q: My statistical analysis pipeline switched from ANOVA to LMM or GEE. Why?**
        * **A:** Traditional ANOVAs require "perfect" balanced data (no missing timepoints). If a subject missed a week, or if your data severely violated normality (skewed distribution), the app's smart engine automatically stepped down to a Linear Mixed Model or GEE to prevent mathematically invalid results. You can view the assumption checks in the expandable dropdown.
        
        **Q: Why are my timepoints showing up as "None" or missing from the x-axis?**
        * **A:** Check your original file's `Ids` column. The app expects the timepoint to be a number followed by a W or T (e.g., `8W`, `12w`, `T1`). If your ID is just `Mouse1_WT_Day5`, the app won't know how to extract the temporal data. Look at the "Troubleshooting" expander in Tab 3 to see which IDs failed.
        
        **Q: Can I save individual graphs without doing the batch export?**
        * **A:** Yes! Hover over the top right corner of any individual graph, and click the "Camera" icon to download that specific plot as a PNG image.
        """)