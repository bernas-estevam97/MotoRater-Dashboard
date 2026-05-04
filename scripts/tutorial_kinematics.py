import streamlit as st

# --- Landing Page Content ---
st.title("❓ MotoRater Suite - Tutorial and help")
st.markdown("---")

st.markdown("""
        # 🐁 Kinematics Longitudinal Analyzer: User Guide & Tutorial
        
        Welcome to the **Kinematics Longitudinal Analyzer**! This application is designed to help researchers quickly process, visualize, and run statistical analyses on longitudinal behavioral and kinematic data. 
        
        This guide will walk you through how to format your data, navigate the tabs, and generate your plots and statistics.
        
        ---
        
        ## 📋 1. Prerequisites: Data Formatting
        For the app to process your data automatically, your Excel file must follow a few specific rules:
        
        1. **Descriptive Statistics Format**: The file should be an Excel workbook (`.xlsx`) containing one or more sheets (e.g., Mean, Median, Max).
        2. **The "Ids" Column**: **This is mandatory.** The first column (or at least one of the columns) must be named exactly `Ids`.
        3. **ID Naming Convention**: The app uses your `Ids` to automatically figure out the subject, their group, and the timepoint. Your IDs should ideally look something like this:
           * `SubjectNumber_GroupTag_Timepoint`
           * *Example*: `Mouse123_WT_M_10W`
           * **Important**: The app specifically looks for numbers followed by "W" or "w" to extract the timepoint in weeks (e.g., `10W` becomes `10`). It takes everything before the first underscore (`_`) as the unique Subject ID.
        
        ---
        
        ## 🚀 2. Step-by-Step Tutorial
        
        ### Step 1: Upload Your Data
        * Drag and drop your `.xlsx` file into the upload box on the main page.
        * Once uploaded, the app will process your sheets and reveal the navigation tabs.
        
        ### Step 2: Verify Your Data (Tabs 1 & 2)
        * **📊 Data Viewer**: Use this tab to check that your Excel sheets loaded correctly. You can switch between different statistics (sheets) using the dropdown.
        * **🆔 ID Overview**: This tab lists all the unique identifiers the app found in your `Ids` column. Scroll through to ensure no rows are missing.
        
        ### Step 3: Define Your Groups (Tab 3 - ⚠️ CRITICAL STEP)
        *You must complete this step before you can plot data or run statistics.*
        
        1. Go to the **🧪 Experimental Groups Setup** tab.
        2. You will see a table with "Group Name" and "Tag in ID".
        3. **Edit the table** to match your experiment. 
           * *Group Name* is what will show up on your graphs (e.g., "Wildtype Males").
           * *Tag in ID* is the exact text the app should search for in your IDs (e.g., "WT_M").
        4. Click the **"Extract Variables from IDs"** button.
        5. A summary table will appear showing you how many unique subjects were successfully assigned to each group. If a group says `N = 0`, double-check your tags!
        
        ### Step 4: Visualize Trends (Tab 4)
        * Go to the **📈 Longitudinal Plotting** tab.
        * Select the sheet you want to look at, the specific measurement, and the groups you want to compare.
        * The app will automatically generate an interactive line graph showing the progression over time, complete with Standard Error of the Mean (SEM) error bars. 
        
        ### Step 5: Statistical Analysis (Tab 5)
        * Go to the **🧮 Statistical Analysis** tab.
        * Select your target measurement, exactly **2 groups** to compare, and the timepoints you want to include.
        * Click **"Run Statistical Analysis"**.
        * The app will:
          1. Filter out subjects that missed a timepoint (ANOVA requires complete data).
          2. Run a **2-Way Mixed ANOVA**.
          3. Run **Multiple Comparisons (Post-Hoc)** if applicable.
          4. Generate an interactive **Box Plot** with statistical significance brackets and p-value asterisks directly on the chart!
        
        ### Step 6: Multivariate Profiling (Tab 6)
        * Go to the **🕸️ Radar Plots** tab to see how groups differ across *multiple* kinematic variables at a single moment in time.
        * Select at least 3 measurements, your groups, and a single timepoint.
        * **Tip**: Leave "Normalize Data" checked. Because angles (degrees) and distances (meters) are on completely different scales, normalizing them allows them to be plotted proportionally on the same graph without squashing the smaller variables.
        
        ---
        
        ## 🛠️ Troubleshooting & FAQ
        
        **Q: My statistical analysis failed and gave me an error. What happened?**
        * **A:** This usually happens if a group ends up with fewer than 2 subjects after the app filters for "complete cases" (subjects that have data for *every* selected timepoint). Open the "Diagnostics & Data Viewer" expander in Tab 5 to see exactly how many subjects remained. 
        
        **Q: Why are my timepoints showing up as "None" or messing up the x-axis?**
        * **A:** Check your Excel file's `Ids` column. The app expects the timepoint to be a number followed by a W (e.g., `8W`, `12w`). If your ID is just `Mouse1_WT_Day5`, the app won't know how to extract the week. 
        
        **Q: Can I save the graphs?**
        * **A:** Yes! Hover over the top right corner of any graph, and click the "Camera" icon to download the plot as a PNG image.
        """)