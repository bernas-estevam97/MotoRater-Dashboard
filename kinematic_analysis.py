import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re
import pingouin as pg
import traceback

# --- NEW PLOTLY STATS FUNCTION ---
def add_plotly_significance_brackets(fig, df, posthocs_df, x_col, y_col):
    """
    Custom function to draw statistical brackets and asterisks on Plotly grouped plots.
    Assumes exactly 2 groups are being compared.
    """
    if posthocs_df is None or posthocs_df.empty: 
        return fig

    # Find the formatted p-value column from Pingouin
    p_col = next((c for c in posthocs_df.columns if 'p-' in c.lower() or c.lower() == 'pval' or c.lower() == 'p'), None)
    if not p_col: 
        return fig

    # Determine overall y-axis scale to make brackets proportional
    y_max_overall = df[y_col].max()
    y_min_overall = df[y_col].min()
    y_range = y_max_overall - y_min_overall
    if y_range == 0: y_range = y_max_overall
    
    step_y = y_range * 0.05  # Bracket spacing height (5% of total range)
    
    for _, row in posthocs_df.iterrows():
        # Only draw if this row corresponds to a specific Timepoint
        if x_col not in row: continue
        
        x_val = row[x_col]
        
        # Get the maximum y-value for this specific timepoint so the bracket clears the data
        tp_data = df[df[x_col] == x_val]
        if tp_data.empty: continue
        
        y_max_tp = tp_data[y_col].max()
        bracket_y = y_max_tp + step_y
        
        # Parse P-Value to scientific asterisks
        raw_pval = str(row[p_col])
        text = raw_pval
        # Extract the numeric part if formatted like "<0.0001"
        num_str = raw_pval.replace('<', '').replace('>', '').replace('=', '').strip()
        
        try:
            val = float(num_str)
            if val < 0.001: text = "***"
            elif val < 0.01: text = "**"
            elif val < 0.05: text = "*"
            else: text = "ns"
        except ValueError:
            pass # If it fails to parse, just print the raw text
        
        # Draw Bracket (Plotly grouped boxes offset centers by approx +/- 0.15)
        try:
            x_center = float(x_val)
            x0 = x_center - 0.15 # Center of left box
            x1 = x_center + 0.15 # Center of right box
            
            # Left vertical line
            fig.add_shape(type="line", x0=x0, x1=x0, y0=bracket_y, y1=bracket_y + step_y * 0.5, line=dict(color="black", width=1.5))
            # Right vertical line
            fig.add_shape(type="line", x0=x1, x1=x1, y0=bracket_y, y1=bracket_y + step_y * 0.5, line=dict(color="black", width=1.5))
            # Top horizontal bridge
            fig.add_shape(type="line", x0=x0, x1=x1, y0=bracket_y + step_y * 0.5, y1=bracket_y + step_y * 0.5, line=dict(color="black", width=1.5))
            
            # Add Asterisks text
            fig.add_annotation(
                x=x_center,
                y=bracket_y + step_y * 1.5,
                text=text,
                showarrow=False,
                font=dict(size=14, color="black", family="Arial")
            )
        except ValueError:
            continue # Skip if x isn't numeric
            
    return fig
# ---------------------------------

# --- CONFIGURATION ---
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

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 Data Viewer", 
        "🆔 ID Overview", 
        "🧪 Experimental Groups Setup", 
        "📈 Longitudinal Plotting",
        "🧮 Statistical Analysis",
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
        * **Group Name**: The clean name displayed on plots (e.g., "Wildtype Males").
        * **Tag in ID**: The exact text snippet the program should look for in the Subject ID (e.g., "WT_M").
        
        *Note: If an ID matches multiple tags, it will belong to both groups.*
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
                match = re.search(r'(\d+)[Ww]', str(id_str))
                return int(match.group(1)) if match else None

            def extract_subject_id(id_str):
                return str(id_str).split('_')[0]

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
            
            st.success("Variables extracted successfully using custom mapping. Multi-group assignments enabled.")
            
            map_df_clean = st.session_state.mapping_df

            st.markdown("### 📋 Group Summary (N)")
            if not map_df_clean.empty and 'Group' in map_df_clean.columns:
                group_counts = map_df_clean[map_df_clean['Group'] != 'Unknown'].groupby('Group')['Subject_ID'].nunique().reset_index()
                if not group_counts.empty:
                    group_counts.columns = ['Experimental Group', 'Number of Unique Subjects (N)']
                    st.dataframe(group_counts, width='stretch', hide_index=True)
                else:
                    st.warning("No groups matched. Check your tags.")
            else:
                st.info("Extract variables to see summary.")

    # --- TAB 4: LONGITUDINAL PLOTTING ---
    with tab4:
        st.subheader("Plot Longitudinal Means")
        
        if 'mapping_df' not in st.session_state:
            st.warning("⚠️ Please go to the 'Experimental Groups Setup' tab and extract variables first.")
        else:
            col1, col2 = st.columns(2)
            with col1:
                plot_sheet = st.selectbox("Select Statistic (Sheet):", sheet_names, key="plot_sheet")
            
            df_to_plot = data_dict[plot_sheet]
            numeric_cols = [col for col in df_to_plot.columns if col != 'Ids']
            
            with col2:
                plot_metric = st.selectbox("Select Measurement to Plot:", numeric_cols, key="plot_metric_select")
            
            all_plot_groups = sorted([g for g in st.session_state.mapping_df['Group'].unique() if g != "Unknown"])
            
            selected_plot_groups = st.multiselect(
                "Select Groups to Display:", 
                all_plot_groups, 
                default=all_plot_groups[:2] if len(all_plot_groups) >= 2 else all_plot_groups,
                key="plot_groups_multiselect"
            )
            
            show_error_bars = st.checkbox("Show Standard Error of the Mean (SEM) bars", value=True, key="sem_bars_checkbox")

            if not selected_plot_groups:
                st.info("Please select at least one group to plot.")
            else:
                mapping_df = st.session_state.mapping_df
                mapping_filtered = mapping_df[mapping_df['Group'].isin(selected_plot_groups)]
                
                merged_df = pd.merge(df_to_plot[['Ids', plot_metric]], mapping_filtered, on='Ids')
                merged_df[plot_metric] = pd.to_numeric(merged_df[plot_metric], errors='coerce')
                merged_df = merged_df.dropna(subset=['Timepoint_Weeks', plot_metric])
                
                if merged_df.empty:
                    st.warning("No valid data found for selected groups and metric.")
                else:
                    summary_df = merged_df.groupby(['Group', 'Timepoint_Weeks'])[plot_metric].agg(['mean', 'sem']).reset_index()
                    summary_df = summary_df.rename(columns={'mean': plot_metric, 'sem': 'SEM'})
                    summary_df = summary_df.sort_values(by='Timepoint_Weeks')

                    fig = px.line(
                        summary_df, 
                        x='Timepoint_Weeks', 
                        y=plot_metric, 
                        color='Group', 
                        markers=True,
                        error_y='SEM' if show_error_bars else None,
                        title=f"Longitudinal Progression of {plot_metric}",
                        labels={'Timepoint_Weeks': 'Timepoint (Weeks)', plot_metric: f'{plot_metric}'}
                    )
                    try:
                        summary_df['Timepoint_Weeks'] = pd.to_numeric(summary_df['Timepoint_Weeks'])
                        fig.update_layout(xaxis=dict(type='linear', dtick=summary_df['Timepoint_Weeks'].unique()[1]-summary_df['Timepoint_Weeks'].unique()[0] if len(summary_df['Timepoint_Weeks'].unique())>1 else 1))
                    except:
                        fig.update_layout(xaxis=dict(type='category'))
                    
                    st.plotly_chart(fig, width='stretch')

    # --- TAB 5: STATISTICAL ANALYSIS (ANOVA) ---
    with tab5:
        st.subheader("2-Way Mixed ANOVA & Multiple Comparisons")
        
        if 'mapping_df' not in st.session_state:
            st.warning("⚠️ Please go to the 'Experimental Groups Setup' tab and extract variables first.")
        else:
            col1, col2 = st.columns(2)
            with col1:
                stat_sheet = st.selectbox("Select Statistic (Sheet):", sheet_names, key="stat_sheet")
            df_stats = data_dict[stat_sheet]
            stat_numeric_cols = [col for col in df_stats.columns if col != 'Ids']
            with col2:
                stat_metric = st.selectbox("Select Measurement to Analyze:", stat_numeric_cols, key="stat_metric")
            
            st.markdown("---")
            
            all_groups = st.session_state.mapping_df['Group'].unique()
            all_groups = sorted([g for g in all_groups if g != "Unknown"])
            all_timepoints = sorted(st.session_state.mapping_df['Timepoint_Weeks'].dropna().unique())
            
            col_g, col_t = st.columns(2)
            with col_g:
                selected_groups = st.multiselect(
                    "Select exactly 2 Groups to compare:", 
                    all_groups, 
                    default=all_groups[:2] if len(all_groups)>=2 else all_groups,
                    key="anova_groups"
                )
            with col_t:
                selected_timepoints = st.multiselect(
                    "Select Timepoints to include:", 
                    all_timepoints, 
                    default=all_timepoints,
                    key="anova_timepoints"
                )
                
            btn_col1, btn_col2, btn_col3 = st.columns([1,1,1])
            if btn_col2.button("Run Statistical Analysis", type="secondary", key="run_stats_btn"):
                st.session_state['run_stats'] = True
            
            if st.session_state.get('run_stats', False):
                if len(selected_groups) != 2:
                    st.error("Please select exactly 2 groups for the comparison.")
                elif len(selected_timepoints) < 2:
                    st.error("Please select at least 2 timepoints for the longitudinal analysis.")
                else:
                    mapping_df = st.session_state.mapping_df
                    mapping_stat = mapping_df[mapping_df['Group'].isin(selected_groups)]
                    
                    merged_stat_df = pd.merge(df_stats[['Ids', stat_metric]], mapping_stat, on='Ids')
                    merged_stat_df[stat_metric] = pd.to_numeric(merged_stat_df[stat_metric], errors='coerce')
                    clean_df = merged_stat_df.dropna(subset=[stat_metric, 'Timepoint_Weeks', 'Subject_ID', 'Group'])
                    
                    filtered_df = clean_df[
                        (clean_df['Timepoint_Weeks'].isin(selected_timepoints))
                    ]
                    
                    agg_df = filtered_df.groupby(['Subject_ID', 'Group', 'Timepoint_Weeks'])[stat_metric].mean().reset_index()
                    
                    expected_tp_count = len(selected_timepoints)
                    subject_tp_counts = agg_df.groupby('Subject_ID')['Timepoint_Weeks'].nunique()
                    complete_subjects = subject_tp_counts[subject_tp_counts == expected_tp_count].index
                    
                    final_df = agg_df[agg_df['Subject_ID'].isin(complete_subjects)]
                    
                    subjects_kept = final_df['Subject_ID'].nunique()
                    subjects_dropped = len(subject_tp_counts) - subjects_kept
                    group_sizes = final_df.groupby('Group')['Subject_ID'].nunique()
                    
                    st.info(f"Filtered for complete cases: Analyzing **{subjects_kept}** subjects. (Dropped {subjects_dropped} subjects missing data).")
                    
                    st.markdown("#### 👥 Subjects Remaining Per Group:")
                    if not group_sizes.empty:
                        metric_cols = st.columns(len(group_sizes))
                        for i, (grp, count) in enumerate(group_sizes.items()):
                            metric_cols[i].metric(label=f"Group: {grp}", value=f"N = {count}")
                    st.markdown("---")

                    with st.expander("🛠️ Diagnostics & Data Viewer", expanded=False):
                        st.markdown("**1. Final Data going into ANOVA:**")
                        st.dataframe(final_df, width='stretch')
                        st.markdown("**2. Standard Deviation Check:** *(If any are 0.0 or NaN, ANOVA fails)*")
                        if subjects_kept >= 2:
                             try:
                                 st_dev_df = final_df.groupby(['Group', 'Timepoint_Weeks'])[stat_metric].std().reset_index()
                                 st.dataframe(st_dev_df, width='stretch')
                             except:
                                 st.warning("Could not calculate standard deviations. Check sample sizes.")
                        else:
                             st.warning("Not enough subjects to check standard deviation.")

                    if subjects_kept < 2:
                        st.error("Not enough total complete subjects to run the ANOVA.")
                    elif (group_sizes < 2).any() or len(group_sizes) != 2:
                        st.error("🚨 ANOVA FAILED: At least one group has fewer than 2 complete subjects.")
                    else:
                        def format_pval(x):
                            if pd.isna(x): return x
                            try:
                                val = float(x)
                                return f"{val:.4f}" if val > 0.0001 else "<0.0001"
                            except:
                                return x

                        # TEST 1: ANOVA
                        try:
                            st.markdown("### 1. Two-Way Mixed ANOVA Results")
                            anova_results = pg.mixed_anova(
                                dv=stat_metric, 
                                within='Timepoint_Weeks', 
                                between='Group', 
                                subject='Subject_ID', 
                                data=final_df
                            )
                            for col in ['p-unc', 'p-val', 'p-GG-corr']:
                                if col in anova_results.columns:
                                    anova_results[col] = anova_results[col].apply(format_pval)
                            
                            if 'p-GG-corr' in anova_results.columns and 'p-val' not in anova_results.columns:
                                anova_results = anova_results.rename(columns={'p-GG-corr': 'p-val'})

                            st.dataframe(anova_results, width='stretch', hide_index=True)
                        except Exception as e:
                            st.error(f"Failed to calculate the 2-Way ANOVA: {e}")
                            with st.expander("View ANOVA Error Log", expanded=True):
                                st.code(traceback.format_exc(), language="python")

                        # TEST 2: POST-HOCS
                        display_posthocs = None
                        try:
                            st.markdown("### 2. Multiple Comparisons (Post-Hoc)")
                            posthocs = pg.pairwise_tests(
                                dv=stat_metric, 
                                within='Timepoint_Weeks', 
                                between='Group', 
                                subject='Subject_ID', 
                                data=final_df, 
                                padjust='holm'
                            )
                            
                            interaction_posthocs = posthocs[posthocs['Contrast'] == 'Timepoint_Weeks * Group']
                            
                            if not interaction_posthocs.empty:
                                display_posthocs = interaction_posthocs.copy()
                                p_cols = [c for c in display_posthocs.columns if 'p-' in c.lower() or c.lower() == 'pval' or c.lower() == 'p']
                                
                                for col in p_cols:
                                    display_posthocs[col] = display_posthocs[col].apply(format_pval)
                                        
                                st.dataframe(display_posthocs, width='stretch', hide_index=True)
                            else:
                                st.write("No interaction post-hocs could be calculated. Showing standard main effect pairwise tests instead:")
                                st.dataframe(posthocs[posthocs['Contrast']!='Timepoint_Weeks * Group'], width='stretch', hide_index=True)

                        except Exception as e:
                            st.error(f"Failed to calculate Multiple Comparisons (Post-Hocs): {e}")
                            with st.expander("View Post-Hoc Error Log", expanded=True):
                                st.code(traceback.format_exc(), language="python")

                        # --- NEW: INTERACTIVE BOX PLOT WITH P-VALUES ---
                        if display_posthocs is not None and not display_posthocs.empty:
                            st.markdown(f"### 3. Distribution & Significance ({stat_metric})")
                            
                            fig_box = px.box(
                                final_df, 
                                x='Timepoint_Weeks', 
                                y=stat_metric, 
                                color='Group',
                                title=f"Box Plot Distributions (with Post-Hoc Significance)",
                                points="all", # Shows individual data points alongside the boxes
                                color_discrete_sequence=px.colors.qualitative.Pastel
                            )
                            
                            # Force numeric x-axis to ensure our custom offsets line up properly
                            try:
                                dtick_val = final_df['Timepoint_Weeks'].unique()[1] - final_df['Timepoint_Weeks'].unique()[0] if len(final_df['Timepoint_Weeks'].unique()) > 1 else 1
                                fig_box.update_layout(xaxis=dict(type='linear', dtick=dtick_val))
                            except:
                                pass # Fallback if timepoints aren't clean numbers
                            
                            # Apply our custom annotation function!
                            fig_box = add_plotly_significance_brackets(
                                fig=fig_box, 
                                df=final_df, 
                                posthocs_df=display_posthocs, 
                                x_col='Timepoint_Weeks', 
                                y_col=stat_metric
                            )
                            
                            # Increase top margin slightly so brackets don't get cut off by the title
                            fig_box.update_layout(margin=dict(t=60))
                            st.plotly_chart(fig_box, width='stretch')

    # --- TAB 6: RADAR PLOTS ---
    with tab6:
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
                "Highly recommended! Since angles and distances use different scales, raw values skew the plot. "
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
                    mapping_df = st.session_state.mapping_df
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
                                max_val = agg_r[m].max()
                                if max_val != 0 and pd.notna(max_val):
                                    agg_r[m] = agg_r[m] / max_val
                                else:
                                    agg_r[m] = 0.0 

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
                        
                        fig_radar = px.line_polar(
                            melted_r_closed, 
                            r='Value', 
                            theta='Measurement', 
                            color='Group', 
                            line_close=True,
                            title=f"Kinematic Profile at {radar_tp} Weeks {'(Normalized)' if normalize_radar else '(Raw Values)'}",
                            color_discrete_sequence=px.colors.qualitative.D3 
                        )
                        fig_radar.update_traces(fill='toself', opacity=0.3)
                        
                        if normalize_radar:
                            fig_radar.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 1])))
                            
                        st.plotly_chart(fig_radar, width='stretch')

else:
    st.info("Please upload your Excel file to get started.")