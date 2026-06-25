import streamlit as st
import pandas as pd
import os
import plotly.express as px
import tkinter as tk
from tkinter import filedialog
import concurrent.futures
import threading
import psutil # NEW: Imported for hardware detection
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

# --- Page Configuration ---
# st.set_page_config(page_title="MotoRater Data Dashboard", layout="wide")

st.title("⏱️ MotoRater Time-Series analysis dashboard - Parquet / HDF5")
st.markdown("Visualize and compare time-series data from local MotoRater Parquet and HDF5 files.")

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

# MODIFIED: Get sheets (files) handling both Parquet and HDF5
def get_data_sheets(folder_path, file_folder_name):
    target_dir = os.path.join(folder_path, file_folder_name)
    if os.path.exists(target_dir):
        valid_extensions = ('.parquet', '.hdf5', '.h5')
        sheets = []
        for f in os.listdir(target_dir):
            for ext in valid_extensions:
                if f.endswith(ext):
                    sheets.append(f.replace(ext, ''))
        return list(set(sheets)) # Return unique sheet names
    return []

# MODIFIED: Load data handling both Parquet and HDF5
@st.cache_data
def load_data(folder_path, file_folder_name, sheet_name):
    try:
        target_dir = os.path.join(folder_path, file_folder_name)
        valid_extensions = ('.parquet', '.hdf5', '.h5')
        file_path = None
        ext_used = None
        
        for ext in valid_extensions:
            temp_path = os.path.join(target_dir, f"{sheet_name}{ext}")
            if os.path.exists(temp_path):
                file_path = temp_path
                ext_used = ext
                break
                
        if not file_path:
            return None
            
        if ext_used == '.parquet':
            df = pd.read_parquet(file_path, engine='pyarrow')
        elif ext_used in ('.hdf5', '.h5'):
            df = pd.read_hdf(file_path)
            
        # Filter logic remains the same
        if "filtered" in file_folder_name.lower() and sheet_name == "Kinematics":
            if len(df) > 6:
                df = df.iloc[:-6]
                
        return df
    except Exception as e:
        return None

# --- Main Logic ---
if folder_path and os.path.isdir(folder_path):
    valid_exts = ('.parquet', '.hdf5', '.h5')
    
    # MODIFIED: Look for directories that contain either .parquet, .hdf5, or .h5 files
    files = [
        f for f in os.listdir(folder_path) 
        if os.path.isdir(os.path.join(folder_path, f)) and 
           any(fname.endswith(valid_exts) for fname in os.listdir(os.path.join(folder_path, f)))
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
            sheet_names = get_data_sheets(folder_path, selected_file)
            
            if sheet_names:
                selected_sheet = st.sidebar.selectbox("Select Sheet:", sheet_names) if len(sheet_names) > 1 else sheet_names[0]
                df = load_data(folder_path, selected_file, selected_sheet)
                
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
                        with c3: chart_type = st.selectbox("Chart Type", ["Line", "Scatter", "Bar", "Polar (Angles)", "Density Heatmap", "Box Plot"])

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
                            
                            st.markdown("### 🎨 Custom Metric Colors")
                            color_cols = st.columns(len(y_axis))
                            custom_color_map = {}
                            default_px_colors = ["#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A", "#19D3F3", "#FF6692", "#B6E880"]

                            for i, col in enumerate(y_axis):
                                with color_cols[i % len(color_cols)]:
                                    chosen_color = st.color_picker(
                                        f"{col}", 
                                        value=default_px_colors[i % len(default_px_colors)],
                                        key=f"single_color_{col}"
                                    )
                                    custom_color_map[col] = chosen_color
                                    custom_color_map[f"{col} (Smoothed)"] = chosen_color

                            if chart_type == "Line": 
                                fig = px.line(plot_df, x=x_axis, y=y_to_plot, title=title, color_discrete_map=custom_color_map)
                            elif chart_type == "Scatter": 
                                fig = px.scatter(plot_df, x=x_axis, y=y_axis, title=title, color_discrete_map=custom_color_map)
                            elif chart_type == "Bar": 
                                fig = px.bar(plot_df, x=x_axis, y=y_axis, title=title, barmode='group', color_discrete_map=custom_color_map)
                            elif chart_type == "Polar (Angles)":
                                polar_df = plot_df.melt(id_vars=[x_axis], value_vars=y_to_plot, var_name='Metric', value_name='Angle')
                                fig = px.scatter_polar(polar_df, r=x_axis, theta='Angle', color='Metric', title=title, color_discrete_map=custom_color_map)
                                fig.update_layout(polar=dict(angularaxis=dict(direction="clockwise")))
                            elif chart_type == "Density Heatmap":
                                heat_df = plot_df.melt(id_vars=[x_axis], value_vars=y_to_plot, var_name='Metric', value_name='Value')
                                fig = px.density_heatmap(heat_df, x=x_axis, y='Value', facet_col='Metric', title=title, nbinsx=50, nbinsy=30)
                            elif chart_type == "Box Plot":
                                box_df = plot_df.melt(id_vars=[x_axis], value_vars=y_to_plot, var_name='Metric', value_name='Value')
                                fig = px.box(box_df, x='Metric', y='Value', color='Metric', title=title, color_discrete_map=custom_color_map)
                                
                            st.plotly_chart(fig, width='stretch')
                        elif not y_axis:
                            st.info("👈 Select Y axes to see the chart.")

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
                "Select Data Folders to Compare:", 
                files, 
                default=files[:2] if len(files) >= 2 else files
            )

            if len(selected_files) < 2:
                st.info("👈 Please select at least two folders from the sidebar to compare.")
            else:
                # ==========================================
                # COMMENTED OUT FUNCTIONAL RESTRICTION
                # ==========================================
                # if len(selected_files) > recommended_max_files:
                #     st.error(f"🛑 You have selected {len(selected_files)} folders, but your system memory only safely supports ~{recommended_max_files} right now. Please deselect some folders to prevent the app from crashing.")
                #     st.stop() # Added to halt execution if uncommented
                # else:
                # ==========================================
                
                ctx = get_script_run_ctx()

                file_paths = [os.path.join(folder_path, f) for f in selected_files]
                common_sheets = None
                
                def get_data_sheets_with_ctx(filepath):
                    add_script_run_ctx(threading.current_thread(), ctx)
                    # Extract the folder name back out of the full path for the function
                    base_folder = os.path.dirname(filepath)
                    folder_name = os.path.basename(filepath)
                    return get_data_sheets(base_folder, folder_name)

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    sheets_results = list(executor.map(get_data_sheets_with_ctx, file_paths))
                
                for sheets in sheets_results:
                    if sheets is not None:
                        if common_sheets is None:
                            common_sheets = set(sheets)
                        else:
                            common_sheets = common_sheets.intersection(set(sheets))
                
                if not common_sheets:
                    st.error("No common sheets/files found among the selected folders.")
                else:
                    common_sheet = st.selectbox("Select Data Sheet to compare across folders:", list(common_sheets))
                    
                    dfs = {}
                    
                    def fetch_file_data_with_ctx(filename):
                        add_script_run_ctx(threading.current_thread(), ctx) 
                        return filename, load_data(folder_path, filename, common_sheet)

                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        results = executor.map(fetch_file_data_with_ctx, selected_files)
                        for filename, df in results:
                            if df is not None:
                                dfs[filename] = df

                    if len(dfs) > 1:
                        st.subheader(f"⚖️ Comparing {len(dfs)} Folders")

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
                            st.error("These datasets have no common numeric columns to plot.")
                        else:
                            c1, c2, c3 = st.columns(3)
                            
                            with c1: 
                                x_axis = "Time"
                                st.text_input("Common X-Axis (Fixed)", value=x_axis, disabled=True)
                                
                            with c2: y_axis = st.multiselect("Common Y-Axis", common_numeric, default=None)
                            with c3: chart_type = st.selectbox("Chart Type", ["Line", "Scatter", "Polar (Angles)", "Box Plot"])

                            smoothing = st.slider("🌊 Noise Reduction (Rolling Avg)", 1, 50, 1) if chart_type == "Line" else 0

                            time_missing = any("Time" not in d.columns for d in dfs.values())
                            if time_missing:
                                st.error("Error: The column 'Time' is missing in one or more of the selected datasets.")
                                x_axis = None

                            st.markdown("### 🎨 Custom File Colors")
                            color_cols = st.columns(len(dfs))
                            file_colors = {}
                            default_px_colors = ["#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A", "#19D3F3", "#FF6692", "#B6E880"]

                            for i, filename in enumerate(dfs.keys()):
                                with color_cols[i]:
                                    file_colors[filename] = st.color_picker(
                                        f"{filename}", 
                                        value=default_px_colors[i % len(default_px_colors)]
                                    )

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
                                
                                custom_color_map = {}
                                for source, color in file_colors.items():
                                    custom_color_map[source] = color 
                                    for metric in y_axis:
                                        custom_color_map[f"{source} | {metric}"] = color 

                                if chart_type == "Line":
                                    fig = px.line(melted_df, x=x_axis, y='Value', color='Legend', title=title, color_discrete_map=custom_color_map)
                                elif chart_type == "Scatter":
                                    fig = px.scatter(melted_df, x=x_axis, y='Value', color='Legend', title=title, color_discrete_map=custom_color_map)
                                elif chart_type == "Polar (Angles)":
                                    fig = px.scatter_polar(melted_df, r=x_axis, theta='Value', color='Legend', title=title, color_discrete_map=custom_color_map)
                                    fig.update_layout(polar=dict(angularaxis=dict(direction="clockwise")))
                                elif chart_type == "Box Plot":
                                    fig = px.box(melted_df, x='Metric', y='Value', color='Source', title=title, color_discrete_map=custom_color_map)

                                st.plotly_chart(fig, width='stretch')
                            elif not y_axis:
                                st.info("👈 Select common Y axes to compare the files.")
        # ==========================================
        # NEW: HARDWARE & MEMORY MONITOR
        # ==========================================
        st.sidebar.header("💻 Hardware & Memory")
        mem = psutil.virtual_memory()
        available_gb = mem.available / (1024**3)
        total_gb = mem.total / (1024**3)
        
        st.sidebar.progress(mem.percent / 100, text=f"RAM: {mem.percent}% Used ({available_gb:.1f} GB Free)")

        # Estimate memory requirements based on sub-folder contents
        total_size_bytes = 0
        for d in files:
            d_path = os.path.join(folder_path, d)
            for f in os.listdir(d_path):
                if f.endswith(valid_exts):
                    total_size_bytes += os.path.getsize(os.path.join(d_path, f))
                    
        avg_size_bytes = total_size_bytes / len(files) if files else 0
        
        # Heuristic: Parquet/HDF5 are heavily compressed. DataFrames can take ~6x the disk size in RAM
        estimated_ram_per_folder = avg_size_bytes * 6 
        
        # Safe threshold: Use max 70% of currently available RAM
        safe_ram_budget = mem.available * 0.70 
        
        if estimated_ram_per_folder > 0:
            recommended_max_files = max(1, int(safe_ram_budget // estimated_ram_per_folder))
        else:
            recommended_max_files = len(files)

        if recommended_max_files < len(files):
            st.sidebar.warning(f"⚠️ **Memory Alert:** Your data files are highly compressed. In RAM, they are very large. It is recommended to compare a maximum of **{recommended_max_files} folders** at once to avoid crashing.")
        else:
            st.sidebar.success(f"✅ System memory is sufficient for comparing all available folders in this directory.")
        # ==========================================
    else:
        st.warning("No Parquet or HDF5 folders found.")
elif folder_path:
    st.error("Invalid folder.")
else:
    st.info("👈 Select a folder to begin. Click the 📂 in the left side column")