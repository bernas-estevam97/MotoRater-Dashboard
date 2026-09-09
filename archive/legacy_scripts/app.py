import streamlit as st
import pandas as pd
import os
import plotly.express as px
import tkinter as tk
from tkinter import filedialog

# --- Page Configuration ---
st.set_page_config(page_title="MotoRater Data Dashboard", layout="wide")

st.title("⏱️ MotoRater Time-Series Dashboard")
st.markdown("Visualize and compare time-series data from local MotoRater Excel files.")

# --- Helper: Folder Picker ---
def select_folder():
    root = tk.Tk()
    root.withdraw()
    root.wm_attributes('-topmost', 1)
    folder_path = filedialog.askdirectory(master=root)
    root.destroy()
    return folder_path

# --- Session State ---
if 'folder_path' not in st.session_state:
    st.session_state.folder_path = ''

# --- Sidebar: Folder Selection ---
st.sidebar.header("1. Data Source")
col1, col2 = st.sidebar.columns([0.2, 0.8])

with col1:
    if st.button("📂"):
        selected = select_folder()
        if selected:
            st.session_state.folder_path = selected

with col2:
    folder_path = st.text_input(
        "Path", 
        value=st.session_state.folder_path, 
        label_visibility="collapsed",
        placeholder="C:/..."
    )

if folder_path != st.session_state.folder_path:
    st.session_state.folder_path = folder_path

# --- Helpers: Excel Loading ---
def get_excel_sheets(file_path):
    try:
        xls = pd.ExcelFile(file_path)
        return xls.sheet_names
    except:
        return None

# --- Helper Function to load data ---
# --- Helper Function to load data ---
@st.cache_data
def load_excel_data(file_path, sheet_name, file_name):
    try:
        df = pd.read_excel(file_path, sheet_name=sheet_name)
        
        # --- FIX: Remove bottom 6 rows for filtered Kinematics ---
        if "filtered" in file_name.lower() and sheet_name == "Kinematics":
            if len(df) > 6:  # Safety check to ensure the file actually has data
                df = df.iloc[:-6]
                
                # --- NEW: Safe numeric conversion to avoid FutureWarning ---
                def safe_convert(col):
                    try:
                        return pd.to_numeric(col)
                    except (ValueError, TypeError):
                        return col  # Leave text/categorical columns alone
                        
                df = df.apply(safe_convert)
                
        return df
    except Exception as e:
        return None

# --- Main Logic ---
if folder_path and os.path.isdir(folder_path):
    files = [f for f in os.listdir(folder_path) if f.endswith(('.xlsx', '.xls'))]
    
    if len(files) > 0:
        st.sidebar.success(f"Found {len(files)} files.")
        
        st.sidebar.header("2. Analysis Mode")
        compare_mode = st.sidebar.checkbox("🔄 Compare Multiple Files")

        # ==========================================
        # SINGLE FILE MODE
        # ==========================================
        if not compare_mode:
            selected_file = st.sidebar.selectbox("Select File:", files)
            full_file_path = os.path.join(folder_path, selected_file)
            sheet_names = get_excel_sheets(full_file_path)
            
            if sheet_names:
                selected_sheet = st.sidebar.selectbox("Select Sheet:", sheet_names) if len(sheet_names) > 1 else sheet_names[0]
                df = load_excel_data(full_file_path, selected_sheet, selected_file)
                
                if df is not None:
                    st.subheader(f"Analyzing: {selected_file}")
                    tab1, tab2 = st.tabs(["📈 Chart", "🧮 Statistics"])

                    all_cols = df.columns.tolist()
                    
                    # --- UPDATED LINE (Excludes "Time") ---
                    numeric_cols = [col for col in df.select_dtypes(include=['float64', 'int64']).columns.tolist() if col != "Time"]
                    time_col = [col for col in df.select_dtypes(include=['float64', 'int64']).columns.tolist() if col == "Time"]

                    with tab1:
                        c1, c2, c3 = st.columns(3)
                        
                        with c1: 
                            # --- FIXED X-AXIS ---
                            x_axis = "Time"
                            st.text_input("X-Axis (Fixed)", value=x_axis, disabled=True)
                            
                        with c2: y_axis = st.multiselect("Y-Axis (Values)", numeric_cols, default=None)
                        with c3: chart_type = st.selectbox("Chart Type", ["Line", "Scatter", "Bar"])

                        smoothing = st.slider("🌊 Noise Reduction (Rolling Avg)", 1, 50, 1) if chart_type == "Line" else 0

                        # Check if "Time" exists in this specific file
                        if x_axis not in all_cols:
                            st.error(f"Error: The column '{x_axis}' was not found in this Excel file.")
                            x_axis = None

                        if x_axis and y_axis:
                            plot_df = df.copy()
                            try: plot_df = plot_df.sort_values(by=x_axis)
                            except: pass

                            if smoothing > 1:
                                for col in y_axis:
                                    plot_df[f"{col} (Smoothed)"] = plot_df[col].rolling(window=smoothing).mean()
                                y_to_plot = [f"{col} (Smoothed)" for col in y_axis]
                            else:
                                y_to_plot = y_axis

                            title = f"{', '.join(y_axis)} over {x_axis}"
                            if chart_type == "Line": fig = px.line(plot_df, x=x_axis, y=y_to_plot, title=title)
                            elif chart_type == "Scatter": fig = px.scatter(plot_df, x=x_axis, y=y_axis, title=title)
                            else: fig = px.bar(plot_df, x=x_axis, y=y_axis, title=title, barmode='group')
                            st.plotly_chart(fig, width="stretch")
                        elif not y_axis:
                            st.info("👈 Select Y axes to see the chart.")

                    # --- TAB 2: Statistics ---
                    with tab2:
                        st.markdown("### 📊 Descriptive Statistics")

                        # ONLY show time duration if the sheet is Kinematics
                        if selected_sheet == "Kinematics" and "Time" in df.columns:
                            valid_times = pd.to_numeric(df["Time"], errors='coerce').dropna()
                            if not valid_times.empty:
                                time_start = valid_times.iloc[0]
                                time_end = valid_times.iloc[-1]
                                time_duration = time_end - time_start
                                st.markdown(f"##### ⏱️ Time duration: {time_duration:.2f} seconds")
                        
                        # --- NEW LOGIC: Toggle for all columns ---
                        show_all_stats = st.checkbox("Show statistics for ALL available measurements", value=False)
                        
                        # Decide which columns to calculate based on the checkbox
                        cols_to_stat = numeric_cols if show_all_stats else y_axis
                        
                        if cols_to_stat:
                            # Calculate and display the stats table
                            stats_df = df[cols_to_stat].describe().transpose()  
                            st.dataframe(stats_df.style.format("{:.5f}"))

                            st.divider()

                            # Correlation Matrix (Only show if more than 1 column is selected/available)
                            if len(cols_to_stat) > 1:
                                st.markdown("### 🔗 Correlation Matrix")
                                st.caption("Values close to 1 mean variables move together. Values close to -1 mean they move opposite.")
                                
                                corr = df[cols_to_stat].corr()
                                fig_corr = px.imshow(corr, text_auto=True, color_continuous_scale='RdBu_r', zmin=-1, zmax=1)
                                st.plotly_chart(fig_corr, width="stretch")
                        else:
                            st.info("👈 Select Y-axis columns in the Chart tab, or check the box above to generate statistics.")

        # ==========================================
        # MULTIPLE FILES COMPARE MODE
        # ==========================================
        else:
            st.sidebar.markdown("---")
            # 1. Multiselect to allow as many files as the user wants
            selected_files = st.sidebar.multiselect(
                "Select Files to Compare:", 
                files, 
                default=files[:2] if len(files) >= 2 else files
            )

            if len(selected_files) < 2:
                st.info("👈 Please select at least two files from the sidebar to compare.")
            else:
                # 2. Find sheets common to ALL selected files to prevent crashes
                common_sheets = None
                for f in selected_files:
                    sheets = get_excel_sheets(os.path.join(folder_path, f))
                    if sheets is not None:
                        if common_sheets is None:
                            common_sheets = set(sheets)
                        else:
                            common_sheets = common_sheets.intersection(set(sheets))
                
                if not common_sheets:
                    st.error("No common sheets found among the selected files.")
                else:
                    common_sheet = st.selectbox("Select Sheet to compare across files:", list(common_sheets))
                    
                    # 3. Load all selected dataframes into a dictionary
                    dfs = {}
                    for file in selected_files:
                        path = os.path.join(folder_path, file)
                        df = load_excel_data(path, common_sheet, file)
                        if df is not None:
                            dfs[file] = df
                    
                    if len(dfs) > 1:
                        st.subheader(f"⚖️ Comparing {len(dfs)} Files")

                        # 4. Display Time Durations dynamically (Conditional on Kinematics)
                        if common_sheet == "Kinematics":
                            # Create exactly enough columns for the number of files selected
                            time_cols = st.columns(len(dfs))
                            
                            for i, (filename, data) in enumerate(dfs.items()):
                                with time_cols[i]:
                                    if "Time" in data.columns:
                                        valid_times = pd.to_numeric(data["Time"], errors='coerce').dropna()
                                        if not valid_times.empty:
                                            t_start = valid_times.iloc[0]
                                            t_end = valid_times.iloc[-1]
                                            st.info(f"⏱️ **{filename}**\n\n{t_end - t_start:.2f} s")
                                        else:
                                            st.warning(f"⏱️ **{filename}**\n\nNo valid time.")
                                    else:
                                        st.warning(f"⏱️ **{filename}**\n\nNo 'Time' col.")
                            st.markdown("---")

                        # 5. Find Common Columns for the Y-Axis across ALL files
                        all_numeric_cols = [set(d.select_dtypes(include=['float64', 'int64']).columns) for d in dfs.values()]
                        common_numeric = list(set.intersection(*all_numeric_cols))
                        # Remove Time from Y-axis options
                        common_numeric = [col for col in common_numeric if col != "Time"]

                        if not common_numeric:
                            st.error("These files have no common numeric columns to plot.")
                        else:
                            c1, c2, c3 = st.columns(3)
                            
                            with c1: 
                                x_axis = "Time"
                                st.text_input("Common X-Axis (Fixed)", value=x_axis, disabled=True)
                                
                            with c2: y_axis = st.multiselect("Common Y-Axis", common_numeric, default=None)
                            with c3: chart_type = st.selectbox("Chart Type", ["Line", "Scatter"])

                            smoothing = st.slider("🌊 Noise Reduction (Rolling Avg)", 1, 50, 1) if chart_type == "Line" else 0

                            # Double check if "Time" is in all files
                            time_missing = any("Time" not in d.columns for d in dfs.values())
                            if time_missing:
                                st.error("Error: The column 'Time' is missing in one or more of the selected files.")
                                x_axis = None

                            if x_axis and y_axis:
                                all_plot_data = []
                                
                                # Process each file in the dictionary
                                for filename, data in dfs.items():
                                    plot_df = data[[x_axis] + y_axis].copy()
                                    plot_df['Source'] = filename
                                    
                                    try:
                                        plot_df = plot_df.sort_values(by=x_axis)
                                    except: pass

                                    # Apply Smoothing
                                    if smoothing > 1:
                                        for col in y_axis:
                                            plot_df[col] = plot_df[col].rolling(window=smoothing).mean()
                                            
                                    all_plot_data.append(plot_df)

                                # Combine everything
                                combined_df = pd.concat(all_plot_data, ignore_index=True)

                                # Melt the data for Plotly
                                melted_df = combined_df.melt(id_vars=[x_axis, 'Source'], value_vars=y_axis, var_name='Metric', value_name='Value')
                                
                                # Unified legend name (e.g. "File1.xlsx | Velocity")
                                melted_df['Legend'] = melted_df['Source'] + " | " + melted_df['Metric']

                                title = f"Comparing {', '.join(y_axis)} over {x_axis}"
                                if chart_type == "Line":
                                    fig = px.line(melted_df, x=x_axis, y='Value', color='Legend', title=title)
                                elif chart_type == "Scatter":
                                    fig = px.scatter(melted_df, x=x_axis, y='Value', color='Legend', title=title)

                                st.plotly_chart(fig, width="stretch")
                            elif not y_axis:
                                st.info("👈 Select common Y axes to compare the files.")
    else:
        st.warning("No Excel files found.")
elif folder_path:
    st.error("Invalid folder.")
else:
    st.info("👈 Select a folder to begin.")