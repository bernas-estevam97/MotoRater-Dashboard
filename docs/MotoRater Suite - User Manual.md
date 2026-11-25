# MotoRater Suite — User Manual

**Application:** MotoRater Suite (Streamlit)
**Document date:** 24 November 2026
**Maintainer:** Bernardo Estevam

This manual describes the whole application: where the input files come from, how the app reads them, how groups and timepoints are extracted, which rules the data must follow, which statistics are run and how to read the graphs. The companion document `docs/Info Statistical Analysis.pdf` is a short guide to reading the result tables. This manual contains the same information in more detail and also covers newer features.

---

## Contents

1. [Purpose and scope](#1-purpose-and-scope)
2. [Application overview](#2-application-overview)
3. [Upstream data pipeline (before the app)](#3-upstream-data-pipeline-before-the-app)
4. [Input files and data rules](#4-input-files-and-data-rules)
5. [Kinematics Longitudinal Analyzer](#5-kinematics-longitudinal-analyzer)
   - 5.1 [Sidebar display settings](#51-sidebar-display-settings)
   - 5.2 [Data tab](#52-data-tab)
   - 5.3 [Groups & Subjects tab: variable extraction](#53-groups--subjects-tab-variable-extraction)
   - 5.4 [Rules for groups, subjects and timepoints](#54-rules-for-groups-subjects-and-timepoints)
   - 5.5 [Statistical Analysis tab: data preparation and quality checks](#55-statistical-analysis-tab-data-preparation-and-quality-checks)
   - 5.6 [Statistical Analysis tab: tests, post-hoc tests and corrections](#56-statistical-analysis-tab-tests-post-hoc-tests-and-corrections)
   - 5.7 [Reading the results](#57-reading-the-results)
   - 5.8 [Graph options and what they show](#58-graph-options-and-what-they-show)
   - 5.9 [Batch export](#59-batch-export)
   - 5.10 [Radar Profile tab](#510-radar-profile-tab)
6. [Time-Series Analysis pages](#6-time-series-analysis-pages)
7. [Excel → Parquet/HDF5 Converter](#7-excel--parquethdf5-converter)
8. [Measurement dictionary](#8-measurement-dictionary)
9. [Limitations](#9-limitations)
10. [Troubleshooting and FAQ](#10-troubleshooting-and-faq)
11. [Glossary](#11-glossary)

---

## 1. Purpose and scope

The MotoRater apparatus films a mouse walking through a test (ground walk/footprint, grid walk, beam walk or swimming) from several camera views. Marker tracking turns the videos into body-marker positions over time. Gait metrics (heights, joint angles, step lengths, paw velocities) are calculated from these positions.

The MotoRater Suite takes these processed files and provides:

- **Longitudinal statistics:** group comparisons over weeks of age, with a choice of tests similar to GraphPad Prism.
- **Exploratory time-series views:** frame-by-frame plots of single recordings.
- **File conversion:** Excel to Parquet or HDF5 for faster loading.

The app does not track videos or calculate gait metrics. These steps happen before the app; Section 3 describes them.

---

## 2. Application overview

The app opens on the **Welcome** page. The sidebar navigation has three sections.

| Section | Page | Purpose | Input |
| :--- | :--- | :--- | :--- |
| Home | Welcome | Links to all tools and guides | — |
| MotoRater Tools | **Kinematics Longitudinal Analysis** | Group comparisons over time, statistics, graphs, radar profiles, batch export | One merged file per experiment (`.xlsx`, `.h5`/`.hdf5`, `.parquet`, `.zip` of Parquet files) |
| MotoRater Tools | Time-Series analysis – Excel Files | Plot single recordings frame by frame; compare recordings | Filtered per-recording `.xlsx`/`.xls` files |
| MotoRater Tools | Time-Series analysis – Parquet & HDF5 Files | Same as above, faster loading | `.parquet`, `.h5`, `.hdf5`, or folders of them |
| MotoRater Tools | Excel → Parquet/HDF5 Converter | Batch-convert Excel files and download them as one ZIP | Uploaded `.xlsx`/`.xls` files |
| Guides | Tutorial – Kinematics | Short in-app tutorial | — |
| Guides | Tutorial – Time Series | Short in-app tutorial | — |
| Guides | Statistical Methodology | In-app summary of the statistics | — |

**Performance notes.**

- On start, the app loads the large statistics libraries (`pingouin`, `statsmodels`) in the background while the Welcome page is shown. This makes the first analysis faster.
- Loaded files are cached by content. If you upload a corrected file with the **same name**, the app detects the new content and resets groups, exclusions and settings for it.
- In the time-series pages, **🧹 Clear Server Cache** frees memory.

---

## 3. Upstream data pipeline (before the app)

The scripts in this section are in the separate *Python-Scripts-Automation* repository. They are not part of the app.

```
Video recording
   │  marker tracking (camera views: ventral, left, right)
   ▼
calculations_<experiment>.py ──►  <name>_processed.xlsx
   │                               sheets: "Positions (used)", "Kinematics"
   ▼
filtering_algorithm.py ─► <name>_filtered.xlsx  (+ error_log.txt)
   │                               Kinematics sheet rebuilt, cut to the movement window,
   │                               heights relative to the floor, QC columns, summary rows
   ▼
descriptive_stats_prep.py ─► <EXPERIMENT>_descriptive_statistics.xlsx
   │                               one sheet per statistic, one row per trial or session
   ▼
(optional) merging / adding metadata columns (group, sex, timepoint)
   ▼
Kinematics Longitudinal Analyzer
```

The time-series pages use the per-recording `_filtered.xlsx` files. The Kinematics Analyzer uses the merged descriptive-statistics file.

### 3.1 Calculation scripts

For each recording, the calculation script writes two sheets:

- **Positions (used):** smoothed marker positions (X, Y per marker, in metres) with the camera Y offset applied, plus a `Time` column.
- **Kinematics:** the calculated metrics per frame.

Version 1 of these scripts damaged the saved Kinematics sheet in four ways:

1. **Outlier removal cut real peaks.** A paw rests for most frames, so the median-based outlier filter flagged every swing peak. Paw speeds came out about 10× too low, and toe-clearance and step-length peaks were cut.
2. **Noisy derivatives.** Velocity and acceleration were calculated by repeated numerical differentiation, which amplifies frame-to-frame noise.
3. **Double smoothing.** A second smoothing pass on the calculated metrics flattened the peaks again.
4. **Mixed camera views.** Nose Height and Tail Tip Height checked one camera view but read the other, so saved sheets mix both views.

The Positions (used) sheet was written before these steps. Filtering v2 therefore uses it as the source.

### 3.2 Filtering

Each `*_processed.xlsx` file is processed in its own process. Files that already have a `_filtered.xlsx` in the output folder are skipped.

1. **Read both sheets** and drop fully empty rows.
2. **Remove tracking placeholders and implausible positions.**
   - A marker whose X and Y repeat exactly between frames is a tracker placeholder (lost marker). The repeated frames become blank.
   - Body checks in the ventral view blank the whole frame when: the nose is behind a hind paw; a hind paw is more than 10 mm ahead of the front paw on the same side; or the nose–tail-base length is outside 70–130 % of the session median.
   - **Jumps:** a marker that moves more than 30 mm in one frame (3 m/s at 100 fps) is blanked in that frame.
   - **Spikes:** a non-tail marker that moves out by more than 8 mm and straight back in one frame is blanked in that frame.
3. **Find the movement window.** The start is the first frame where the chosen marker (tail tip, tail centre, tail base or both hind paws) moves away from its first position. The end is when the nose reaches its exit position or stops being tracked near the exit. Frames outside the window are removed.
4. **Rebuild the Kinematics sheet from positions.** For every column with a known formula:
   - Heights, clearances and drag: the marker's Y (absolute value in the upside-down right view).
   - Distances (step width, step length, protraction/retraction): Euclidean distance between two markers.
   - Angles: the angle at the middle of three markers.
   - Paw Vx, Vy, Speed, Ax, Ay, |Acc|: Savitzky-Golay derivative (window 5, order 2).
   - Columns without a formula, or whose markers are missing, are copied from the old sheet and listed in the log.
5. **Optional hind-paw height cutoff.** Height columns are blanked after the left hind toe reaches a fixed X position (0 m for the "new" setup, −0.016 m for the "old" setup).
6. **Heights relative to the floor.** Height columns are found by name (`Height`, `Clearance`, `Drag`). A column whose mean is above 0.3 m belongs to the upside-down right view.
   - *auto* (recommended): the floor is measured per session. The left floor is the 10th percentile of left hind toe Y, and the right floor is the 90th percentile of |right hind toe Y|. Left height = value − floor; right height = floor − value.
   - *fixed*: constants per species, experiment and setup (old method).
7. **Swing frames only for paw kinematics.** For each paw, frames where its speed is at or below the swing threshold are blanked in all six velocity and acceleration columns. Statistics of these columns therefore describe the swing phase only. Heights, angles and distances are not affected.

   | Experiment | Default threshold | Reason |
   | :--- | :--- | :--- |
   | groundwalk | 0.1 m/s | Bimodal speeds: jitter ≈ 0.02 m/s, swing ≈ 0.5–0.6 m/s; 0.1 m/s is in the valley |
   | gridwalk | 0.1 m/s | Same shape as groundwalk |
   | beamwalk | 0.03 m/s | One broad peak (slow gripping); 0.03 m/s removes only jitter |
   | swimming | 0.1 m/s | Not measured; general default |

   A threshold of 0 keeps stance frames.
8. **Quality-control (QC) columns** are added, with one constant value per session:
   - `QC Tracked Frames (%)`: frames in the window where all four paws have a position. A warning is logged below 70 %.
   - `QC Hind Ahead of Front (%)`: frames where a hind paw is ahead of the front paw on the same side. This value should be near 0; high values mean label swaps.
   - `QC Step Length SD (Left/Right) (m)`: near 0 means the front and hind markers are stuck on one paw.
9. **Summary rows and save.** Under the frame data the script writes: a blank row, `Time Duration`, then `Mean`, `Std`, `Median`, `Min`, `Max`, `Max_Normalized_Mean` and `CV` per column, then `Height Window (start, end s)` (v2 only). Blank cells are skipped. The output is `<name>_filtered.xlsx` plus `error_log.txt`, which records the settings, warnings and floor values.

**Prompts asked once per run:** input/output folder, start marker (0 tail tip, 1 tail centre, 2 tail base, 3 both hind paws), species (Mus, Acomys), experiment type, old/new setup, hind-paw height cutoff (yes/no), floor reference (auto/fixed), swing speed threshold.

### 3.3 Descriptive statistics setup

This script reads the summary rows of every `*filtered.xlsx` file in a folder and writes `<EXPERIMENT>_descriptive_statistics.xlsx`:

- One sheet per statistic: **Mean, Std, Median, Min, Max, Max_Normalized_Mean, CV**, plus a **Time Duration** sheet.
- One row per file. The first column, `Ids`, is the file name up to `_out` (for example `2199_1R_44W_FOOTPRINT_WT_F`).
- **Optional trial grouping:** if you answer *yes*, a 1- or 2-digit trial number between underscores (`_1`, `_02`) is removed from the ID. Rows with the same remaining ID are then averaged. This requires that all trials of a session have the same base name.

Files from several experiments can be merged with `descriptive_merger_with_rename_map.py`, which also harmonises paw-velocity column names (`Front Right Vx (m/s)` → `Front Right Paw Vx (m/s)`). A merged ("all-in-one", AIO) file can also have metadata columns added (animal, group, sex, timepoint). The analyzer reads these in **Metadata columns** mode (Section 5.3).

---

## 4. Input files and data rules

### 4.1 Kinematics Longitudinal Analyzer

| Format | How it is read |
| :--- | :--- |
| `.xlsx` | Every worksheet becomes a sheet (statistic). |
| `.h5` / `.hdf5` | Every key in the HDF5 store becomes a sheet. |
| `.parquet` | One sheet named `Data`. |
| `.zip` | Every `.parquet` file inside becomes a sheet, named after the file without `.parquet`. |

**Required structure.**

- Each sheet holds **one summary statistic** (Mean, Median, Std, CV, …) with **one row per trial or session** and one column per measurement.
- All sheets must use the same row identifiers. These are the `Ids` column in Trial-ID mode, or the subject and timepoint columns in Metadata mode.
- Group, timepoint and sex are taken from the **first sheet** of the file.

**Automatic processing on load.**

- **Column names are standardised** with a fixed rename map. Units are added to lengths and angles (for example `Hip Height (Left)` → `Hip Height (Left) (m)`, `Knee Angle (Left)` → `Knee Angle (Left) (º)`), and `m/s^2` is written as `m/s²`.
- **Measurement columns** are columns that are not metadata, not `Ids` and not `QC …`, and that are mostly numeric (more than 50 % of the cells convert to a number). One stray text cell therefore does not hide a measurement.
- **QC columns are hidden** from the measurement lists. They rate tracking quality, not the animal, and are often constant (for example 100 %). They remain visible in the Data tab.

### 4.2 Time-series pages

- One file per recording. The **`Time` column is required**; it is always the X axis.
- Summary rows under the frames of filtered files are removed automatically: only rows with a numeric `Time` value are kept. This works for v1 files (9 summary rows) and v2 files (10 summary rows), and has no effect on files that are already trimmed.

### 4.3 Converter

- Input: `.xlsx`/`.xls` files. The same summary-row removal is applied to every sheet that has a `Time` column, and text columns that are fully numeric are converted to numbers.

---

## 5. Kinematics Longitudinal Analyzer

The workflow follows the four tabs from left to right: **📂 Data → 🧪 Groups & Subjects → 🧮 Statistical Analysis → 🕸️ Radar Profile**.

### 5.1 Sidebar display settings

| Setting | Effect |
| :--- | :--- |
| **Distance units** (m / mm) | Multiplies columns whose names end in `(m)`, `(m/s)`, `(m/s²)` or `(m/s^2)` by 1000 and renames them (`(mm)`, `(mm/s)`, `(mm/s²)`). P-values do not change. Columns without a unit in their name are not converted. |
| **Add left/right averages** | Adds an `(L/R mean)` measurement for every Left/Right column pair, as the mean of both sides per row. Fewer measurements mean a smaller multiple-testing penalty. |
| **Group colors** | One colour picker per group (available after variable extraction). Used in all graphs and exported PNGs. |
| **Significance marker color** | Colour of the stars on graphs (use white in dark mode). |
| **Fill available width** | On-screen graphs fill the page width. Turn it off to use the width slider on screen too. |
| **Plot width / height (px)** | Size of exported PNGs, and of on-screen graphs when *Fill available width* is off. |

### 5.2 Data tab

- Header cards: number of sheets, number of measurements and number of unique trial IDs.
- A sheet selector and a scrollable table of the raw data.
- **Trial IDs found:** list of every value in the `Ids` column.

### 5.3 Groups & Subjects tab: variable extraction

You must click **Extract variables** before the Statistical Analysis and Radar tabs can be used. There are two modes. The app pre-selects **Metadata columns** when the first sheet has text columns other than `Ids`.

#### Mode A — Trial IDs (tags inside each ID)

Group, timepoint, subject and sex are read from IDs such as `2199_1R_44W_FOOTPRINT_WT_F`.

**Group tags.** Edit the table with **Group Name** (shown on graphs) and **Tag in ID** (text searched in the ID). The default table is:

| Group Name | Tag in ID |
| :--- | :--- |
| Wildtype | WT |
| Transgenic | TG |
| WT Male | WT_M |
| WT Female | WT_F |
| TG Male | TG_M |
| TG Female | TG_F |

Matching rules:

1. The ID and the tag are converted to upper case. Hyphens and spaces become `_`, and the text is wrapped in `_` on both sides.
2. A tag matches only **whole `_`-separated parts** of the ID. `TG` matches `…_TG_F` but not `…_ATG1_…`. A multi-part tag such as `TG_F` matches the consecutive parts `…_TG_F`.
3. An ID can match **several tags**. It then belongs to several groups (for example `Transgenic` and `TG Female`). These overlapping groups are useful for different analysis levels, but **must not be selected together** in one analysis (Section 5.4).
4. An ID that matches no tag is assigned to group **Unknown**. Unknown is never offered for analysis.

**Timepoint.** The app takes the first number followed by `W` or `w` (`44W` → week 44). If there is none, it takes a number after `T` or `t` (`T2` → 2). If neither is found, the timepoint is empty and the ID is listed under Troubleshooting.

**Subject (animal).** The ID is split at `_`. The subject is every part before the first timepoint-like part (`44W`, `Week 44W`, `W44`, `T2`, `2T`). For `2199_1R_44W_…` the subject is `2199_1R`. If no such part exists, the first part is used.

**Sex.** A separate ID part `M`/`MALE` gives M, and `F`/`FEMALE` gives F (case-insensitive). If at least one ID has a sex, IDs without one get `Unknown`. If no ID has a sex, the sex variable is not created.

#### Mode B — Metadata columns

Use this mode for files with columns such as `Ids` (animal), `Experimental Group`, `Gender` and `Timepoint`. The app pre-selects columns whose names contain typical words (animal/subject/id, timepoint/week/time/age, group/genotype/condition, sex/gender). You can change every choice.

| Control | Meaning |
| :--- | :--- |
| Animal / subject column | Identifies the animal. |
| Timepoint column | Numeric timepoint. Rows that are not numeric get no timepoint. |
| Weeks per timepoint unit | Converts the timepoint column to weeks: use 1 if it already holds weeks, or 4 if timepoint 1 = week 4, 2 = week 8, and so on. |
| Group column(s) | One or more columns that define groups. At least one is required. |
| Sex column (optional) | Enables *Adjust for sex* in the progression model. `MALE`/`FEMALE` are shortened to `M`/`F`; empty values become `Unknown`. |

How the groups are built:

1. With several group columns, **every combination of the columns** becomes a set of groups. For example, *Experimental Group* + *Gender* gives `WT`, `TG`, `F`, `M`, `WT F`, `WT M`, `TG F`, `TG M`. You can therefore analyse by genotype only, by sex only, or by both, without extracting again.
2. Group names are the column values joined with a space.
3. In the full combination (all columns), a row with a missing value in any group column is assigned to **Unknown**. In partial combinations, such rows are left out.
4. Each row gets a key `subject|timepoint` (for example `2199_1R|44`). This key replaces `Ids` in **every sheet that has both the subject and the timepoint column**. Several rows with the same key (several trials) are averaged later.
5. **Labelling check:** in the full combination, each animal should have one group. If an animal has different groups in different rows, the app shows the rows that disagree with the animal's most common group. This is usually a typo in the file. Fix the file or exclude these sessions.

#### Exclusions

- **Whole animals removed:** removes the selected animals from every graph and statistic (for example dropouts).
- **Single sessions removed (animal @ week):** removes one recording session, for example a failed recording. The outlier panel (Section 5.5) can add sessions here. Exclusions apply to all measurements and sheets.

#### Cohorts & recording setup (optional)

Fill in this table when animals started the experiment at different times, or when the camera setup changed. **Only the progression model uses it.**

| Column | Rule |
| :--- | :--- |
| Cohort | Cohort name. |
| Animal IDs | Separated by commas, semicolons or spaces. An ID matches a subject that equals it or starts with it plus `_`: `2273` matches `2273`, `2273_1L` and `2273_2R`. |
| New setup from week | First week recorded with the new camera setup. Sessions of this cohort at or after this week are marked `Setup = New`. Leave empty if the setup did not change. |

Subjects that match no row form an **Unassigned** cohort, and a warning lists them. The caption under the table shows the number of subjects per cohort.

#### Group summary and Troubleshooting

- **Group summary:** for each group, the number of subjects (N), timepoints and trials, after exclusions.
- **Troubleshooting:** lists IDs that matched no group tag and IDs without a timepoint. The panel opens automatically when there are problems.

### 5.4 Rules for groups, subjects and timepoints

| Rule | Consequence when broken |
| :--- | :--- |
| Selected groups must **not share animals** (for example, do not combine `Transgenic` with `TG Female`). | Red error; the analysis is blocked. |
| Each selected group needs **at least 2 subjects**. | Red error; no test can be run. |
| Repeated-measures models (RM ANOVA, mixed-effects, GEE, progression) need **at least 3 subjects per group**. | Red error for these tests. *Auto* then tests each timepoint separately instead. |
| The **progression model** needs **at least 3 timepoints**. | The test is not offered with fewer timepoints. |
| A measurement must **vary**: it cannot have the same value in every selected session. | Red error ("same value in every selected session"). |
| The **first selected group is the reference** (Group A). All differences are reported as B − A. | — |
| Several trials of one animal at one timepoint are **averaged first** (one value per animal per timepoint). This avoids pseudo-replication. | — |
| Group `Unknown` is never analysed. | — |
| In Metadata mode, every sheet must contain the subject and timepoint columns. | Sheets without them keep the original `Ids` and do not match any animal. |

### 5.5 Statistical Analysis tab: data preparation and quality checks

**Selections.** Choose the **sheet** (statistic), the **measurement**, the **groups** (2 groups for a two-group comparison, 3 or more for a multi-group analysis) and the **timepoints**. One timepoint gives a cross-sectional test; two or more give a longitudinal analysis.

**Data preparation.** The selected measurement is joined to the group mapping. Values are converted to numbers, and empty values are removed. Trials are then averaged per **subject × group × timepoint**. Cohort, setup and sex are carried along when they exist.

**KPI header.**

| Card | Meaning |
| :--- | :--- |
| Subjects | Number of animals (tooltip: n per group). |
| Groups / Timepoints | Number selected with data. |
| Residual normality | Pass/Fail of the normality check (tooltip: test and p-value). |
| Design | *Balanced* when every animal has every selected timepoint; otherwise the number of incomplete animals. |

**Automatic warnings for the measurement.**

- **CV of a measurement that crosses zero.** On a variability sheet (a sheet name containing the word `std`, `sd`, `cv`, `var` or `variance`), negative values mean that the underlying measurement crosses zero. Examples are signed velocity or acceleration components and toe clearance. Their coefficient of variation is not meaningful; use the SD sheet.
- **Left/right disagreement.** For an `(L/R mean)` measurement, the app compares the two sides. If the correlation is r < 0.5, or the means differ by more than 20 %, the sides probably do not measure the same thing (different camera, calibration or floor reference). Analyse each side separately.

**Possible outlier sessions.** For each measurement the app calculates:

1. The deviation of each session from its **group × week median**. This follows growth and disease course.
2. The deviation minus the **animal's own median deviation**. This allows for animals that are always a little higher or lower.
3. A robust z-score: this value divided by 1.4826 × the median absolute deviation (MAD) of all sessions.

Sessions with |robust z| > 5 are listed. A button adds them to *Single sessions removed* for all measurements; you can undo this in the Groups & Subjects tab. Check the video before you exclude a session: a flagged session is often a tracking or calibration failure, but not always.

**Assumption checks** (run on every selection, at the chosen α):

| Check | Method | Used for |
| :--- | :--- | :--- |
| Residual normality | Residuals of a model that matches the design: a mixed model `time × group` with a random intercept per animal (2+ timepoints, ≥ 2 animals per group), otherwise ordinary least squares. **Shapiro-Wilk** when there are fewer than 20 residuals, **D'Agostino-Pearson** otherwise. **CLT override:** with ≥ 100 residuals and \|skew\| < 1 the data are treated as normal. | Parametric vs non-parametric tests |
| Equal variances | **Levene's test** at each timepoint where at least 2 groups have ≥ 2 values; the worst (smallest) p is reported. | Student's t, ordinary ANOVA, Tukey vs Welch tests, Games-Howell |
| Design balance | Does every animal have every selected timepoint? | RM ANOVA vs mixed-effects model |
| Sphericity | **Mauchly's test** on complete animals, 3+ timepoints. | Greenhouse-Geisser correction of RM ANOVA |
| Group overlap | Is any animal in two selected groups? | Blocks the analysis |
| Constant measurement | Is there only one value? | Blocks the analysis |
| Data shape | Counts (non-negative integers), strictly positive values, skew of the raw values | Automatic GEE distribution family |

### 5.6 Statistical Analysis tab: tests, post-hoc tests and corrections

#### Analysis setup

| Control | Options |
| :--- | :--- |
| Statistical test | **Auto** (default) applies the recommended test, which is decided separately for each measurement. You can also pick any valid test. The recommended test is marked ★, and its reason is shown below the setup panel. |
| Multiple comparisons | Post-hoc tests valid for the chosen test. |
| Correction | Multiple-comparison correction. It is disabled for Tukey and Games-Howell, which already control the error rate. |
| α | 0.05 (default), 0.01, 0.001 or 0.1. |
| GEE options | Distribution family (auto, Gaussian, Gamma, Poisson) and working correlation (auto, autoregressive, exchangeable, independence). Shown for GEE only. |
| Progression options | Adjust for sex, Covariate, Log-transform. Shown for the progression model only. |

#### Recommendation (decision tree used by *Auto*)

```
2+ timepoints AND every group has ≥ 3 animals?
├─ yes ─ residuals normal AND design balanced ─► Two-way RM ANOVA (mixed design)
│        residuals normal, missing timepoints   ─► Mixed-effects model (REML)
│        residuals not normal                   ─► GEE
└─ no (1 timepoint, or a group with < 3 animals → each timepoint tested separately)
   ├─ 2 groups ─ normal ─► Welch's t-test      | not normal ─► Mann-Whitney U
   └─ 3+ groups ─ normal + equal variances ─► Ordinary one-way ANOVA + Tukey
                  normal, unequal variances ─► Welch's ANOVA + Games-Howell
                  not normal                ─► Kruskal-Wallis + Dunn
```

The progression model is never chosen automatically. Select it yourself when you expect a gradual change over many weeks.

#### Tests available

| Design | Test | Post-hoc options | Main assumptions |
| :--- | :--- | :--- | :--- |
| 2 groups, 1 timepoint | Welch's unpaired t-test | Direct comparison | Normality |
| | Unpaired t-test (equal variances) | Direct comparison | Normality, equal variances |
| | Mann-Whitney U (two-sided) | Direct comparison | Similar distribution shape |
| 3+ groups, 1 timepoint | Ordinary one-way ANOVA | Tukey's HSD, pairwise t-tests, pairwise Welch t-tests | Normality, equal variances |
| | Welch's one-way ANOVA | Games-Howell, pairwise Welch t-tests | Normality |
| | Kruskal-Wallis | Dunn's test, pairwise Mann-Whitney U | — |
| 2+ groups, 2+ timepoints | Two-way RM ANOVA (mixed design) | Model-based contrasts | Normality, complete data, sphericity (corrected) |
| | Mixed-effects model (REML) | Model-based contrasts | Normal residuals |
| | Generalized estimating equations (GEE) | Model-based contrasts | Many animals (robust standard errors) |
| 2+ groups, 3+ timepoints | Progression model | Level and rate contrasts vs the reference group | Normal residuals (log option) |
| 2+ timepoints | Any single-timepoint test above, run at each timepoint | As above | Ignores repeated measures (a warning is shown) |

#### How each longitudinal model works

**Two-way RM ANOVA (mixed design).** Time is the within-animal factor and group is the between-animal factor (`pingouin.mixed_anova`). Animals with any missing timepoint are **removed completely** (listwise deletion); the number removed is shown under the omnibus table. When Mauchly's test shows a sphericity violation, the **Greenhouse-Geisser corrected p** is reported. Effect size: partial eta-squared (η²p). Post-hoc contrasts come from a mixed model fitted to the same complete animals.

**Mixed-effects model (REML).** `value ~ time × group`, with time and group as categories and a **random intercept per animal**. It keeps every available data point, as Prism's mixed-effects analysis does. Main effects and the interaction are tested with **Wald χ²** tests using sum-to-zero coding (Type III-style). The fit tries several optimizers (L-BFGS, BFGS, Powell, Nelder-Mead) because one optimizer alone often fails on singular matrices.

**GEE.** Same fixed effects as the mixed model, with robust ("sandwich") standard errors.

- *Family (auto):* Poisson for counts, Gamma with log link for strictly positive data with skew > 1, otherwise Gaussian. With a log link, differences are on the log scale (exp(difference) = ratio B/A).
- *Working correlation (auto):* autoregressive AR(1). If AR(1) cannot be estimated, the fit falls back to exchangeable and a warning is shown.
- With **fewer than 40 animals**, the **Mancl-DeRouen bias-reduced** standard errors are used, because plain sandwich errors are too small in small samples.

**Model-based contrasts** (post-hoc test for the three models above). The difference B − A is calculated for every pair of groups at every timepoint, from the fitted model and its covariance (the pooled repeated-measures error, as Prism does). Each contrast has an SE, a 95 % Wald confidence interval and a p-value.

**Progression model.** Age is treated as a **continuous** variable instead of separate weeks:

```
value ~ age × group + age²  [+ Setup] [+ Sex] [+ covariate]
```

- Age is centred on the middle of the selected weeks and scaled internally. All results are converted back to **per week**.
- The **age² term is shared** by all groups. It allows a curved course; the groups differ in level and in linear rate.
- **Random effects:** an intercept and an age slope per animal. With **2 or more cohorts**, the model instead has variance components for animal, animal slope and **recording session (cohort × week)**. This absorbs day-to-day recording differences. If the slopes cannot be estimated, the model uses random intercepts only and shows a note.
- **Setup:** a fixed effect for the camera-setup change. The reference is the setup recorded first, so the term reads *Setup: New*.
- **Adjust for sex:** sex as a fixed effect. This lets you compare, for example, WT vs TG with both sexes pooled. It needs sex information and both sexes in the selection.
- **Covariate:** any numeric column from any sheet (for example walking speed or Time Duration). It is standardised (reported per SD). Sessions without a value are left out, with a note. Do not use a covariate that the genotype itself changes; it would remove part of the real effect.
- **Log-transform:** on by default for SD/CV sheets, and available only when all values are positive. Differences are then also reported as **% differences**, with % confidence intervals.
- **Output:** two contrasts per group vs the reference: **Level difference at week c** (c = centre week) and **Rate difference per week**. The model's residual normality is checked after fitting and shown as a note.

#### Post-hoc tests for single-timepoint analyses

| Post-hoc | Details |
| :--- | :--- |
| Tukey's HSD | After ordinary ANOVA, equal variances. Already adjusted within each timepoint. |
| Games-Howell | After Welch's ANOVA, unequal variances. Already adjusted within each timepoint. |
| Dunn's test | After Kruskal-Wallis. Tie-corrected z on ranks pooled over the selected groups at that timepoint. |
| Pairwise t / Welch t / Mann-Whitney U | Simple pairwise tests, adjusted with the selected correction. |

Groups with fewer than 2 values at a timepoint are left out at that timepoint.

#### Multiple-comparison corrections

The **family** is every comparison in the results table. For example, 2 groups × 8 timepoints is a family of 8 comparisons.

| Correction | Controls | Notes |
| :--- | :--- | :--- |
| **Holm (step-down)** — default | Family-wise error rate | More powerful than Bonferroni; a safe general choice. |
| Šídák / Holm-Šídák | Family-wise error rate | Slightly more powerful than Bonferroni / Holm. |
| Bonferroni | Family-wise error rate | Strictest. |
| Benjamini-Hochberg (FDR) | False discovery rate | For exploratory screens with many comparisons. |
| Two-stage step-up, Benjamini-Krieger-Yekutieli (FDR) | False discovery rate | More powerful FDR method. |
| None (Fisher's LSD) | — | Only for a few planned comparisons. A warning appears with more than one comparison. |

#### Fit messages

Every choice is checked against the data before it runs:

- **Red (error, blocks the analysis):** overlapping groups; constant measurement; a group with fewer than 2 animals; a repeated-measures test with fewer than 3 animals per group; the progression model with fewer than 3 timepoints.
- **Yellow (warning, the analysis still runs):**
  - a parametric test on non-normal residuals (with a non-parametric alternative suggested);
  - unequal variances with Student's t, ordinary ANOVA, Tukey or pairwise t-tests;
  - RM ANOVA with missing timepoints;
  - a single-timepoint test repeated over several timepoints;
  - no correction with several comparisons;
  - the progression model on skewed data (Log-transform suggested).
- **Blue (information):** a non-parametric test on normal data (less power); GEE on normal data; GEE small-sample correction; small sample for the normality test; sphericity violation (Greenhouse-Geisser applied).

### 5.7 Reading the results

Results are shown in five tabs.

**📈 Graph** — see Section 5.8.

**🔬 Multiple comparisons** — one row per comparison. Significant rows are highlighted in green. A CSV download is available.

| Column | Meaning |
| :--- | :--- |
| Timepoint Weeks | Week of the comparison (not shown for the progression model). |
| Effect | Progression model only: *Level difference at week c* or *Rate difference per week*. |
| Group A / Group B | A = reference (first selected group). |
| Difference (B − A) | Mean of B minus mean of A (or the model estimate). Positive = B higher. |
| % difference, % CI | Progression model with Log-transform. |
| SE | Standard error (model-based contrasts, progression). |
| 95 % CI low / high | Confidence interval of the difference, **not adjusted** for multiple comparisons. Empty for rank-based tests and Tukey/Games-Howell. |
| Statistic | t, z or U, depending on the test (not shown for model contrasts). |
| p (unadjusted) | Raw p of this single comparison. Do not use it to claim significance. |
| p (adjusted) | **Use this value.** It applies the selected correction; for Tukey/Games-Howell it is their own adjusted p. |
| Summary | Prism-style: `ns`, `*` p < 0.05, `**` p < 0.01, `***` p < 0.001, `****` p < 0.0001. |
| Significant | Yes when the adjusted p < α. |

**📋 Model effects** — the overall tests or model terms for the chosen test.

- RM ANOVA: Group, Time and Time × Group with F, df, p and η²p (≈ 0.01 small, 0.06 medium, ≥ 0.14 large).
- Mixed-effects and GEE: Wald χ², df and p.
- Progression model: estimate, SE, z and p for every fixed-effect term, with age terms per week.
- Single-timepoint multi-group tests: one row per timepoint (F, Welch F or H).
- A direct two-group test has no table here.

**✅ Assumptions** — normality (test, p, skew, n, CLT override), Levene (worst timepoint), design balance with a list of animals that miss timepoints, and sphericity.

**📝 Methods text** — a ready-made paragraph that names the exact test, model structure, post-hoc test, correction, confidence intervals and α. Review and adapt it before you put it in a manuscript.

### 5.8 Graph options and what they show

The graph section reruns on its own, so changing a graph option does not recalculate the statistics.

| Option | What it shows |
| :--- | :--- |
| **Line Plot** | Group mean per week, joined by lines, with ± SEM error bars (optional). Best for longitudinal progression. |
| **Bar Plot** | Group means per week as grouped bars, with ± SEM (optional). Best for comparing a few timepoints. |
| **Box Plot** | Distribution of the per-animal values per week: median, quartiles and whiskers. *Show all data points* overlays each animal. Shows spread and outliers. |
| **Violin Plot** | Distribution shape (density) with an inner box. Shows skew and bimodality. |
| **Show significance on plot** | Stars from the **adjusted** p-values above each week. Only for 2-group comparisons; with 3+ groups, see the Multiple comparisons tab. |
| **Show fitted progression trend** | Progression model only: dashed lines of the model's average (fixed-effects) curve per group. These are the curves that the level and rate tests compare. |
| Label every timepoint | One X tick per selected week. |
| Custom X-axis range | Manual X limits. |
| **Log-scale Y axis** | Logarithmic spacing in original units; equal % differences look equally large. Only for strictly positive values. |

**Notes.**

- All graphs use **one value per animal per week** (trials already averaged). Mean ± SEM is calculated over animals.
- With Log-transform, the graph still shows raw values. The transform affects only the statistics.
- To save a single graph, use the camera icon in the graph toolbar.

### 5.9 Batch export

**📦 Batch export — all measurements in this sheet** renders every selected measurement of the current sheet (2 parallel workers on the cloud server) and creates a ZIP file with:

- `<measurement>.png`: 300-dpi line plot of mean ± SEM per group, with stars (2 groups) and dashed trend lines (progression model). The size follows the plot width and height sliders.
- `statistics_summary.csv`: every comparison of every measurement, with `Measurement` and `Test` columns.

**Rules.**

- The export uses the current groups, timepoints, correction and α. With **Auto**, the recommended test is chosen **separately for each measurement**. With a specific test, that test is used for all measurements.
- For the progression model, Log-transform follows the sheet type: on for SD/CV sheets.
- **Primary outcomes:** select only the measurements you planned to test. The column `p_corr_all_measurements` adjusts the raw p-values with the chosen correction across **all comparisons of all selected measurements**. Fewer, pre-chosen outcomes give more power.

### 5.10 Radar Profile tab

The radar chart shows a multivariate "fingerprint" of each group at **one timepoint**.

- Select a sheet, **at least 3 measurements**, the groups and one timepoint.
- Each axis is one measurement. Each coloured polygon is one group.
- Values are averaged per **animal** first and then per group, as in the statistics. Animals with more trials therefore do not count more.
- **Normalize (proportional to maximum):** each measurement is divided by its highest group mean, so the highest group reaches 1.0 and the ratios between groups are kept. This puts degrees and metres on one scale. Normalization is meaningful only for measurements with positive values.
- The radar chart is **descriptive only**; it has no statistical test.

---

## 6. Time-Series Analysis pages

There are two pages with the same functions: one reads Excel files, and one reads Parquet/HDF5 files.

### 6.1 Loading files

- **Upload files** by drag and drop in the sidebar. A counter shows how many files are loaded. The limit is **20 files** per page; above it the page stops and offers **🗑️ Remove All Files (Start Over)**.
- The Parquet page reads single `.parquet` files (one sheet named `Data (Parquet)`) and `.h5`/`.hdf5` files (one sheet per key). To use a multi-sheet ZIP from the converter, unzip it and upload the Parquet files.
- Excel files are read with the fast `calamine` engine, with `openpyxl` as fallback. Results are cached for 30 minutes (up to 50 files).

### 6.2 Single-file mode

- Select a file and a sheet (for example `Kinematics` or `Positions (used)`).
- **📈 Chart tab:** X = `Time` (fixed); select one or more Y columns.

  | Chart type | What it shows |
  | :--- | :--- |
  | Line | Values over time; best for continuous signals. |
  | Scatter | Individual frames over time, without interpolation lines. |
  | Bar | Value per frame as bars. |
  | Polar (Angles) | Angle as direction and time as radius. This avoids false jumps when an angle wraps from 359° to 0°. |
  | Density Heatmap | Where values concentrate over time (50 × 30 bins, one panel per measurement). |
  | Box Plot | Distribution (median, quartiles, outliers) of each selected measurement, without the time axis. |

  **Noise Reduction (Rolling Avg):** a trailing moving average over 1–50 frames (Line chart only). The first *window − 1* frames are empty.
  You can choose a colour for each measurement.
- **🧮 Statistics tab:** recording duration (last − first `Time`, Kinematics sheet), descriptive statistics (count, mean, SD, min, quartiles, max) of the selected or all measurements, and a **Pearson correlation matrix**. A value of +1 means the measurements rise together, and −1 means they move in opposite directions.

### 6.3 Compare-multiple-files mode

- Select 2 or more files. The app finds **sheets common to all files**, then **numeric columns common to all files**.
- For the Kinematics sheet, the duration of each recording is shown.
- Chart types: Line, Scatter, Polar, Box. There is one colour per file, and each legend entry reads `file | measurement`.

### 6.4 Sidebar

- **🧹 Clear Server Cache:** frees cached files.

---

## 7. Excel → Parquet/HDF5 Converter

1. **Source:** upload one or more `.xlsx`/`.xls` files.
2. **Format:** Parquet or HDF5.
3. **🚀 Start Conversion.** A progress bar and a log show each file.
4. **⬇️ Download Converted Files (ZIP):** one ZIP with all converted files (`converted_files_parquet.zip` or `converted_files_hdf5.zip`).

| Output | Single-sheet Excel | Multi-sheet Excel |
| :--- | :--- | :--- |
| Parquet | `<name>.parquet` | `<name>_parquet.zip` containing `<name>_<sheet>.parquet` per sheet |
| HDF5 | `<name>.h5` with one key per sheet | same (spaces and hyphens in sheet names become `_`) |

For every sheet with a `Time` column, the summary rows of filtered files are removed (Section 4.2), and text columns that are fully numeric are converted to numbers.

Parquet files load up to about 50× faster than Excel files and use less memory. A converted merged file can be uploaded to the Kinematics Analyzer as a `.zip`; each sheet is then named `<name>_<sheet>`.

---

## 8. Measurement dictionary

Units are those shown with *Distance units = Meters*. With *Millimeters*, `(m)`, `(m/s)` and `(m/s²)` become `(mm)`, `(mm/s)` and `(mm/s²)`. Left/Right refer to the side of the animal. The "right view" camera image is upside down; filtering v2 corrects this.

### 8.1 Heights and clearances (vertical position above the floor)

| Measurement | Marker | Description |
| :--- | :--- | :--- |
| Toe Clearance Forepaw (Left/Right) (m) | Front toe | Height of the front toe above the floor. Can be slightly negative from tracking or floor-estimate error. |
| Toe Clearance Hindpaw (Left/Right) (m) | Hind toe | Height of the hind toe above the floor. |
| Iliac Crest Height (Left/Right) (m) | PSIS (posterior superior iliac spine) | Height of the pelvis. |
| Hip Height (Left/Right) (m) | Hip | Height of the hip joint. |
| Tail Base Height (Left/Right) (m) | Tail base (left or right view) | Height of the tail base. |
| Shoulder Height (Left/Right) (m) | Upper shoulder | Height of the shoulder. |
| Nose Height (m) | Nose (left view in v2) | Height of the nose. Older saved sheets mix camera views. |
| Tail Tip Height (m) | Tail tip (left view in v2) | Height of the tail tip. Older saved sheets mix camera views. |
| Front/Hind Paw Drag (Left/Right) | Front/hind toe | Absolute vertical toe position, used to detect dragging (no unit in the name, in metres). |
| Head Rotation | Jaw | Vertical position of the jaw marker (no unit in the name). |

### 8.2 Distances

| Measurement | Markers | Description |
| :--- | :--- | :--- |
| Step Width (Hind) (m) | Left and right hind paw | Lateral distance between the hind paws. |
| Step Width (Front) (m) | Left and right front paw | Lateral distance between the front paws. |
| Step Length (Left/Right) (m) | Front and hind paw on the same side | Distance between the front and hind paw. |
| Protraction/Retraction (Left/Right) (m) | Hind toe and PSIS | Euclidean distance from the hind toe to the pelvis: how far the leg reaches forward or back. This is a **length, not an angle**. |

### 8.3 Joint angles (degrees, angle at the middle marker)

| Measurement | Markers (middle = vertex) |
| :--- | :--- |
| Hip Angle (Left/Right) (º) | PSIS – **Hip** – Knee |
| Knee Angle (Left/Right) (º) | Hip – **Knee** – Ankle |
| Ankle Angle (Left/Right) | Knee – **Ankle** – Hind toe |
| Shoulder Angle (Left/Right) | Upper shoulder – **Lower shoulder** – Elbow |
| Elbow Angle (Left/Right) | Lower shoulder – **Elbow** – Wrist |
| Wrist Angle (Left/Right) | Elbow – **Wrist** – Front toe |
| Tail Angle (Side View) (º) | Tail base – **Tail centre** – Tail tip |

### 8.4 Paw kinematics (swing phase only)

For each paw (Front/Hind × Left/Right): `Vx`, `Vy` (horizontal and vertical velocity, m/s), `Speed` (magnitude, m/s), `Ax`, `Ay` (acceleration components, m/s²) and `|Acc|` (magnitude, m/s²). The names are `Front Right Speed (m/s)` (groundwalk) or `Front Right Paw Speed (m/s)` (gridwalk and merged files). Only frames above the swing threshold are included (Section 3.2, step 7). Vx, Vy, Ax and Ay are signed, so do not use their CV.

### 8.5 Quality-control columns (hidden from analysis)

| Column | Meaning | Good value |
| :--- | :--- | :--- |
| QC Tracked Frames (%) | Frames where all four paws are tracked | High (≥ 70 %). About 100 % on v1 files, where it is not meaningful. |
| QC Hind Ahead of Front (%) | Frames with a hind paw ahead of the front paw on the same side | Near 0 |
| QC Step Length SD (Left/Right) (m) | Variation of step length | Clearly above 0 |

### 8.6 Statistic sheets of the merged file

Each sheet summarises the frames of one recording into one value per measurement.

| Sheet | Definition |
| :--- | :--- |
| Mean | Arithmetic mean over the frames. |
| Std | Standard deviation over the frames (within-recording variability). |
| Median | Median over the frames. |
| Min / Max | Smallest / largest value. |
| Max_Normalized_Mean | Mean of the values divided by the recording's maximum (0–1). |
| CV | Std / Mean, as a ratio (not %). Not meaningful for measurements that cross zero. |
| Time Duration | Duration of the movement window in seconds. Useful as a covariate (walking speed). |

---

## 9. Limitations

**Statistics**

- Confidence intervals are **not adjusted** for multiple comparisons. Rank-based tests and Tukey/Games-Howell have no confidence intervals.
- RM ANOVA removes animals with any missing timepoint. Prefer the mixed-effects model when animals have dropped out.
- GEE p-values can still be slightly optimistic with very few animals, even with the bias-reduced correction.
- Single-timepoint tests over several weeks ignore that the same animals are measured repeatedly.
- The progression model assumes one shared curvature (age²) for all groups. Groups differ only in level and linear rate.
- Log-transform is available only in the progression model, and only for strictly positive values.
- Batch export with *Auto* can use a different test for each measurement. Check the `Test` column of the CSV.
- The normality test has low power below 20 residuals; a "normal" result there is weak evidence.
- Statistical significance is not the same as biological relevance. Report effect sizes and confidence intervals.

**Data and variable extraction**

- Trial-ID mode needs the timepoint as `44W` or `T2`. Other formats (for example `Day5`, `W44` alone) give no timepoint.
- In Metadata mode, every sheet needs the subject and timepoint columns.
- Group, timepoint and sex are read from the first sheet only.
- Unit conversion covers only columns with `(m)`, `(m/s)`, `(m/s²)` or `(m/s^2)` in the name. Paw Drag and Head Rotation are not converted.
- Radar normalization assumes positive values. The radar chart has no statistics.

**Upstream data (v1 calculation files)**

- Filtering v2 cannot undo what the v1 calculation script did **before** smoothing. Gaps filled with the last known position look like a frozen paw; reduced tracking jumps can remain as speed spikes (for example 1.84 m/s from a 30 mm one-frame label swap) and stay in the Mean and Max of paw speed.
- Saved v1 Kinematics sheets mix camera views for Nose Height and Tail Tip Height. Filtering v2 always rebuilds them from the left view.
- Run filtering v2 on **every** file of an experiment, so that all values come from the same formulas.

**Deployment**

- Streamlit Cloud (free tier) has about 1 GB of memory: the time-series pages accept at most 20 files, and batch export uses 2 workers. For large studies use the local `prod_pro` version.

---

## 10. Troubleshooting and FAQ

| Message or problem | Cause | Action |
| :--- | :--- | :--- |
| "Could not find an 'Ids' column to extract from." | Trial-ID mode without an `Ids` column. | Use **Metadata columns** mode, or rename the ID column to `Ids`. |
| "Pick at least one group column." | Metadata mode without a group column. | Select at least one group column. |
| IDs listed under *No group tag matched* | No tag matches a whole ID part. | Check the spelling, separators (`_`) and the tag table. |
| IDs listed under *No timepoint found* | No `44W`/`T2` part in the ID. | Fix the IDs, or use Metadata mode. |
| "Animals labelled with different groups in different rows" | Typo in a group column. | Fix the file, or exclude the listed sessions. |
| "N subject(s) belong to more than one selected group" | Overlapping groups (for example `Transgenic` + `TG Female`). | Select groups that do not share animals. |
| "At least one group has fewer than 2 subjects" | Too few animals. | Add groups or timepoints, or check exclusions. |
| "Repeated-measures models need at least 3 subjects per group" | Too few animals for a longitudinal model. | Use *Auto* (tests each timepoint) or a single-timepoint test. |
| "…has the same value in every selected session" | Constant measurement. | Nothing to test; choose another measurement. |
| "No numeric data for this measurement in at least two of the selected groups." | Empty or non-numeric column for these groups. | Check the Data tab. In Metadata mode, check that the sheet has the subject and timepoint columns. |
| "…failed: the values do not vary within subjects or groups…" | RM ANOVA cannot calculate an error term. | Use GEE or a non-parametric test. |
| "Autoregressive working correlation failed to fit; fell back to Exchangeable." | AR(1) correlation ≈ 1. | Information only; the result is valid. |
| "The progression model did not fully converge" | Difficult data or too few animals. | Treat p-values with caution; try Log-transform or fewer covariates. |
| CV warning on negative values | The measurement crosses zero. | Use the SD sheet. |
| Left/right disagreement warning | The two sides measure different things. | Analyse each side separately. |
| Time-series page: "column 'Time' was not found" | The file or sheet has no `Time` column. | Use a per-recording filtered file and the Kinematics or Positions sheet. |
| "Capacity Exceeded!" in a time-series page | More than 20 files uploaded. | Remove files, or use **Remove All Files (Start Over)**. |

**FAQ**

- **Do the results match GraphPad Prism?** The tests, model-based contrasts (pooled repeated-measures error), mixed-effects analysis for missing data, corrections and star notation follow Prism 8+. Small numerical differences can come from different optimizers.
- **Why did Auto pick a mixed-effects model or GEE instead of RM ANOVA?** RM ANOVA needs complete data and normal residuals. With missing timepoints, Auto picks the mixed-effects model; with non-normal residuals, it picks GEE. The Assumptions tab shows which check failed.
- **When should I use the progression model?** When you follow the same animals over many weeks and expect a gradual change. One rate test replaces many per-week tests, so slow phenotypes are easier to detect.
- **Should I pool sexes?** Use *Adjust for sex* in the progression model to compare genotypes with both sexes pooled. Use the combined groups (for example `WT F`, `TG F`) to test sexes separately.
- **Can I save a single graph?** Yes: use the camera icon in the graph toolbar, or Batch export for 300-dpi PNGs.

---

## 11. Glossary

| Term | Meaning |
| :--- | :--- |
| Session | One recording of one animal at one timepoint (may contain several trials). |
| Trial | One run through the apparatus. Trials of a session are averaged. |
| Reference group (Group A) | The first selected group; all differences are B − A. |
| Omnibus test | Overall test of whether any difference exists (F, χ², H). |
| Post-hoc test | Pairwise comparisons after the omnibus test. |
| SEM | Standard error of the mean = SD / √n (n = animals). |
| CI | Confidence interval: a range of plausible values for the difference. |
| FWER / FDR | Family-wise error rate (probability of ≥ 1 false positive) / false discovery rate (expected share of false positives). |
| REML | Restricted maximum likelihood, the fitting method of the mixed models. |
| Sandwich SE | Robust standard error used by GEE. |
| Sphericity | Equal variances of the differences between all pairs of timepoints (RM ANOVA assumption). |
| MAD | Median absolute deviation, a robust measure of spread. |
| Swing / stance | Phase when the paw moves through the air / rests on the ground. |
| PSIS | Posterior superior iliac spine (pelvis marker). |
| Cohort | Animals that started the experiment together and were recorded on the same days. |
