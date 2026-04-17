import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re
import pingouin as pg
import traceback
import statsmodels.formula.api as smf

# Suppress warnings

import warnings
from statsmodels.tools.sm_exceptions import ConvergenceWarning

warnings.simplefilter('ignore', ConvergenceWarning)

# --- PLOTLY STATS FUNCTION (For Box Plots in Tab 5) ---
def add_plotly_significance_brackets(fig, df, posthocs_df, x_col, y_col, text_color="black"):
    """
    Custom function to draw statistical brackets and asterisks on Plotly grouped plots.
    Assumes exactly 2 groups are being compared.
    """
    if posthocs_df is None or posthocs_df.empty: 
        return fig

    p_col = next((c for c in posthocs_df.columns if 'p-' in c.lower() or 'p_' in c.lower() or c.lower() == 'pval' or c.lower() == 'p'), None)
    if not p_col: 
        return fig

    y_max_overall = df[y_col].max()
    y_min_overall = df[y_col].min()
    y_range = y_max_overall - y_min_overall
    if y_range == 0: y_range = y_max_overall
    
    step_y = y_range * 0.05  
    
    for _, row in posthocs_df.iterrows():
        if x_col not in row: continue
        
        x_val = row[x_col]
        tp_data = df[df[x_col] == x_val]
        if tp_data.empty: continue
        
        y_max_tp = tp_data[y_col].max()
        bracket_y = y_max_tp + step_y
        
        raw_pval = str(row[p_col])
        text = raw_pval
        num_str = raw_pval.replace('<', '').replace('>', '').replace('=', '').strip()
        
        try:
            val = float(num_str)
            if val < 0.001: text = "***"
            elif val < 0.01: text = "**"
            elif val < 0.05: text = "*"
            else: text = "ns"
        except ValueError:
            pass 
        
        try:
            x_center = float(x_val)
            x0 = x_center - 0.15 
            x1 = x_center + 0.15 
            
            # Apply user-selected color to brackets and text
            fig.add_shape(type="line", x0=x0, x1=x0, y0=bracket_y, y1=bracket_y + step_y * 0.5, line=dict(color=text_color, width=1.5))
            fig.add_shape(type="line", x0=x1, x1=x1, y0=bracket_y, y1=bracket_y + step_y * 0.5, line=dict(color=text_color, width=1.5))
            fig.add_shape(type="line", x0=x0, x1=x1, y0=bracket_y + step_y * 0.5, y1=bracket_y + step_y * 0.5, line=dict(color=text_color, width=1.5))
            
            fig.add_annotation(
                x=x_center, y=bracket_y + step_y * 1.5, text=text, showarrow=False, font=dict(size=14, color=text_color, family="Arial")
            )
        except ValueError:
            continue 
            
    return fig
# ---------------------------------

# --- CONFIGURATION ---
st.set_page_config(layout="wide") 
st.title("🐁 Kinematics Longitudinal Analyzer")

column_rename_map = {
    "Step Width (Hind)": "Step Width (Hind) (m)",
    "Step Width (Front)": "Step Width (Front) (m)",
    "Step Length (Left)": "Step Length (Left) (m)",
    "Step Length (Right)": "Step Length (Right) (m)",
    "Toe Clearance Forepaw (Right)": "Toe Clearance Forepaw (Right) (m)",
    "Toe Clearance Hindpaw (Right)": "Toe Clearance Hindpaw (Right) (m)",
    "Toe Clearance Forepaw (Left)": "Toe Clearance Forepaw (Left) (m)",
    "Toe Clearance Hindpaw (Left)": "Toe Clearance Hindpaw (Left) (m)",
    "Iliac Crest Height (Right)": "Iliac Crest Height (Right) (m)",
    "Iliac Crest Height (Left)": "Iliac Crest Height (Left) (m)",
    "Hip Height (Right)": "Hip Height (Right) (m)",
    "Hip Height (Left)": "Hip Height (Left) (m)",
    "Tail Base Height (Right)": "Tail Base Height (Right) (m)",
    "Tail Base Height (Left)": "Tail Base Height (Left) (m)",
    "Nose Height": "Nose Height (m)",
    "Tail Tip Height": "Tail Tip Height (m)",
    "Shoulder Height (Right)": "Shoulder Height (Right) (m)",
    "Shoulder Height (Left)": "Shoulder Height (Left) (m)",
    "Protraction/Retraction (Right)": "Protraction/Retraction (Right) (º)",
    "Protraction/Retraction (Left)": "Protraction/Retraction (Left) (º)",
    "Hip Angle (Right)": "Hip Angle (Right) (º)",
    "Knee Angle (Right)": "Knee Angle (Right) (º)",
    "Hip Angle (Left)": "Hip Angle (Left) (º)",
    "Knee Angle (Left)": "Knee Angle (Left) (º)",
    "Tail Angle (Side View)": "Tail Angle (Side View) (º)",
    "Front Right Ax (m/s^2)": "Front Right Ax (m/s²)",
    "Front Right Ay (m/s^2)": "Front Right Ay (m/s²)",
    "Front Right |Acc| (m/s^2)": "Front Right |Acc| (m/s²)",
    "Front Left Ax (m/s^2)": "Front Left Ax (m/s²)",
    "Front Left Ay (m/s^2)": "Front Left Ay (m/s²)",
    "Front Left |Acc| (m/s^2)": "Front Left |Acc| (m/s²)",
    "Hind Right Ax (m/s^2)": "Hind Right Ax (m/s²)",
    "Hind Right Ay (m/s^2)": "Hind Right Ay (m/s²)",
    "Hind Right |Acc| (m/s^2)": "Hind Right |Acc| (m/s²)",
    "Hind Left Ax (m/s^2)": "Hind Left Ax (m/s²)",
    "Hind Left Ay (m/s^2)": "Hind Left Ay (m/s²)",
    "Hind Left |Acc| (m/s^2)": "Hind Left |Acc| (m/s²)"
}

# --- 1. FILE UPLOAD ---
uploaded_file = st.file_uploader("Upload your cleaned Descriptive Statistics Excel file", type=['xlsx'])

if uploaded_file:
    if 'data_dict' not in st.session_state or st.session_state.get('uploaded_filename') != uploaded_file.name:
        xls = pd.ExcelFile(uploaded_file)
        sheet_names = xls.sheet_names
        st.session_state.data_dict = {
            sheet: pd.read_excel(xls, sheet_name=sheet).rename(columns=column_rename_map) 
            for sheet in sheet_names
        }
        st.session_state.sheet_names = sheet_names
        st.session_state.uploaded_filename = uploaded_file.name
        if 'run_stats' in st.session_state:
            del st.session_state['run_stats']

    data_dict = st.session_state.data_dict
    sheet_names = st.session_state.sheet_names

    # --- SIDEBAR SETTINGS ---
    st.sidebar.header("🎨 Custom Group Colors")
    color_map = {}
    if 'mapping_df' in st.session_state:
        extracted_groups = [g for g in st.session_state.mapping_df['Group'].unique() if g != "Unknown"]
        default_colors = px.colors.qualitative.Plotly + px.colors.qualitative.D3
        for i, grp in enumerate(sorted(extracted_groups)):
            default_hex = default_colors[i % len(default_colors)]
            color_map[grp] = st.sidebar.color_picker(f"{grp} Color", default_hex, key=f"color_{grp}")
            
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Global Plot Settings")
    annotation_color = st.sidebar.color_picker(
        "Significance Annotation Color", 
        "#000000", 
        help="Change this to White (#FFFFFF) if you are using Streamlit's Dark Mode so the asterisks are visible."
    )
    # ----------------------------------------

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Data Viewer", 
        "🆔 ID Overview", 
        "🧪 Experimental Groups Setup", 
        "🧮 Statistical Analysis ➡️ Longitudinal Plotting 📈",
        "🕸️ Radar Plots"
    ])

    # --- TAB 1: DATA VIEWER ---
    with tab1:
        st.subheader("View Individual Sheets")
        selected_sheet = st.selectbox("Select a sheet to display:", sheet_names, key="viewer_sheet_select")
        st.dataframe(data_dict[selected_sheet], width='stretch')

    # --- TAB 2: ID OVERVIEW ---
    with tab2:
        st.subheader("Extracted IDs")
        first_sheet_df = data_dict[sheet_names[0]]
        if 'Ids' in first_sheet_df.columns:
            unique_ids = first_sheet_df['Ids'].unique()
            st.write(f"**Total unique rows/trials found:** {len(unique_ids)}")
            st.dataframe(pd.DataFrame(unique_ids, columns=["Subject IDs"]), width='stretch')
        else:
            st.error("Could not find an 'Ids' column. Please check your Excel file format.")

    # --- TAB 3: EXPERIMENTAL GROUPS SETUP ---
    with tab3:
        st.subheader("Define Groups and Parse Timepoints")
        st.markdown("""
        Manually define your experimental groups below. 
        * **Group Name**: The clean name displayed on plots.
        * **Tag in ID**: The exact text snippet the program should look for in the Subject ID.
        """)
        
        if 'group_definitions' not in st.session_state:
            st.session_state.group_definitions = pd.DataFrame({
                "Group Name": ["Wildtype", "Transgenic", "WT Male", "WT Female", "TG Male", "TG Female"],
                "Tag in ID": ["WT", "TG", "WT_M", "WT_F", "TG_M", "TG_F"]
            })
        
        edited_groups = st.data_editor(
            st.session_state.group_definitions,
            num_rows="dynamic",
            width='stretch',
            hide_index=True,
            key="groups_editor"
        )

        if st.button("Extract Variables from IDs", type="secondary", key="extract_vars_btn"):
            if 'unique_ids' not in locals():
                first_sheet_df = data_dict[sheet_names[0]]
                if 'Ids' in first_sheet_df.columns:
                    unique_ids = first_sheet_df['Ids'].unique()
                else:
                    st.error("Could not find an 'Ids' column to extract from.")
                    st.stop()

            valid_groups = edited_groups.dropna(how='all').copy()
            valid_groups["Tag in ID"] = valid_groups["Tag in ID"].astype(str).str.strip()
            valid_groups["Group Name"] = valid_groups["Group Name"].astype(str).str.strip()
            valid_groups = valid_groups[valid_groups["Tag in ID"] != ""]
            valid_groups['tag_length'] = valid_groups['Tag in ID'].apply(len)
            valid_groups = valid_groups.sort_values('tag_length', ascending=False).drop(columns=['tag_length'])

            def extract_timepoint(id_str):
                # 1st Check: Look for format like "4W", "12w", etc.
                match_w = re.search(r'(\d+)[Ww]', str(id_str))
                if match_w: 
                    return int(match_w.group(1))
                
                # 2nd Check: Look for format like "T1", "t13", etc.
                match_t = re.search(r'[Tt](\d+)', str(id_str))
                if match_t: 
                    return int(match_t.group(1))
                
                return None
            
            def extract_subject_id(id_str):
                tokens = str(id_str).split('_')
                for i, token in enumerate(tokens):
                    # Stop combining chunks when we hit the timepoint token (like "12W" or "T1")
                    if re.fullmatch(r'(?:[Ww]eek\s*)?\d+\s*[Ww]|[Ww]\s*\d+|[Tt]\s*\d+|\d+\s*[Tt]', token):
                        return "_".join(tokens[:i])
                
                # Fallback just in case
                return tokens[0]

            mapping_records = []
            for id_str in unique_ids:
                timepoint = extract_timepoint(id_str)
                subject_id = extract_subject_id(id_str)
                id_upper = str(id_str).upper()
                
                matched_groups = []
                for _, row in valid_groups.iterrows():
                    tag = row["Tag in ID"].upper()
                    if tag and tag in id_upper:
                        matched_groups.append(row["Group Name"])
                
                if not matched_groups:
                    matched_groups.append("Unknown")
                    
                for grp in matched_groups:
                    mapping_records.append({
                        "Ids": id_str,
                        "Timepoint_Weeks": timepoint,
                        "Subject_ID": subject_id,
                        "Group": grp
                    })
            
            mapping_df = pd.DataFrame(mapping_records)
            st.session_state.mapping_df = mapping_df
            st.session_state.group_definitions_final = valid_groups 
            
            st.success("Variables extracted successfully! You can now choose your group colors in the sidebar.")
            st.rerun()
        
        # --- NEW: EXCLUDE SUBJECTS UI ---
        if 'mapping_df' in st.session_state:
            st.markdown("### 🚫 Exclude Specific Subjects")
            all_extracted_subjects = sorted(st.session_state.mapping_df['Subject_ID'].dropna().unique())
            
            # Use a multiselect so the user can dynamically drop subjects
            subjects_to_exclude = st.multiselect(
                "Select any subjects you want to completely remove from all plots and stats (e.g., outliers, dropouts):", 
                options=all_extracted_subjects,
                key="exclude_subjects_ui"
            )
            
            # Create a clean copy of the dataframe with those subjects removed
            map_df_clean = st.session_state.mapping_df.copy()
            if subjects_to_exclude:
                map_df_clean = map_df_clean[~map_df_clean['Subject_ID'].isin(subjects_to_exclude)]
                st.warning(f"Excluded {len(subjects_to_exclude)} subjects from the dataset.")
            # ---------------------------------

            st.markdown("### 📋 Group Summary (N)")
            if not map_df_clean.empty and 'Group' in map_df_clean.columns:
                # IMPORTANT: Use map_df_clean here instead of st.session_state.mapping_df
                group_counts = map_df_clean[map_df_clean['Group'] != 'Unknown'].groupby('Group')['Subject_ID'].nunique().reset_index()
                if not group_counts.empty:
                    group_counts.columns = ['Experimental Group', 'Number of Unique Subjects (N)']
                    st.dataframe(group_counts, width='stretch', hide_index=True)

        # if 'mapping_df' in st.session_state:
        #     map_df_clean = st.session_state.mapping_df
        #     st.markdown("### 📋 Group Summary (N)")
        #     if not map_df_clean.empty and 'Group' in map_df_clean.columns:
        #         group_counts = map_df_clean[map_df_clean['Group'] != 'Unknown'].groupby('Group')['Subject_ID'].nunique().reset_index()
        #         if not group_counts.empty:
        #             group_counts.columns = ['Experimental Group', 'Number of Unique Subjects (N)']
        #             st.dataframe(group_counts, width='stretch', hide_index=True)

        # --- DEBUGGING BLOCK ---
        if 'mapping_df' in st.session_state:
            with st.expander("🚨 Troubleshooting: Unmatched IDs & Missing Timepoints", expanded=True):
                debug_df = st.session_state.mapping_df
                
                # Filter for the problem rows
                unknown_groups = debug_df[debug_df['Group'] == 'Unknown']
                missing_timepoints = debug_df[debug_df['Timepoint_Weeks'].isna()]
                
                col_d1, col_d2 = st.columns(2)
                
                with col_d1:
                    st.markdown("#### ❌ Failed Group Match")
                    st.caption("These IDs didn't contain any of your defined tags.")
                    if unknown_groups.empty:
                        st.success("All IDs successfully mapped to groups!")
                    else:
                        # Dropping duplicates so we only see the unique IDs that failed
                        st.dataframe(unknown_groups[['Ids', 'Subject_ID']].drop_duplicates(), width='stretch', hide_index=True)
                        
                with col_d2:
                    st.markdown("#### ⏱️ Failed Timepoint Extraction")
                    st.caption("The regex could not find a valid week/time in these IDs.")
                    if missing_timepoints.empty:
                        st.success("All IDs have a valid timepoint!")
                    else:
                        st.dataframe(missing_timepoints[['Ids', 'Group']].drop_duplicates(), width='stretch', hide_index=True)
        # -----------------------

# --- TAB 4: LONGITUDINAL ANALYSIS & STATS ---
    with tab4:
        st.subheader("Longitudinal Progression & Statistical Analysis")
        
        if 'mapping_df' not in st.session_state:
            st.warning("⚠️ Please go to the 'Experimental Groups Setup' tab and extract variables first.")
        else:
            mapping_df = st.session_state.mapping_df.copy()
            if st.session_state.get('exclude_subjects_ui'):
                mapping_df = mapping_df[~mapping_df['Subject_ID'].isin(st.session_state.exclude_subjects_ui)]
            
            # --- SECTION 1: DATA SELECTION ---
            col1, col2 = st.columns(2)
            with col1:
                plot_sheet = st.selectbox("Select Statistic (Sheet):", sheet_names, key="plot_sheet")
            
            df_to_plot = data_dict[plot_sheet]
            numeric_cols = [col for col in df_to_plot.columns if col != 'Ids']
            
            with col2:
                plot_metric = st.selectbox("Select Measurement to Analyze:", numeric_cols, key="plot_metric_select")
            
            all_groups = sorted([g for g in mapping_df['Group'].unique() if g != "Unknown"])
            all_timepoints = sorted(mapping_df['Timepoint_Weeks'].dropna().unique())
            
            col_grp, col_tp = st.columns(2)
            with col_grp:
                selected_plot_groups = st.multiselect(
                    "Select EXACTLY 2 Groups for ANOVA & Plotting:", 
                    all_groups, 
                    default=all_groups[:2] if len(all_groups) >= 2 else all_groups,
                    key="plot_groups_multiselect"
                )
            with col_tp:
                selected_plot_timepoints = st.multiselect(
                    "Select Timepoints to Display:", 
                    all_timepoints, 
                    default=all_timepoints,
                    key="plot_tps_multiselect"
                )

            if len(selected_plot_groups) != 2:
                st.error("🚨 Statistical significance requires exactly 2 groups selected.")
            elif len(selected_plot_timepoints) < 2:
                st.error("🚨 Longitudinal tests require at least 2 timepoints selected.")
            else:
                # --- DATA PREPARATION (Strictly automated, no imputation UI) ---
                mapping_filtered = mapping_df[
                    (mapping_df['Group'].isin(selected_plot_groups)) & 
                    (mapping_df['Timepoint_Weeks'].isin(selected_plot_timepoints))
                ]
                
                merged_raw = pd.merge(df_to_plot[['Ids', plot_metric]], mapping_filtered, on='Ids')
                merged_raw[plot_metric] = pd.to_numeric(merged_raw[plot_metric], errors='coerce')
                
                # Drop rows where the metric cell is truly empty, then calculate a single mean per mouse per week
                final_df = merged_raw.dropna(subset=[plot_metric]).groupby(['Subject_ID', 'Group', 'Timepoint_Weeks'])[plot_metric].mean().reset_index()


                # --- SMART STATS ENGINE (Collapsible) ---
                with st.expander("📊 Statistical Tables & Assumptions (Click to Expand)", expanded=False):
                    
                    # 1. Check Normality (Shapiro-Wilk)
                    norm_test = pg.normality(data=final_df, dv=plot_metric, group='Group')
                    is_normal = norm_test['normal'].all() if not norm_test.empty else True
                    
                    # 2. Check Balance (Missing Data)
                    expected_tps = len(selected_plot_timepoints)
                    subj_tps = final_df.groupby('Subject_ID')['Timepoint_Weeks'].nunique()
                    is_balanced = (subj_tps == expected_tps).all()

                    # --- NEW: DYNAMIC PIPELINE ANNOUNCER ---
                    st.markdown("### 1. Model Assumptions & Pipeline Selection")
                    
                    col_chk1, col_chk2 = st.columns(2)
                    with col_chk1:
                        if is_normal:
                            st.success("✔️ **Normality (Shapiro-Wilk):** Passed")
                        else:
                            st.error("⚠️ **Normality (Shapiro-Wilk):** Violated (Skewed)")
                            
                    with col_chk2:
                        if is_balanced:
                            st.success("✔️ **Design Balance:** Passed (No missing data)")
                        else:
                            st.error("⚠️ **Design Balance:** Violated (Missing timepoints)")
                            
                            # --- NEW: Explicitly show which IDs are missing timepoints ---
                            expected_tps_list = sorted(selected_plot_timepoints)
                            subj_tps_list = final_df.groupby(['Subject_ID', 'Group'])['Timepoint_Weeks'].agg(list).reset_index()
                            subj_tps_list['Missing_Timepoints'] = subj_tps_list['Timepoint_Weeks'].apply(lambda tps: [t for t in expected_tps_list if t not in tps])
                            
                            incomplete_subjs = subj_tps_list[subj_tps_list['Missing_Timepoints'].str.len() > 0].copy()
                            
                            if not incomplete_subjs.empty:
                                incomplete_subjs['Missing_Timepoints'] = incomplete_subjs['Missing_Timepoints'].apply(lambda x: ", ".join(map(str, x)) + " Weeks")
                                st.dataframe(
                                    incomplete_subjs[['Group', 'Subject_ID', 'Missing_Timepoints']].sort_values(['Group', 'Subject_ID']), 
                                    hide_index=True, 
                                    width='stretch'
                                )
                            # -------------------------------------------------------------

                    st.markdown("---")
                    
                    # Explain exactly what the engine is doing based on the checks
                    if is_normal and is_balanced:
                        st.info("""
                        🚀 **Active Pipeline: A (2-Way Mixed-Design ANOVA)**
                        * **Why?** Your data is normally distributed and perfectly balanced.
                        * **What's happening?** The engine is running a standard Parametric ANOVA. Post-hocs are pairwise simple main effects with a Holm-Bonferroni correction.
                        """)
                    elif is_normal and not is_balanced:
                        st.warning("""
                        🚀 **Active Pipeline: B (Linear Mixed-Effects Model)**
                        * **Why?** Your data is normal, but mice are missing timepoints.
                        * **What's happening?** A standard ANOVA would delete subjects missing later timepoints, causing 'Survivor Bias'. The engine upgraded to an LMM to safely utilize all available data points. Post-hocs are cross-sectional Welch's T-Tests (Holm-corrected).
                        """)
                    else:
                        st.error("""
                        🚀 **Active Pipeline: C (Non-Parametric Analysis)**
                        * **Why?** Your data violates normality assumptions.
                        * **What's happening?** Running an ANOVA on highly skewed data produces invalid p-values. The engine safely fell back to robust, rank-based Mann-Whitney U tests evaluated cross-sectionally (Holm-corrected).
                        """)
                    

                    st.markdown("### 2. Results")
                    display_posthocs = pd.DataFrame()
                    
                    def format_pval(x):
                        if pd.isna(x): return x
                        try:
                            val = float(x)
                            return f"{val:.4f}" if val > 0.0001 else "<0.0001"
                        except:
                            return x

                    # --- DECISION TREE ---
                    if is_normal and is_balanced:
                        # STANDARD PARAMETRIC
                        try:
                            anova_res = pg.mixed_anova(dv=plot_metric, within='Timepoint_Weeks', between='Group', subject='Subject_ID', data=final_df)
                            st.markdown("**2-Way Mixed ANOVA**")
                            for col in ['p_unc', 'p_unc', 'p_val', 'p_GG_corr']:
                                if col in anova_res.columns: anova_res[col] = anova_res[col].apply(format_pval)
                            st.dataframe(anova_res, width='stretch', hide_index=True)
                            
                            post_res = pg.pairwise_tests(dv=plot_metric, within='Timepoint_Weeks', between='Group', subject='Subject_ID', data=final_df, padjust='holm')
                            display_posthocs = post_res[post_res['Contrast'] == 'Timepoint_Weeks * Group'].copy()
                        except Exception as e:
                            st.error(f"ANOVA Failed: {e}")

                    elif is_normal and not is_balanced:
                        # LMM FOR MISSING DATA
                        final_df['_metric_'] = final_df[plot_metric].astype(float)
                        final_df['_time_'] = final_df['Timepoint_Weeks'].astype(str)
                        final_df['_group_'] = final_df['Group'].astype(str)
                        
                        try:
                            md = smf.mixedlm("_metric_ ~ _time_ * _group_", final_df, groups=final_df["Subject_ID"])
                            mdf = md.fit(method='cg')
                            st.markdown("**Linear Mixed-Effects Model (LMM)** *(Best for missing data)*")
                            st.dataframe(mdf.summary().tables[1], width='stretch')
                        except Exception as e:
                            st.error(f"LMM Failed to converge: {e}")

                        # Pairwise Parametric
                        st.markdown("**Pairwise T-Tests (Holm-Corrected for FDR)**")
                        rows = []
                        for tp in selected_plot_timepoints:
                            tp_df = final_df[final_df['Timepoint_Weeks'] == tp]
                            g1 = tp_df[tp_df['Group'] == selected_plot_groups[0]][plot_metric]
                            g2 = tp_df[tp_df['Group'] == selected_plot_groups[1]][plot_metric]
                            if len(g1) > 1 and len(g2) > 1:
                                res = pg.ttest(g1, g2)
                                rows.append({'Timepoint_Weeks': tp, 'Group A': selected_plot_groups[0], 'Group B': selected_plot_groups[1], 'p_unc': res['p_val'].values[0]})
                        if rows:
                            display_posthocs = pd.DataFrame(rows)
                            _, p_corr = pg.multicomp(display_posthocs['p_unc'].values, method='holm')
                            display_posthocs['p_corr'] = p_corr

                    else:
                        # NON-PARAMETRIC
                        st.markdown("**Non-Parametric Pairwise Tests (Mann-Whitney U)**")
                        rows = []
                        for tp in selected_plot_timepoints:
                            tp_df = final_df[final_df['Timepoint_Weeks'] == tp]
                            g1 = tp_df[tp_df['Group'] == selected_plot_groups[0]][plot_metric]
                            g2 = tp_df[tp_df['Group'] == selected_plot_groups[1]][plot_metric]
                            if len(g1) > 1 and len(g2) > 1:
                                res = pg.mwu(g1, g2)
                                rows.append({'Timepoint_Weeks': tp, 'Group A': selected_plot_groups[0], 'Group B': selected_plot_groups[1], 'p_unc': res['p_val'].values[0]})
                        if rows:
                            display_posthocs = pd.DataFrame(rows)
                            _, p_corr = pg.multicomp(display_posthocs['p_unc'].values, method='holm')
                            display_posthocs['p_corr'] = p_corr

                    if not display_posthocs.empty:
                        df_show = display_posthocs.copy()
                        for col in ['p_unc', 'p_corr']:
                            if col in df_show.columns: df_show[col] = df_show[col].apply(format_pval)
                        st.dataframe(df_show, width='stretch', hide_index=True)

                # --- SECTION 3: VISUALIZATION ---
                col_p1, col_p2, col_p3 = st.columns(3)
                with col_p1:
                    plot_format = st.selectbox("Plot Format:", ["Line Plot", "Bar Plot", "Box Plot", "Violin Plot"])
                with col_p2:
                    if plot_format in ["Line Plot", "Bar Plot"]:
                        show_error_bars = st.checkbox("Show SEM error bars", value=True)
                    else:
                        show_points = st.checkbox("Show all data points", value=True)
                with col_p3:
                    show_pvals_on_line = st.checkbox("Draw significance asterisks on plot", value=True)

                summary_df = final_df.groupby(['Group', 'Timepoint_Weeks'])[plot_metric].agg(['mean', 'sem']).reset_index()
                summary_df = summary_df.rename(columns={'mean': plot_metric, 'sem': 'SEM'}).sort_values(by='Timepoint_Weeks')
                title_text = f"Longitudinal Progression of {plot_metric}"

                if plot_format == "Line Plot":
                    fig = px.line(summary_df, x='Timepoint_Weeks', y=plot_metric, color='Group', markers=True,
                                  error_y='SEM' if show_error_bars else None, title=title_text,
                                  labels={'Timepoint_Weeks': 'Timepoint (Weeks)'}, color_discrete_map=color_map)
                elif plot_format == "Bar Plot":
                    fig = px.bar(summary_df, x='Timepoint_Weeks', y=plot_metric, color='Group', barmode='group',
                                 error_y='SEM' if show_error_bars else None, title=title_text,
                                 labels={'Timepoint_Weeks': 'Timepoint (Weeks)'}, color_discrete_map=color_map)
                elif plot_format == "Box Plot":
                    fig = px.box(final_df, x='Timepoint_Weeks', y=plot_metric, color='Group',
                                 points="all" if show_points else False, title=title_text,
                                 labels={'Timepoint_Weeks': 'Timepoint (Weeks)'}, color_discrete_map=color_map)
                elif plot_format == "Violin Plot":
                    fig = px.violin(final_df, x='Timepoint_Weeks', y=plot_metric, color='Group', box=True,
                                    points="all" if show_points else False, title=title_text,
                                    labels={'Timepoint_Weeks': 'Timepoint (Weeks)'}, color_discrete_map=color_map)

                # Fix Plotly X-Axis spacing
                try:
                    dtick_val = sorted(final_df['Timepoint_Weeks'].unique())[1] - sorted(final_df['Timepoint_Weeks'].unique())[0] if len(final_df['Timepoint_Weeks'].unique()) > 1 else 1
                    fig.update_layout(xaxis=dict(type='linear', dtick=dtick_val))
                except:
                    fig.update_layout(xaxis=dict(type='category'))

                # --- Draw Asterisks from the Auto-Engine ---
                if show_pvals_on_line and display_posthocs is not None and not display_posthocs.empty:
                    if plot_format in ["Box Plot", "Violin Plot"]:
                        fig = add_plotly_significance_brackets(
                            fig=fig, df=final_df, posthocs_df=display_posthocs, 
                            x_col='Timepoint_Weeks', y_col=plot_metric, text_color=annotation_color
                        )
                    else:
                        y_max_overall = final_df[plot_metric].max()
                        y_min_overall = final_df[plot_metric].min()
                        offset = (y_max_overall - y_min_overall) * 0.08 if y_max_overall != y_min_overall else (y_max_overall * 0.05)

                        valid_p_cols = ['p_corr', 'p_corr', 'p_unc', 'p_unc', 'p_val', 'pval', 'p']
                        p_col = next((c for c in display_posthocs.columns if c.lower() in valid_p_cols), None)

                        if p_col:
                            for _, row in display_posthocs.iterrows():
                                tp = row['Timepoint_Weeks']
                                raw_pval = str(row[p_col]).replace('<', '').replace('>', '').replace('=', '').strip()
                                try:
                                    pval = float(raw_pval)
                                    if pval < 0.001: star = "***"
                                    elif pval < 0.01: star = "**"
                                    elif pval < 0.05: star = "*"
                                    else: continue 
                                    
                                    tp_df = summary_df[summary_df['Timepoint_Weeks'].astype(str) == str(tp)]
                                    if tp_df.empty: continue
                                    y_highest_tp = (tp_df[plot_metric] + tp_df['SEM']).max() if show_error_bars else tp_df[plot_metric].max()

                                    fig.add_annotation(
                                        x=tp, y=y_highest_tp + offset, text=star, showarrow=False,
                                        font=dict(size=18, color=annotation_color, family="Arial")
                                    )
                                except ValueError:
                                    pass

                fig.update_layout(margin=dict(t=30))
                st.plotly_chart(fig, width='stretch')

    # --- TAB 5: RADAR PLOTS ---
    with tab5:
        st.subheader("Multivariate Radar Plot Analysis")
        
        if 'mapping_df' not in st.session_state:
            st.warning("⚠️ Please go to the 'Experimental Groups Setup' tab and extract variables first.")
        else:
            radar_sheet = st.selectbox("Select Statistic (Sheet) for Radar Data:", sheet_names, key="radar_sheet")
            df_radar = data_dict[radar_sheet]
            radar_num_cols = [col for col in df_radar.columns if col != 'Ids']
            
            st.markdown("Select at least 3 measurements to form a valid radar chart.")
            default_radar_metrics = radar_num_cols[:4] if len(radar_num_cols) >= 4 else radar_num_cols
            radar_metrics = st.multiselect(
                "Select Measurements:", 
                radar_num_cols, 
                default=default_radar_metrics,
                key="radar_metrics_select"
            )
            
            all_groups = st.session_state.mapping_df['Group'].unique()
            all_groups = sorted([g for g in all_groups if g != "Unknown"])
            all_timepoints = sorted(st.session_state.mapping_df['Timepoint_Weeks'].dropna().unique())
            
            col_rg, col_rt = st.columns(2)
            with col_rg:
                radar_groups = st.multiselect(
                    "Select Groups to Display:", 
                    all_groups, 
                    default=all_groups,
                    key="radar_groups" 
                )
            with col_rt:
                radar_tp = st.selectbox(
                    "Select a single Timepoint (Weeks):", 
                    all_timepoints,
                    key="radar_timepoint" 
                )
            
            tooltip_text = (
                "Highly recommended! Since angles and distances use different scales, raw values skew the plot. Measurements with larger means will also dominate the shape, making it hard to compare groups across metrics."
                "Proportional normalization divides each metric by its highest group mean. The highest group reaches the outer edge (1.0), "
                "and other groups are plotted proportionally (e.g., 0.85). This preserves the true ratios between your groups!"
            )
            normalize_radar = st.checkbox("Normalize Data (Proportional to Maximum)", value=True, help=tooltip_text)

            if st.button("Generate Radar Plot", type="primary", key="generate_radar_btn"):
                if len(radar_metrics) < 3:
                    st.error("Please select at least 3 metrics for a valid radar plot.")
                elif not radar_groups:
                    st.error("Please select at least one group.")
                else:
                    mapping_df = st.session_state.mapping_df.copy()
                    if st.session_state.get('exclude_subjects_ui'):
                        mapping_df = mapping_df[~mapping_df['Subject_ID'].isin(st.session_state.exclude_subjects_ui)]
                    mapping_radar = mapping_df[(mapping_df['Group'].isin(radar_groups)) & (mapping_df['Timepoint_Weeks'] == radar_tp)]
                    
                    if mapping_radar.empty:
                        st.warning(f"No valid group mappings found for timepoint {radar_tp} Weeks.")
                        st.stop()

                    merged_r = pd.merge(df_radar[['Ids'] + radar_metrics], mapping_radar, on='Ids')
                    for m in radar_metrics:
                        merged_r[m] = pd.to_numeric(merged_r[m], errors='coerce')
                    merged_r = merged_r.dropna(subset=radar_metrics)
                    
                    if merged_r.empty:
                        st.warning("No data found for the selected metrics, timepoint, and groups.")
                    else:
                        agg_r = merged_r.groupby('Group')[radar_metrics].mean().reset_index()
                        
                        if normalize_radar:
                            for m in radar_metrics:
                                # Max sclaing normalization (preserves ratios between groups)
                                # ---------------------------------------------------------#
                                max_val = agg_r[m].max()
                                if max_val != 0 and pd.notna(max_val):
                                    agg_r[m] = agg_r[m] / max_val 
                                else:
                                    agg_r[m] = 0.0


                                # Alternative Min-Max Scaling
                                # min_val = agg_r[m].min()
                                # max_val = agg_r[m].max()
                                # if max_val != min_val:
                                #     agg_r[m] = (agg_r[m] - min_val) / (max_val - min_val)
                                # else:
                                #     agg_r[m] = 0.0

                        melted_r = pd.melt(
                            agg_r, 
                            id_vars=['Group'], 
                            value_vars=radar_metrics, 
                            var_name='Measurement', 
                            value_name='Value'
                        )
                        
                        dfs_to_concat = []
                        for group in radar_groups:
                            group_data = melted_r[melted_r['Group'] == group]
                            if not group_data.empty:
                                closed_loop = pd.concat([group_data, group_data.iloc[[0]]])
                                dfs_to_concat.append(closed_loop)
                        
                        if not dfs_to_concat:
                            st.warning("Could not build plot data.")
                            st.stop()

                        melted_r_closed = pd.concat(dfs_to_concat)
                        
                        # 1. Generate a dynamic string of the selected groups (e.g., "Wildtype vs. Transgenic")
                        groups_str = " vs. ".join(radar_groups)
                        
                        # Generate base plot (removed the title argument here since we build a custom one below)
                        fig_radar = px.line_polar(
                            melted_r_closed, 
                            r='Value', 
                            theta='Measurement', 
                            color='Group', 
                            line_close=True,
                            color_discrete_map=color_map
                        )
                        fig_radar.update_traces(fill='toself', opacity=0.3)
                        
                        # --- MODIFICATION START: Contrast, Background, and Dynamic Title ---
                        polar_config = dict(
                            angularaxis=dict(
                                tickfont=dict(color="black", size=12) 
                            ),
                            radialaxis=dict(
                                tickfont=dict(color="black"),
                                gridcolor="lightgrey", 
                                visible=True
                            )
                        )
                        
                        # Preserve normalized range logic
                        if normalize_radar:
                            polar_config['radialaxis']['range'] = [0, 1]
                            
                        fig_radar.update_layout(
                            paper_bgcolor="white", # Clean white chart area
                            plot_bgcolor="white",
                            polar=polar_config,
                            # 2. Dynamic Title with Groups as a subtitle
                            title=dict(
                                text=f"Kinematic Profile at {radar_tp} Weeks {'(Normalized)' if normalize_radar else '(Raw Values)'}<br><sup style='color: dimgrey;'>{groups_str}</sup>",
                                font=dict(color="black", size=18)
                            ),
                            # 3. Explicitly force both the legend title ('Group') and its text to be black
                            legend=dict(
                                title=dict(text="Group", font=dict(color="black", size=14, weight="bold")),
                                font=dict(color="black", size=12)
                            )
                        )
                        
                        # Display modified plot
                        st.plotly_chart(fig_radar, width='stretch')
            st.markdown("---")
            st.markdown("##### ❗Important Note:")
            radar_info = st.markdown("Every time any color, group, timepoint, or metric selection is changed, your current radar plot generated will disappear and you will need to generate the radar plot again using the **Generate Radar Plot** button to update the visualization. This ensures that the plot accurately reflects your current selections and allows you to explore different combinations of metrics and groups effectively.", text_alignment="justify")

else:
    st.info("Please upload your Excel file to get started.")