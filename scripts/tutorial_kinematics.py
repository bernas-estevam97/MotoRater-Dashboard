import streamlit as st

# --- Landing Page Content ---
st.title("❓ MotoRater Suite - Tutorial and help")
st.markdown("---")

st.markdown("""
        # 🐁 Kinematics Longitudinal Analyzer: User Guide & Tutorial
        
        Welcome to the **Kinematics Longitudinal Analyzer**! This application is designed to help researchers quickly process, visualize, and run robust statistical analyses on longitudinal behavioral and kinematic data. 
        
        This guide walks you through formatting your data, navigating the tabs, choosing statistical tests and customizing your plots.
        
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

        ### Step 1: Upload your data
        * Drag and drop your data file into the upload box.
        * **Sidebar → Display settings**: switch distance units (m / mm), set group colors (after Step 3), the
          significance marker color (use white in dark mode) and the plot size used on screen and in exported PNGs.

        ### Step 2: Check your data (📂 Data tab)
        * The header shows how many sheets, measurements and unique trial IDs were found.
        * Switch sheets with the dropdown. Expand **Trial IDs found** to scroll through every ID.

        ### Step 3: Define your groups (🧪 Groups & Subjects tab — ⚠️ required)
        1. Edit the table: *Group Name* is shown on plots, *Tag in ID* is the text searched for in each ID (e.g. "WT_M").
        2. Click **Extract variables from IDs**.
        3. Optionally **exclude subjects** (outliers, dropouts) from every plot and statistic.
        4. Check the **Group summary** (subjects, timepoints, trials per group) and the **Troubleshooting** panel for
           IDs without a group or timepoint.

        ### Step 4: Statistical analysis (🧮 Statistical Analysis tab)
        1. Pick the sheet, the measurement, the **groups** (2 for a two-group comparison, 3+ for multi-group; the first
           group selected is the reference, "Group A") and the **timepoints** (1 = cross-sectional, 2+ = longitudinal).
        2. The header cards show subjects, groups, timepoints, residual normality and design balance at a glance.
        3. In **Analysis setup**, choose like in GraphPad Prism:
            * **Statistical test** — *Auto* (default) uses the recommended test for every measurement; or pick one
              yourself. The recommended test is marked ★ and the reason is shown underneath.
            * **Multiple comparisons** — e.g. Tukey, Games-Howell, Dunn, pairwise t-tests, or model-based contrasts.
            * **Correction** — Holm, Šídák, Holm-Šídák, Bonferroni, Benjamini-Hochberg, two-stage BKY, or none.
            * **α** — significance threshold.
        4. **Read the warnings.** If your choice does not fit the data (e.g. a t-test on non-normal data, an RM ANOVA
           with missing timepoints, unequal variances with Tukey) a yellow box explains why and suggests an
           alternative. You can still run the test — the decision is yours.
        5. Results are split into tabs: **Graph**, **Multiple comparisons** (with CSV download), **Omnibus / model**,
           **Assumptions**, and **Methods text** (a ready-to-adapt statistics paragraph for your manuscript).
        6. **📦 Batch export** renders a 300-dpi PNG for every measurement in the sheet plus a
           `statistics_summary.csv`, using the same test, post-hoc and correction you selected.

        ### Step 5: Multivariate profiling (🕸️ Radar Profile tab)
        * Select at least 3 measurements, your groups and one timepoint — the plot updates automatically.
        * **Normalize** (recommended) scales each measurement to its highest group mean so degrees and meters can be
          compared on one chart.

        ---

        ## 🛠️ Troubleshooting & FAQ
        
        **Q: Do the statistical results match GraphPad Prism?**
        * **A:** Yes! The automated engine is specifically designed to mirror GraphPad Prism 8+ methodologies. For example, missing longitudinal data automatically triggers a Mixed-Effects Model (REML) just like Prism, and balanced repeated-measures post-hoc tests correctly calculate their standard errors using the pooled variance of the subjects rather than treating them as independent observations.
        
        **Q: Auto picked a mixed-effects model or GEE instead of ANOVA. Why? Can I override it?**
        * **A:** RM ANOVA needs complete data (no missing timepoints) and normal residuals. With missing timepoints Auto
          picks a mixed-effects model; with non-normal residuals it picks GEE. You can choose any test yourself in
          **Analysis setup** — the app then tells you which assumptions your choice violates. See the **Assumptions** tab.

        **Q: I get "subjects belong to more than one selected group".**
        * **A:** Two of your selected groups share animals (e.g. "Transgenic" and "TG Female"). Select groups that do
          not overlap.
        
        **Q: Why are my timepoints showing up as "None" or missing from the x-axis?**
        * **A:** Check your original file's `Ids` column. The app expects the timepoint to be a number followed by a W or T (e.g., `8W`, `12w`, `T1`). If your ID is just `Mouse1_WT_Day5`, the app won't know how to extract the temporal data. Look at the "Troubleshooting" expander in Tab 3 to see which IDs failed.
        
        **Q: Can I save individual graphs without doing the batch export?**
        * **A:** Yes! Hover over the top right corner of any individual graph, and click the "Camera" icon to download that specific plot as a PNG image.
        """)