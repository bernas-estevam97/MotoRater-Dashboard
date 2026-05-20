import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re
import pingouin as pg
import traceback
import statsmodels.formula.api as smf
import statsmodels.api as sm
import io
import zipfile

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
    # Check if this is a brand new file being uploaded
    if 'data_dict' not in st.session_state or st.session_state.get('uploaded_filename') != uploaded_file.name:
        xls = pd.ExcelFile(uploaded_file)
        sheet_names = xls.sheet_names
        st.session_state.data_dict = {
            sheet: pd.read_excel(xls, sheet_name=sheet).rename(columns=column_rename_map) 
            for sheet in sheet_names
        }
        st.session_state.sheet_names = sheet_names
        st.session_state.uploaded_filename = uploaded_file.name
        
        # --- 🧹 CLEANUP OLD SESSION STATE ---
        # Delete old extracted variables so the app doesn't mix File 1 IDs with File 2 Data
        keys_to_delete = ['mapping_df', 'group_definitions_final', 'run_stats']
        for key in keys_to_delete:
            if key in st.session_state:
                del st.session_state[key]
        
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
            elif len(selected_plot_timepoints) == 0:
                st.error("🚨 Please select at least 1 timepoint to analyze.")
            else:
                # --- DATA PREPARATION ---
                mapping_filtered = mapping_df[
                    (mapping_df['Group'].isin(selected_plot_groups)) & 
                    (mapping_df['Timepoint_Weeks'].isin(selected_plot_timepoints))
                ]
                
                merged_raw = pd.merge(df_to_plot[['Ids', plot_metric]], mapping_filtered, on='Ids')
                merged_raw[plot_metric] = pd.to_numeric(merged_raw[plot_metric], errors='coerce')
                
                final_df = merged_raw.dropna(subset=[plot_metric]).groupby(['Subject_ID', 'Group', 'Timepoint_Weeks'])[plot_metric].mean().reset_index()

                final_df['_metric_'] = final_df[plot_metric].astype(float)
                final_df['_time_'] = final_df['Timepoint_Weeks'].astype(str)
                final_df['_group_'] = final_df['Group'].astype(str)

                display_posthocs = pd.DataFrame()
                
                def format_pval(x):
                    if pd.isna(x): return "NaN"
                    try:
                        val = float(x)
                        return f"{val:.4f}" if val > 0.0001 else "<0.0001"
                    except:
                        return str(x)

                # =====================================================================
                # BRANCH 1: CROSS-SECTIONAL ANALYSIS (EXACTLY 1 TIMEPOINT)
                # =====================================================================
                if len(selected_plot_timepoints) == 1:
                    with st.expander("📊 Cross-Sectional Stats (Click to Expand)", expanded=False):
                        tp = selected_plot_timepoints[0]
                        st.markdown(f"### Analysis for Week {tp}")
                        
                        g1_data = final_df[final_df['Group'] == selected_plot_groups[0]][plot_metric]
                        g2_data = final_df[final_df['Group'] == selected_plot_groups[1]][plot_metric]
                        
                        if len(g1_data) < 2 or len(g2_data) < 2:
                            st.error(f"🚨 Not enough data at Week {tp} to perform statistical testing. Group {selected_plot_groups[0]} has n={len(g1_data)}, Group {selected_plot_groups[1]} has n={len(g2_data)}.")
                        else:
                            base_model = smf.ols("_metric_ ~ C(_group_)", data=final_df).fit()
                            norm_test = pg.normality(base_model.resid)
                            is_normal = norm_test['normal'].iloc[0] if not norm_test.empty else True
                            
                            col_chk1, col_chk2 = st.columns(2)
                            with col_chk1:
                                if is_normal:
                                    st.success("✔️ **Normality:** Passed")
                                    st.info("🚀 **Active Pipeline: Welch's T-Test**")
                                else:
                                    st.error("⚠️ **Normality:** Violated")
                                    st.warning("🚀 **Active Pipeline: Mann-Whitney U**")
                                    
                            with col_chk2:
                                st.info(f"📐 **Sample Sizes:** {selected_plot_groups[0]} (n={len(g1_data)}), {selected_plot_groups[1]} (n={len(g2_data)})")

                            try:
                                if is_normal: res = pg.ttest(g1_data, g2_data) 
                                else: res = pg.mwu(g1_data, g2_data)
                                    
                                st.markdown("**Results:**")
                                res_show = res.copy()
                                
                                p_col = next((c for c in res_show.columns if c.lower() in ['p-val', 'p_val', 'pval', 'p']), None)
                                
                                if p_col:
                                    res_show[p_col] = res_show[p_col].apply(format_pval)
                                st.dataframe(res_show, width='stretch')
                                
                                if p_col:
                                    p_val_raw = res[p_col].values[0]
                                    display_posthocs = pd.DataFrame([{
                                        'Timepoint_Weeks': tp, 
                                        'Group A': selected_plot_groups[0], 
                                        'Group B': selected_plot_groups[1], 
                                        'p_unc': p_val_raw,
                                        'p_corr': p_val_raw
                                    }])
                                
                            except Exception as e:
                                st.error(f"Test Failed: {e}")

                # =====================================================================
                # BRANCH 2: LONGITUDINAL ANALYSIS (2+ TIMEPOINTS)
                # =====================================================================
                else:
                    with st.expander("📊 Statistical Tables & Assumptions (Click to Expand)", expanded=False):
                        
                        base_model = smf.ols("_metric_ ~ C(_time_) * C(_group_)", data=final_df).fit()
                        residuals = base_model.resid
                        
                        norm_test = pg.normality(residuals)
                        is_normal = norm_test['normal'].iloc[0] if not norm_test.empty else True
                        
                        expected_tps = len(selected_plot_timepoints)
                        subj_tps = final_df.groupby('Subject_ID')['Timepoint_Weeks'].nunique()
                        is_balanced = (subj_tps == expected_tps).all()

                        st.markdown("### 1. Model Assumptions & Pipeline Selection")
                        
                        col_chk1, col_chk2 = st.columns(2)
                        with col_chk1:
                            if is_normal: st.success("✔️ **Residual Normality:** Passed")
                            else: st.error("⚠️ **Residual Normality:** Violated (Skewed)")
                                
                        with col_chk2:
                            if is_balanced:
                                st.success("✔️ **Design Balance:** Passed (No missing data)")
                            else:
                                st.error("⚠️ **Design Balance:** Violated (Missing timepoints)")
                                expected_tps_list = sorted(selected_plot_timepoints)
                                subj_tps_list = final_df.groupby(['Subject_ID', 'Group'])['Timepoint_Weeks'].agg(list).reset_index()
                                subj_tps_list['Missing_Timepoints'] = subj_tps_list['Timepoint_Weeks'].apply(lambda tps: [t for t in expected_tps_list if t not in tps])
                                incomplete_subjs = subj_tps_list[subj_tps_list['Missing_Timepoints'].str.len() > 0].copy()
                                
                                if not incomplete_subjs.empty:
                                    incomplete_subjs['Missing_Timepoints'] = incomplete_subjs['Missing_Timepoints'].apply(lambda x: ", ".join(map(str, x)) + " Weeks")
                                    st.dataframe(incomplete_subjs[['Group', 'Subject_ID', 'Missing_Timepoints']].sort_values(['Group', 'Subject_ID']), hide_index=True, width='stretch')

                        st.markdown("---")
                        
                        if is_normal and is_balanced:
                            st.info("🚀 **Active Pipeline: A (2-Way Mixed-Design ANOVA)**\n* **Why?** Data residuals are normal and design is perfectly balanced.")
                        elif is_normal and not is_balanced:
                            st.warning("🚀 **Active Pipeline: B (Linear Mixed-Effects Model)**\n* **Why?** Data residuals are normal, but missing timepoints required an upgrade to LMM to prevent survivor bias.")
                        else:
                            st.error("🚀 **Active Pipeline: C (Generalized Estimating Equations - GEE)**\n* **Why?** Data residuals violate normality.\n* **What's happening?** The engine upgraded to a robust GEE model. It safely handles skewed data while preserving the longitudinal structure.")

                        st.markdown("### 2. Results")

                        if is_normal and is_balanced:
                            # --- PIPELINE A: ANOVA ---
                            try:
                                anova_res = pg.mixed_anova(dv=plot_metric, within='Timepoint_Weeks', between='Group', subject='Subject_ID', data=final_df)
                                st.markdown("**2-Way Mixed ANOVA**")
                                for col in ['p_unc', 'p_unc', 'p_val', 'p_GG_corr']:
                                    if col in anova_res.columns: anova_res[col] = anova_res[col].apply(format_pval)
                                st.dataframe(anova_res, width='stretch', hide_index=True)
                                
                                # FIXED: Use robust pairwise T-Tests for Simple Main Effects to guarantee formatting
                                st.markdown("**Pairwise T-Tests (Holm-Corrected for FDR)**")
                                rows = []
                                for tp in selected_plot_timepoints:
                                    tp_df = final_df[final_df['Timepoint_Weeks'] == tp]
                                    g1 = tp_df[tp_df['Group'] == selected_plot_groups[0]][plot_metric]
                                    g2 = tp_df[tp_df['Group'] == selected_plot_groups[1]][plot_metric]
                                    if len(g1) > 1 and len(g2) > 1:
                                        res = pg.ttest(g1, g2)
                                        p_val_found = next((c for c in res.columns if c.lower() in ['p-val', 'pval', 'p_val', 'p']), None)
                                        if p_val_found:
                                            rows.append({'Timepoint_Weeks': tp, 'Group A': selected_plot_groups[0], 'Group B': selected_plot_groups[1], 'p_unc': res[p_val_found].values[0]})
                                if rows:
                                    display_posthocs = pd.DataFrame(rows)
                                    _, p_corr = pg.multicomp(display_posthocs['p_unc'].values, method='holm')
                                    display_posthocs['p_corr'] = p_corr
                            except Exception as e:
                                st.error(f"ANOVA Failed: {e}")


                        elif is_normal and not is_balanced:
                            # --- PIPELINE B: LMM ---
                            try:
                                md = smf.mixedlm("_metric_ ~ C(_time_) * C(_group_)", final_df, groups="Subject_ID")
                                mdf = md.fit(method='cg')
                                st.markdown("**Linear Mixed-Effects Model (LMM)** *(Best for missing data)*")
                                
                                # FIXED: Safely convert LMM results natively to avoid PyArrow crashes
                                df_lmm = mdf.summary().tables[1].reset_index()
                                df_lmm.rename(columns={'index': 'Parameter'}, inplace=True)
                                st.dataframe(df_lmm.astype(str), width='stretch', hide_index=True)
                                
                                # FIXED: Fallback to robust Welch's T-Tests for pairwise to bypass statsmodels string parser bug
                                st.markdown("**Pairwise T-Tests (Holm-Corrected for FDR)**")
                                rows = []
                                for tp in selected_plot_timepoints:
                                    tp_df = final_df[final_df['Timepoint_Weeks'] == tp]
                                    g1 = tp_df[tp_df['Group'] == selected_plot_groups[0]][plot_metric]
                                    g2 = tp_df[tp_df['Group'] == selected_plot_groups[1]][plot_metric]
                                    if len(g1) > 1 and len(g2) > 1:
                                        res = pg.ttest(g1, g2)
                                        p_val_found = res.get('p-val', res.get('pval', res.get('p_val', None)))
                                        if p_val_found is not None:
                                            rows.append({'Timepoint_Weeks': tp, 'Group A': selected_plot_groups[0], 'Group B': selected_plot_groups[1], 'p_unc': p_val_found.values[0]})
                                if rows:
                                    display_posthocs = pd.DataFrame(rows)
                                    _, p_corr = pg.multicomp(display_posthocs['p_unc'].values, method='holm')
                                    display_posthocs['p_corr'] = p_corr
                                    
                            except Exception as e:
                                st.error(f"LMM Failed to converge: {e}")

                        else:
                            # --- PIPELINE C: GEE ---
                            st.markdown("**Generalized Estimating Equations (GEE)**")
                            try:
                                cov_struct = sm.cov_struct.Exchangeable()
                                fam = sm.families.Gaussian() 
                                
                                md = smf.gee("_metric_ ~ C(_time_) * C(_group_)", groups=final_df["Subject_ID"], data=final_df, cov_struct=cov_struct, family=fam)
                                mdf = md.fit()
                                
                                sm_table = mdf.summary().tables[1]
                                df_gee = pd.DataFrame(sm_table.data[1:], columns=sm_table.data[0])
                                st.dataframe(df_gee, width='stretch')
                                
                                st.markdown("**GEE Pairwise Contrasts (Group A vs B per Timepoint, Holm-Corrected)**")
                                groups_sorted = sorted(final_df['_group_'].unique())
                                ref_group = groups_sorted[0]
                                test_group = groups_sorted[1]
                                tps_sorted = sorted(final_df['_time_'].unique())
                                ref_time = tps_sorted[0]
                                
                                rows = []
                                for tp in selected_plot_timepoints:
                                    tp_str = str(tp)
                                    if tp_str == ref_time: hypothesis = f"C(_group_)[T.{test_group}] = 0"
                                    else: hypothesis = f"C(_group_)[T.{test_group}] + C(_time_)[T.{tp_str}]:C(_group_)[T.{test_group}] = 0"
                                    
                                    contrast_res = mdf.t_test(hypothesis)
                                    rows.append({'Timepoint_Weeks': tp, 'Group A': ref_group, 'Group B': test_group, 'p_unc': float(contrast_res.pvalue)})
                                    
                                if rows:
                                    display_posthocs = pd.DataFrame(rows)
                                    _, p_corr = pg.multicomp(display_posthocs['p_unc'].values, method='holm')
                                    display_posthocs['p_corr'] = p_corr
                                    
                            except Exception as e:
                                st.error(f"GEE Failed: {e}")

                        if not display_posthocs.empty:
                            df_show = display_posthocs.copy()
                            for col in ['p_unc', 'p_corr']:
                                if col in df_show.columns: df_show[col] = df_show[col].apply(format_pval)
                            st.dataframe(df_show, width='stretch', hide_index=True)


                # =====================================================================
                # SECTION 3: VISUALIZATION (100% Native, Bulletproof Asterisks)
                # =====================================================================
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

                # --- NEW: ADVANCED X-AXIS SETTINGS ---
                with st.expander("⚙️ Advanced Plot Settings", expanded=False):
                    st.markdown("**X-Axis Configuration**")
                    col_x1, col_x2 = st.columns(2)
                    with col_x1:
                        force_exact_ticks = st.checkbox("Force exact timepoint labels", value=True, 
                                                        help="Forces Plotly to draw a number on the X-axis for every week in your data, avoiding generic intervals like 5, 10, 15.")
                    with col_x2:
                        custom_x_range = st.checkbox("Customize X-Axis Range", value=False)
                    
                    if custom_x_range:
                        # Calculate a smart default margin based on the selected data
                        min_tp = float(min(selected_plot_timepoints))
                        max_tp = float(max(selected_plot_timepoints))
                        margin = (max_tp - min_tp) * 0.1 if max_tp != min_tp else 1.0
                        
                        col_r1, col_r2 = st.columns(2)
                        with col_r1:
                            x_min = st.number_input("X-Axis Minimum", value=min_tp - margin)
                        with col_r2:
                            x_max = st.number_input("X-Axis Maximum", value=max_tp + margin)

                summary_df = final_df.groupby(['Group', 'Timepoint_Weeks'])[plot_metric].agg(['mean', 'sem']).reset_index()
                summary_df = summary_df.rename(columns={'mean': plot_metric, 'sem': 'SEM'}).sort_values(by='Timepoint_Weeks')
                title_text = f"Longitudinal Progression of {plot_metric}"

                # 1. Generate the Base Plot (Using your sidebar's color_map automatically!)
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

                # 2. Apply Custom X-Axis Settings
                xaxis_dict = dict(type='linear')
                
                if force_exact_ticks:
                    # Extracts the exact unique timepoints from your dataframe and forces Plotly to display them
                    xaxis_dict['tickvals'] = sorted(final_df['Timepoint_Weeks'].unique())
                    
                if custom_x_range:
                    # Applies the user's manual bounds
                    xaxis_dict['range'] = [x_min, x_max]

                fig.update_layout(xaxis=xaxis_dict)

                # 3. Universal Asterisk Engine
                if show_pvals_on_line and not display_posthocs.empty:
                    y_max_overall = final_df[plot_metric].max()
                    y_min_overall = final_df[plot_metric].min()
                    
                    # Calculate a dynamic gap above the data for the stars
                    offset = (y_max_overall - y_min_overall) * 0.08 if y_max_overall != y_min_overall else (y_max_overall * 0.05)

                    valid_p_cols = ['p_corr', 'p-corr', 'p_unc', 'p-unc', 'p_val', 'pval', 'p', 'p-val']
                    p_col = next((c for c in display_posthocs.columns if c.lower() in valid_p_cols), None)

                    if p_col:
                        highest_drawn_y = y_max_overall
                        
                        for _, row in display_posthocs.iterrows():
                            tp = row['Timepoint_Weeks']
                            raw_pval = str(row[p_col]).replace('<', '').replace('>', '').replace('=', '').strip()
                            
                            try:
                                pval = float(raw_pval)
                                if pval < 0.001: star = "***"
                                elif pval < 0.01: star = "**"
                                elif pval < 0.05: star = "*"
                                else: star = "ns" 
                                
                                # Find highest Y point depending on plot type so the asterisk floats perfectly above the tallest bar/whisker
                                if plot_format in ["Line Plot", "Bar Plot"] and show_error_bars:
                                    tp_summary = summary_df[summary_df['Timepoint_Weeks'].astype(str) == str(tp)]
                                    if tp_summary.empty: continue
                                    y_highest_tp = (tp_summary[plot_metric] + tp_summary['SEM'].fillna(0)).max()
                                else:
                                    tp_raw = final_df[final_df['Timepoint_Weeks'].astype(str) == str(tp)][plot_metric]
                                    if tp_raw.empty: continue
                                    y_highest_tp = tp_raw.max()

                                y_pos = y_highest_tp + offset
                                
                                # Keep track of the highest star so we can expand the ceiling of the graph
                                if y_pos > highest_drawn_y:
                                    highest_drawn_y = y_pos

                                # Draw the star natively (Using your sidebar's annotation_color automatically!)
                                fig.add_annotation(
                                    x=tp, 
                                    y=y_pos, 
                                    text=star, 
                                    showarrow=False,
                                    font=dict(size=14 if star == "ns" else 22, color=annotation_color, family="Arial")
                                )
                            except Exception as e:
                                pass
                                
                        # 4. Expand the Y-Axis ceiling so the stars don't get cut off!
                        y_upper_limit = highest_drawn_y + (offset * 1.5)
                        y_lower_limit = y_min_overall - (offset * 0.5)
                        fig.update_layout(yaxis=dict(range=[y_lower_limit, y_upper_limit]))
                    else:
                        st.warning(f"⚠️ Engine could not locate a p-value column to plot. Found: {list(display_posthocs.columns)}")

                fig.update_layout(margin=dict(t=30))
                st.plotly_chart(fig, width='stretch')

                # =====================================================================
                # SECTION 4: BATCH EXPORT (ALL METRICS AS PNG WITH STATS)
                # =====================================================================
                st.markdown("---")
                st.subheader("📦 Batch Export All Measurements")
                st.write("Generate and download a ZIP archive containing high-resolution **PNG** plots (with statistical significance) for **all** measurements in the current sheet.")
                
                if st.button("Generate All Plots (ZIP)", type="secondary"):
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    zip_buffer = io.BytesIO()
                    
                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                        total_metrics = len(numeric_cols)
                        
                        for idx, metric in enumerate(numeric_cols):
                            status_text.text(f"Rendering {idx + 1}/{total_metrics}: {metric} ...")
                            progress_bar.progress((idx) / total_metrics)
                            
                            # Prepare data for this specific metric
                            loop_merged = pd.merge(df_to_plot[['Ids', metric]], mapping_filtered, on='Ids')
                            loop_merged[metric] = pd.to_numeric(loop_merged[metric], errors='coerce')
                            loop_df = loop_merged.dropna(subset=[metric]).copy()
                            
                            if loop_df.empty or loop_df['Group'].nunique() < 2:
                                continue
                            
                            # Generate Summary Stats
                            loop_summary = loop_df.groupby(['Group', 'Timepoint_Weeks'])[metric].agg(['mean', 'sem']).reset_index()
                            loop_summary = loop_summary.rename(columns={'mean': metric, 'sem': 'SEM'}).sort_values(by='Timepoint_Weeks')
                            title_text = f"Longitudinal Progression of {metric}"
                            
                            # 3. Calculate Significance (🚨 STRICT FLOAT MATCHING 🚨)
                            batch_posthocs = pd.DataFrame()
                            if show_pvals_on_line:
                                rows = []
                                # Create a strictly numeric timepoint column for safe filtering
                                loop_df['_tp_numeric_'] = pd.to_numeric(loop_df['Timepoint_Weeks'], errors='coerce')
                                
                                for tp in selected_plot_timepoints:
                                    try:
                                        tp_num = float(tp)
                                    except ValueError:
                                        continue # Skip if timepoint isn't a valid number
                                        
                                    # Filter using the float value
                                    tp_df = loop_df[loop_df['_tp_numeric_'] == tp_num]
                                    
                                    g1 = pd.to_numeric(tp_df[tp_df['Group'] == selected_plot_groups[0]][metric], errors='coerce').dropna()
                                    g2 = pd.to_numeric(tp_df[tp_df['Group'] == selected_plot_groups[1]][metric], errors='coerce').dropna()
                                    
                                    if len(g1) > 1 and len(g2) > 1:
                                        try:
                                            res = pg.ttest(g1, g2)
                                            p_col = next((c for c in res.columns if c.lower() in ['p-val', 'pval', 'p_val', 'p']), None)
                                            if p_col:
                                                rows.append({'Timepoint_Weeks': tp_num, 'p_val': float(res[p_col].iloc[0])})
                                        except: 
                                            try:
                                                res = pg.mwu(g1, g2)
                                                p_col = next((c for c in res.columns if c.lower() in ['p-val', 'pval', 'p_val', 'p']), None)
                                                if p_col:
                                                    rows.append({'Timepoint_Weeks': tp_num, 'p_val': float(res[p_col].iloc[0])})
                                            except: pass
                                
                                if rows:
                                    batch_posthocs = pd.DataFrame(rows)
                                    if len(batch_posthocs) > 1:
                                        _, p_corr = pg.multicomp(batch_posthocs['p_val'].values, method='holm')
                                        batch_posthocs['p_val'] = p_corr

                            # Build Figure
                            if plot_format == "Line Plot":
                                loop_fig = px.line(loop_summary, x='Timepoint_Weeks', y=metric, color='Group', markers=True,
                                              error_y='SEM' if show_error_bars else None, title=title_text,
                                              labels={'Timepoint_Weeks': 'Timepoint (Weeks)'}, color_discrete_map=color_map)
                            elif plot_format == "Bar Plot":
                                loop_fig = px.bar(loop_summary, x='Timepoint_Weeks', y=metric, color='Group', barmode='group',
                                             error_y='SEM' if show_error_bars else None, title=title_text,
                                             labels={'Timepoint_Weeks': 'Timepoint (Weeks)'}, color_discrete_map=color_map)
                            elif plot_format == "Box Plot":
                                loop_fig = px.box(loop_df, x='Timepoint_Weeks', y=metric, color='Group',
                                             points="all" if show_points else False, title=title_text,
                                             labels={'Timepoint_Weeks': 'Timepoint (Weeks)'}, color_discrete_map=color_map)
                            elif plot_format == "Violin Plot":
                                loop_fig = px.violin(loop_df, x='Timepoint_Weeks', y=metric, color='Group', box=True,
                                                points="all" if show_points else False, title=title_text,
                                                labels={'Timepoint_Weeks': 'Timepoint (Weeks)'}, color_discrete_map=color_map)
                            
                            loop_fig.update_layout(xaxis=xaxis_dict)
                            
                            # Draw Asterisks
                            if show_pvals_on_line and not batch_posthocs.empty:
                                y_max_overall = loop_df[metric].max()
                                y_min_overall = loop_df[metric].min()
                                offset = (y_max_overall - y_min_overall) * 0.08 if y_max_overall != y_min_overall else (y_max_overall * 0.05)
                                highest_drawn_y = y_max_overall
                                
                                # Strict numeric matching for summary filtering as well
                                loop_summary['_tp_numeric_'] = pd.to_numeric(loop_summary['Timepoint_Weeks'], errors='coerce')

                                for _, row in batch_posthocs.iterrows():
                                    tp_num = float(row['Timepoint_Weeks'])
                                    pval = float(row['p_val'])
                                    
                                    if pval < 0.001: star = "***"
                                    elif pval < 0.01: star = "**"
                                    elif pval < 0.05: star = "*"
                                    else: star = "ns"

                                    if plot_format in ["Line Plot", "Bar Plot"] and show_error_bars:
                                        tp_summary = loop_summary[loop_summary['_tp_numeric_'] == tp_num]
                                        if tp_summary.empty: continue
                                        y_highest_tp = float((tp_summary[metric] + tp_summary['SEM'].fillna(0)).max())
                                    else:
                                        tp_raw = loop_df[loop_df['_tp_numeric_'] == tp_num][metric]
                                        if tp_raw.empty: continue
                                        y_highest_tp = float(tp_raw.max())

                                    y_pos = y_highest_tp + offset
                                    if y_pos > highest_drawn_y: highest_drawn_y = y_pos

                                    loop_fig.add_annotation(
                                        x=tp_num, y=float(y_pos), text=star, showarrow=False,
                                        font=dict(size=14 if star == "ns" else 22, color="#000000", family="Arial")
                                    )

                                y_upper_limit = highest_drawn_y + (offset * 1.5)
                                y_lower_limit = y_min_overall - (offset * 0.5)
                                loop_fig.update_layout(yaxis=dict(range=[y_lower_limit, y_upper_limit]))

                            # FORCE WHITE BACKGROUND AND BLACK TEXT FOR EXPORT
                            loop_fig.update_layout(
                                margin=dict(t=30),
                                paper_bgcolor="white", 
                                plot_bgcolor="white",
                                font=dict(color="black")
                            )
                            loop_fig.update_xaxes(showline=True, linewidth=1, linecolor='black', gridcolor='lightgrey')
                            loop_fig.update_yaxes(showline=True, linewidth=1, linecolor='black', gridcolor='lightgrey')
                            
                            # Convert to PNG and save
                            img_bytes = loop_fig.to_image(format="png", width=1200, height=800, scale=2)
                            safe_metric = "".join([c for c in metric if c.isalpha() or c.isdigit() or c==' ']).rstrip()
                            zip_file.writestr(f"{safe_metric}.png", img_bytes)
                            
                    progress_bar.progress(1.0)
                    status_text.success("✅ All plots generated successfully! Ready for download.")
                    
                    st.download_button(
                        label="📥 Download PNG ZIP",
                        data=zip_buffer.getvalue(),
                        file_name=f"All_Kinematic_PNGs_{plot_sheet}.zip",
                        mime="application/zip"
                    )

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