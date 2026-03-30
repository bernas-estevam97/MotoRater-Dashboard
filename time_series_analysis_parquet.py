import streamlit as st
import pandas as pd
import os
import plotly.express as px
import tkinter as tk
from tkinter import filedialog
import concurrent.futures
import threading
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

# --- Page Configuration ---
# st.set_page_config(page_title="MotoRater Data Dashboard", layout="wide")

st.title("⏱️ MotoRater Time-Series analysis dashboard  - Parquet")
st.markdown("Visualize and compare time-series data from local MotoRater Parquet files.")

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

# To get the "sheets" (which are now just parquet files in the folder)
def get_parquet_sheets(folder_path, file_folder_name):
    # file_folder_name would be "Test_Run_01"
    target_dir = os.path.join(folder_path, file_folder_name)
    if os.path.exists(target_dir):
        # Return names without the .parquet extension to keep the UI looking the same
        return [f.replace('.parquet', '') for f in os.listdir(target_dir) if f.endswith('.parquet')]
    return []

# To load the data
@st.cache_data
def load_parquet_data(folder_path, file_folder_name, sheet_name):
    try:
        file_path = os.path.join(folder_path, file_folder_name, f"{sheet_name}.parquet")
        
        # This will load in milliseconds compared to Excel
        df = pd.read_parquet(file_path, engine='pyarrow')
        
        # Filter logic remains the same
        if "filtered" in file_folder_name.lower() and sheet_name == "Kinematics":
            if len(df) > 6:
                df = df.iloc[:-6]
                
        return df
    except Exception as e:
        return None

# --- Main Logic ---
if folder_path and os.path.isdir(folder_path):
    # CHANGED: Look for directories inside the selected folder that contain .parquet files
    files = [
        f for f in os.listdir(folder_path) 
        if os.path.isdir(os.path.join(folder_path, f)) and 
           any(fname.endswith('.parquet') for fname in os.listdir(os.path.join(folder_path, f)))
    ]
    
    if len(files) > 0:
        st.sidebar.success(f"Found {len(files)} data folders.")
        
        st.sidebar.header("2. Analysis Mode")
        compare_mode = st.sidebar.checkbox("🔄 Compare Multiple Files")

        # ==========================================
        # SINGLE FILE MODE
        # ==========================================
        if not compare_mode:
            selected_file = st.sidebar.selectbox("Select Data Folder:", files)
            # CHANGED: Use Parquet functions
            sheet_names = get_parquet_sheets(folder_path, selected_file)
            
            if sheet_names:
                selected_sheet = st.sidebar.selectbox("Select Sheet:", sheet_names) if len(sheet_names) > 1 else sheet_names[0]
                # CHANGED: Use Parquet functions
                df = load_parquet_data(folder_path, selected_file, selected_sheet)
                
                if df is not None:
                    st.subheader(f"Analyzing: {selected_file}")
                    tab1, tab2 = st.tabs(["📈 Chart", "🧮 Statistics"])

                    all_cols = df.columns.tolist()
                    numeric_cols = [col for col in df.select_dtypes(include=['float64', 'int64']).columns.tolist() if col != "Time"]
                    
                    with tab1:
                        c1, c2, c3 = st.columns(3)
                        
                        with c1: 
                            x_axis = "Time"
                            st.text_input("X-Axis (Fixed)", value=x_axis, disabled=True)
                            
                        with c2: y_axis = st.multiselect("Y-Axis (Values)", numeric_cols, default=None)
                        with c3: chart_type = st.selectbox("Chart Type", ["Line", "Scatter", "Bar"])

                        smoothing = st.slider("🌊 Noise Reduction (Rolling Avg)", 1, 50, 1) if chart_type == "Line" else 0

                        if x_axis not in all_cols:
                            st.error(f"Error: The column '{x_axis}' was not found in this data.")
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
                            # NEW: Logic for handling the new chart types
                            if chart_type == "Line": 
                                fig = px.line(plot_df, x=x_axis, y=y_to_plot, title=title)
                            elif chart_type == "Scatter": 
                                fig = px.scatter(plot_df, x=x_axis, y=y_axis, title=title)
                            elif chart_type == "Bar": 
                                fig = px.bar(plot_df, x=x_axis, y=y_axis, title=title, barmode='group')
                            elif chart_type == "Polar (Angles)":
                                polar_df = plot_df.melt(id_vars=[x_axis], value_vars=y_to_plot, var_name='Metric', value_name='Angle')
                                fig = px.scatter_polar(polar_df, r=x_axis, theta='Angle', color='Metric', title=title)
                                fig.update_layout(polar=dict(angularaxis=dict(direction="clockwise")))
                            elif chart_type == "Density Heatmap":
                                heat_df = plot_df.melt(id_vars=[x_axis], value_vars=y_to_plot, var_name='Metric', value_name='Value')
                                fig = px.density_heatmap(heat_df, x=x_axis, y='Value', facet_col='Metric', title=title, nbinsx=50, nbinsy=30)
                            elif chart_type == "Box Plot":
                                box_df = plot_df.melt(id_vars=[x_axis], value_vars=y_to_plot, var_name='Metric', value_name='Value')
                                fig = px.box(box_df, x='Metric', y='Value', color='Metric', title=title)
                            st.plotly_chart(fig, width='stretch')
                        elif not y_axis:
                            st.info("👈 Select Y axes to see the chart.")

                    # --- TAB 2: Statistics ---
                    with tab2:
                        st.markdown("### 📊 Descriptive Statistics")

                        if selected_sheet == "Kinematics" and "Time" in df.columns:
                            valid_times = pd.to_numeric(df["Time"], errors='coerce').dropna()
                            if not valid_times.empty:
                                time_start = valid_times.iloc[0]
                                time_end = valid_times.iloc[-1]
                                time_duration = time_end - time_start
                                st.markdown(f"##### ⏱️ Time duration: {time_duration:.2f} seconds")
                        
                        show_all_stats = st.checkbox("Show statistics for ALL available measurements", value=False)
                        cols_to_stat = numeric_cols if show_all_stats else y_axis
                        
                        if cols_to_stat:
                            stats_df = df[cols_to_stat].describe().transpose()  
                            st.dataframe(stats_df.style.format("{:.5f}"))
                            st.divider()

                            if len(cols_to_stat) > 1:
                                st.markdown("### 🔗 Correlation Matrix")
                                st.caption("Values close to 1 mean variables move together. Values close to -1 mean they move opposite to each other.")
                                corr = df[cols_to_stat].corr()
                                fig_corr = px.imshow(corr, text_auto=True, color_continuous_scale='RdBu_r', zmin=-1, zmax=1)
                                st.plotly_chart(fig_corr, width='stretch')
                        else:
                            st.info("Check the box above to generate statistics. While the box is checked you can swap between files as it will update accordingly.")

        # ==========================================
        # MULTIPLE FILES COMPARE MODE
        # ==========================================
        else:
            st.sidebar.markdown("---")
            selected_files = st.sidebar.multiselect(
                "Select Files to Compare:", 
                files, 
                default=files[:2] if len(files) >= 2 else files
            )

            if len(selected_files) < 2:
                st.info("👈 Please select at least two files from the sidebar to compare.")
            else:
                # 🛑 GRAB THE CONTEXT FROM THE MAIN THREAD 🛑
                ctx = get_script_run_ctx()

                # OPTIMIZATION 4: Multi-threading for finding common sheets
                file_paths = [os.path.join(folder_path, f) for f in selected_files]
                common_sheets = None
                
                # Wrapper function to inject context before getting sheets
                def get_excel_sheets_with_ctx(filepath):
                    add_script_run_ctx(threading.current_thread(), ctx)
                    return get_parquet_sheets(filepath)

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    # Use the wrapper function here
                    sheets_results = list(executor.map(get_excel_sheets_with_ctx, file_paths))
                
                for sheets in sheets_results:
                    if sheets is not None:
                        if common_sheets is None:
                            common_sheets = set(sheets)
                        else:
                            common_sheets = common_sheets.intersection(set(sheets))
                
                if not common_sheets:
                    st.error("No common sheets found among the selected files.")
                else:
                    common_sheet = st.selectbox("Select Sheet to compare across files:", list(common_sheets))
                    
                    # OPTIMIZATION 4: Multi-threading for loading Excel data
                    dfs = {}
                    
                    # Wrapper function to inject context before fetching data
                    def fetch_file_data_with_ctx(filename):
                        add_script_run_ctx(threading.current_thread(), ctx) # Inject context
                        path = os.path.join(folder_path, filename)
                        return filename, load_parquet_data(path, common_sheet, filename)

                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        # Use the wrapper function here
                        results = executor.map(fetch_file_data_with_ctx, selected_files)
                        for filename, df in results:
                            if df is not None:
                                dfs[filename] = df

        
                    
                    if len(dfs) > 1:
                        st.subheader(f"⚖️ Comparing {len(dfs)} Files")

                        if common_sheet == "Kinematics":
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

                        all_numeric_cols = [set(d.select_dtypes(include=['float64', 'int64']).columns) for d in dfs.values()]
                        common_numeric = list(set.intersection(*all_numeric_cols))
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

                            time_missing = any("Time" not in d.columns for d in dfs.values())
                            if time_missing:
                                st.error("Error: The column 'Time' is missing in one or more of the selected files.")
                                x_axis = None

                            if x_axis and y_axis:
                                all_plot_data = []
                                
                                for filename, data in dfs.items():
                                    plot_df = data[[x_axis] + y_axis].copy()
                                    plot_df['Source'] = filename
                                    
                                    try:
                                        plot_df = plot_df.sort_values(by=x_axis)
                                    except: pass

                                    if smoothing > 1:
                                        for col in y_axis:
                                            plot_df[col] = plot_df[col].rolling(window=smoothing).mean()
                                            
                                    all_plot_data.append(plot_df)

                                combined_df = pd.concat(all_plot_data, ignore_index=True)
                                melted_df = combined_df.melt(id_vars=[x_axis, 'Source'], value_vars=y_axis, var_name='Metric', value_name='Value')
                                melted_df['Legend'] = melted_df['Source'] + " | " + melted_df['Metric']

                                title = f"Comparing {', '.join(y_axis)} over {x_axis}"
                                # NEW: Handlers for multiple file chart compare modes
                                if chart_type == "Line":
                                    fig = px.line(melted_df, x=x_axis, y='Value', color='Legend', title=title)
                                elif chart_type == "Scatter":
                                    fig = px.scatter(melted_df, x=x_axis, y='Value', color='Legend', title=title)
                                elif chart_type == "Polar (Angles)":
                                    fig = px.scatter_polar(melted_df, r=x_axis, theta='Value', color='Legend', title=title)
                                    fig.update_layout(polar=dict(angularaxis=dict(direction="clockwise")))
                                elif chart_type == "Box Plot":
                                    # Group by Metric, color by Source for easy distribution comparison
                                    fig = px.box(melted_df, x='Metric', y='Value', color='Source', title=title)

                                st.plotly_chart(fig, width='stretch')
                            elif not y_axis:
                                st.info("👈 Select common Y axes to compare the files.")
    else:
        st.warning("No Parquet data folders found. Make sure you select the target folder from the conversion script.")
elif folder_path:
    st.error("Invalid folder.")
else:
    st.info("👈 Select a folder to begin. Click the 📂 in the left side column")