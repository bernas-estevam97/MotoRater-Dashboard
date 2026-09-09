import streamlit as st
import pandas as pd
import os
import io
import plotly.express as px
import concurrent.futures
import threading
try:
    import psutil
except ImportError:
    psutil = None

from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
from scripts.utils.file_utils import is_gui_available, safe_select_folder

# --- Page Configuration ---
# st.set_page_config(page_title="MotoRater Data Dashboard", layout="wide")

st.title("⏱️ MotoRater Time-Series analysis dashboard  - Excel")
st.markdown("Visualize and compare time-series data from MotoRater Excel files.")

# --- Session State ---
if 'folder_path' not in st.session_state:
    st.session_state.folder_path = ''
if 'excel_uploader_key' not in st.session_state:
    st.session_state.excel_uploader_key = 0

# --- Sidebar: Data Source ---
st.sidebar.header("1. Data Source")

gui_available = is_gui_available()
mode_options = ["📂 Local Folder", "📤 Upload Files"] if gui_available else ["📤 Upload Files"]
source_mode = st.sidebar.radio("Data Input Mode:", mode_options, horizontal=True)

files_map = {}  # filename -> bytes or callable returning bytes

if source_mode == "📂 Local Folder":
    col1, col2 = st.sidebar.columns([0.25, 0.75])
    with col1:
        if st.button("📂", help="Open native folder picker"):
            selected = safe_select_folder(title="Select MotoRater Excel Folder")
            if selected:
                st.session_state.folder_path = selected

    with col2:
        folder_path = st.text_input(
            "Path", 
            value=st.session_state.folder_path, 
            label_visibility="collapsed",
            placeholder="C:/path/to/folder"
        )

    if folder_path != st.session_state.folder_path:
        st.session_state.folder_path = folder_path

    if folder_path and os.path.isdir(folder_path):
        excel_filenames = [f for f in os.listdir(folder_path) if f.endswith(('.xlsx', '.xls'))]
        for f in excel_filenames:
            full_p = os.path.join(folder_path, f)
            files_map[f] = full_p
    elif folder_path:
        st.sidebar.error("Invalid directory path.")
else:
    # Upload Mode (Streamlit Cloud & local drag-and-drop)
    uploaded_files = st.sidebar.file_uploader(
        "Upload Excel Files (.xlsx, .xls)", 
        type=['xlsx', 'xls'], 
        accept_multiple_files=True,
        key=f"excel_uploader_{st.session_state.excel_uploader_key}"
    )
    if uploaded_files:
        for uf in uploaded_files:
            files_map[uf.name] = uf

files = list(files_map.keys())


# Helper to get bytes regardless of source
def get_file_bytes(filename: str) -> bytes:
    source = files_map[filename]
    if isinstance(source, str):
        with open(source, 'rb') as f:
            return f.read()
    else:
        return source.getvalue()


# --- Helpers: Excel Loading (Cached by bytes) ---
@st.cache_data(show_spinner=False, max_entries=50, ttl=1800)
def get_excel_sheets(file_bytes: bytes):
    try:
        xls = pd.ExcelFile(io.BytesIO(file_bytes), engine='calamine')
        return xls.sheet_names
    except Exception:
        try:
            xls = pd.ExcelFile(io.BytesIO(file_bytes))
            return xls.sheet_names
        except Exception:
            return None


@st.cache_data(show_spinner=False, max_entries=50, ttl=1800)
def load_excel_data(file_bytes: bytes, sheet_name: str, file_name: str):
    try:
        try:
            df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name, engine='calamine')
        except Exception:
            df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name)

        if "filtered" in file_name.lower() and sheet_name == "Kinematics":
            if len(df) > 7:
                df = df.iloc[:-7]
                cols_to_convert = df.select_dtypes(include=['object']).columns
                for col in cols_to_convert:
                    try:
                        df[col] = pd.to_numeric(df[col])
                    except (ValueError, TypeError):
                        pass
        return df
    except Exception:
        return None


# --- Main Logic ---
if len(files) > 0:
    st.sidebar.success(f"Found {len(files)} files.")
    
    st.sidebar.header("2. Analysis Mode")
    compare_mode = st.sidebar.checkbox("🔄 Compare Multiple Files")

    # ==========================================
    # SINGLE FILE MODE
    # ==========================================
    if not compare_mode:
        selected_file = st.sidebar.selectbox("Select File:", files)
        file_bytes = get_file_bytes(selected_file)
        sheet_names = get_excel_sheets(file_bytes)
        
        if sheet_names:
            selected_sheet = st.sidebar.selectbox("Select Sheet:", sheet_names) if len(sheet_names) > 1 else sheet_names[0]
            df = load_excel_data(file_bytes, selected_sheet, selected_file)
            
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
                        
                    with c2: 
                        y_axis = st.multiselect("Y-Axis (Values)", numeric_cols, default=None)
                    with c3: 
                        chart_type = st.selectbox("Chart Type", ["Line", "Scatter", "Bar", "Polar (Angles)", "Density Heatmap", "Box Plot"])

                    smoothing = st.slider("🌊 Noise Reduction (Rolling Avg)", 1, 50, 1) if chart_type == "Line" else 0

                    if x_axis not in all_cols:
                        st.error(f"Error: The column '{x_axis}' was not found in this Excel file.")
                        x_axis = None

                    if x_axis and y_axis:
                        plot_df = df.copy()
                        try: 
                            plot_df = plot_df.sort_values(by=x_axis)
                        except Exception: 
                            pass

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
            "Select Files to Compare:", 
            files, 
            default=files[:2] if len(files) >= 2 else files
        )

        if len(selected_files) < 2:
            st.info("👈 Please select at least two files from the sidebar to compare.")
        else:
            ctx = get_script_run_ctx()
            selected_bytes = {f: get_file_bytes(f) for f in selected_files}
            common_sheets = None
            
            def get_excel_sheets_with_ctx(f_bytes):
                add_script_run_ctx(threading.current_thread(), ctx)
                return get_excel_sheets(f_bytes)

            with concurrent.futures.ThreadPoolExecutor() as executor:
                sheets_results = list(executor.map(get_excel_sheets_with_ctx, selected_bytes.values()))
            
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
                dfs = {}
                
                def fetch_file_data_with_ctx(filename):
                    add_script_run_ctx(threading.current_thread(), ctx) 
                    return filename, load_excel_data(selected_bytes[filename], common_sheet, filename)

                with concurrent.futures.ThreadPoolExecutor() as executor:
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
                            
                        with c2: 
                            y_axis = st.multiselect("Common Y-Axis", common_numeric, default=None)
                        with c3: 
                            chart_type = st.selectbox("Chart Type", ["Line", "Scatter", "Polar (Angles)", "Box Plot"])

                        smoothing = st.slider("🌊 Noise Reduction (Rolling Avg)", 1, 50, 1) if chart_type == "Line" else 0

                        time_missing = any("Time" not in d.columns for d in dfs.values())
                        if time_missing:
                            st.error("Error: The column 'Time' is missing in one or more of the selected files.")
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
                                except Exception: 
                                    pass

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

    # Memory Monitor in Sidebar (safe fallback if psutil is unavailable)
    if psutil:
        try:
            st.sidebar.header("💻 Hardware & Memory")
            mem = psutil.virtual_memory()
            available_gb = mem.available / (1024**3)
            st.sidebar.progress(mem.percent / 100, text=f"RAM: {mem.percent}% Used ({available_gb:.1f} GB Free)")
        except Exception:
            pass

elif source_mode == "📂 Local Folder" and not folder_path:
    st.info("👈 Select a folder to begin. Click the 📂 button or enter the directory path.")
else:
    st.info("👈 Upload your Excel files in the sidebar to begin.")

# --- Sidebar: System Controls ---
st.sidebar.markdown("---")
st.sidebar.caption("Free cached data and memory:")
if st.sidebar.button("🧹 Clear Server Cache"):
    st.cache_data.clear()
    st.sidebar.success("Cache cleared!")