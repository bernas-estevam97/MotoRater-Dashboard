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
        **Supported file types**: Excel (`.xlsx`), HDF5 (`.h5`), single Parquet (`.parquet`), or a ZIP of Parquet
        files. Each sheet holds one summary statistic (Mean, Median, Std, CV, …) with one row per trial or session.
        The app reads groups and timepoints in one of two ways:

        **A. Metadata columns (recommended).** The file has columns such as `Ids` (animal), `Experimental Group`,
        `Gender`, `Timepoint`, followed by the measurements. You pick the columns in the app; several group columns
        are combined (e.g. `WT F`). If the timepoint column is an index (1, 2, 3 …) set *Weeks per timepoint unit*
        (e.g. 4 if 1 = week 4). Extra columns such as body weight or recording date are simply ignored, or can be
        used as a covariate if numeric.

        **B. Tags inside the trial ID.** A column named exactly `Ids` with IDs like `2199_1R_44W_FOOTPRINT_WT_F`:

        * Timepoint: a number followed by `W` (weeks) or preceded by `T` (e.g. `44W`, `T2`).
        * Subject: everything before the timepoint (`2199_1R`).
        * Group: each *Tag in ID* is matched as a whole part between `_` separators (`TG` matches `…_TG_F`,
          not `ATG1`). Sex is read from an `M` / `F` part when present.
        
        ---
        
        ## 🚀 2. Step-by-Step Tutorial

        ### Step 1: Upload your data
        * Drag and drop your data file into the upload box.
        * **Sidebar → Display settings**: switch distance units (m / mm), set group colors (after Step 3), the
          significance marker color (use white in dark mode) and the plot size used on screen and in exported PNGs.
        * **Units & measurements → Add left/right averages** adds an `(L/R mean)` measurement for every Left/Right
          pair. Fewer measurements = less multiple-testing penalty.

        ### Step 2: Check your data (📂 Data tab)
        * The header shows how many sheets, measurements and unique trial IDs were found.
        * Switch sheets with the dropdown. Expand **Trial IDs found** to scroll through every ID.

        ### Step 3: Define your groups (🧪 Groups & Subjects tab — ⚠️ required)
        1. Choose **Extract variables from**: *Metadata columns* (pick animal, timepoint, group and optional sex
           columns) or *Trial IDs* (edit the tag table: *Group Name* is shown on plots, *Tag in ID* is matched in each ID).
        2. Click **Extract variables**. In metadata mode, animals labelled with different groups in different rows
           are listed in red — usually a typo in the file.
        3. Optionally exclude **whole animals** (dropouts) or **single sessions** (animal @ week, e.g. a failed
           recording) from every plot and statistic.
        4. Optionally fill **Cohorts & recording setup**: one row per cohort with its animal IDs (comma-separated;
           `2273` matches `2273_1L`, `2273_2R`, ...) and, if the camera setup changed, the first week recorded with the
           new setup. Use it when animals started at different times. Only the **Progression model** uses it.
        5. Check the **Group summary** (subjects, timepoints, trials per group) and the **Troubleshooting** panel for
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
        5. Results are split into tabs: **Graph**, **Multiple comparisons** (with CSV download), **Model effects**,
           **Assumptions**, and **Methods text** (a ready-to-adapt statistics paragraph for your manuscript).
        6. **📦 Batch export** renders a 300-dpi PNG for every selected measurement plus a
           `statistics_summary.csv`, using the same test, post-hoc and correction you selected. Pick your
           **primary outcomes** there: the column `p_corr_all_measurements` adjusts across all of them.

        ### Progression model (3+ timepoints)
        Tests whether groups **differ in level** (at the middle week) and whether they **change at different rates**
        (per week), treating age as continuous instead of comparing every timepoint separately. A slowly
        progressing phenotype is usually only detectable this way.
        * With cohort information it also absorbs recording-day (cohort × week) and camera-setup differences.
        * **Adjust for sex** pools both sexes (e.g. WT vs TG) while correcting for sex differences — more animals per
          group than splitting into WT Male / WT Female / ….
        * **Covariate** (optional): any numeric column from any sheet, e.g. walking speed or *Time Duration*.
          Avoid covariates that the disease itself changes, or part of the real effect is removed.
        * The graph shows the model's fitted trend per group as dashed lines (*Show fitted progression trend*).

        ### Data quality helpers
        * **95% confidence intervals** are shown for every difference where they can be computed.
        * **Possible outlier sessions**: for each measurement, sessions more than 5 robust SDs away from what is
          expected for that animal at that week are listed, with a button to exclude them.
        * **Left/right check**: an `(L/R mean)` measurement whose two sides disagree (r < 0.5 or means > 20% apart)
          shows a warning — the sides probably do not measure the same thing.
        * **Log-scale Y axis** (Graph → Axis settings): equal % differences look equally large.
        * **Log-transform** is on by default for SD / CV sheets (skewed values); results are then % differences.
        * On a CV sheet, measurements with negative values (signed velocity/acceleration, toe clearance) trigger a
          warning: their CV is not meaningful — use the SD sheet.

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