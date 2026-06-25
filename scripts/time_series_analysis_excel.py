import streamlit as st
import pandas as pd
import plotly.express as px
import concurrent.futures
import threading
import io
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

# --- Page Configuration ---
# st.set_page_config(page_title="MotoRater Data Dashboard", layout="wide")

st.title("⏱️ MotoRater Time-Series analysis dashboard  - Excel")
st.markdown("Visualize and compare time-series data from uploaded MotoRater Excel files.")

# --- Server Safety Configuration ---
MAX_FILES_ALLOWED = 20 # Adjust this number based on your average file size


# --- Sidebar: Data Source ---
st.sidebar.header("1. Data Source")
uploaded_files = st.sidebar.file_uploader(
    "Upload Excel Files (.xlsx, .xls)", 
    type=['xlsx', 'xls'], 
    accept_multiple_files=True
)

# --- NEW: Dynamic Capacity Counter ---
current_file_count = len(uploaded_files)
remaining_space = MAX_FILES_ALLOWED - current_file_count

# Calculate progress (safeguard against going over 1.0 if they upload too many)
progress_value = min(current_file_count / MAX_FILES_ALLOWED, 1.0)
st.sidebar.progress(progress_value)

if remaining_space > 0:
    st.sidebar.caption(f"📁 **{current_file_count} / {MAX_FILES_ALLOWED}** files uploaded. You can add **{remaining_space}** more.")
elif remaining_space == 0:
    st.sidebar.caption(f"⚠️ **{current_file_count} / {MAX_FILES_ALLOWED}** files uploaded. Server is at maximum capacity.")

# --- Server Safety Check ---
if current_file_count > MAX_FILES_ALLOWED:
    st.sidebar.error(f"🚨 **Capacity Exceeded!** You uploaded {current_file_count} files.")
    st.error(f"To keep the server from crashing, please remove {abs(remaining_space)} file(s) to get back under the {MAX_FILES_ALLOWED} file limit.")
    st.stop() # Halts script execution

# Create a dictionary to easily access uploaded files by their names
file_dict = {file.name: file for file in uploaded_files}
files = list(file_dict.keys())

# --- Helpers: Excel Loading ---
@st.cache_data(show_spinner=False, max_entries=20, ttl=1800)
def get_excel_sheets(file_bytes):
    try:
        xls = pd.ExcelFile(io.BytesIO(file_bytes), engine='calamine')
        return xls.sheet_names
    except Exception as e:
        return None

@st.cache_data(show_spinner=False, max_entries=20, ttl=1800)
def load_excel_data(file_bytes, sheet_name, file_name):
    try:
        df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name, engine='calamine')
        
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
    except Exception as e:
        return None

# --- Main Logic ---
if len(files) > 0:
    st.sidebar.success(f"Loaded {len(files)} files.")
    
    st.sidebar.header("2. Analysis Mode")
    compare_mode = st.sidebar.checkbox("🔄 Compare Multiple Files")

    # ==========================================
    # SINGLE FILE MODE
    # ==========================================
    if not compare_mode:
        selected_file = st.sidebar.selectbox("Select File:", files)
        file_bytes = file_dict[selected_file].getvalue()
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
            ctx = get_script_run_ctx()
            common_sheets = None
            
            def get_excel_sheets_with_ctx(filename):
                add_script_run_ctx(threading.current_thread(), ctx)
                return get_excel_sheets(file_dict[filename].getvalue())

            with concurrent.futures.ThreadPoolExecutor() as executor:
                sheets_results = list(executor.map(get_excel_sheets_with_ctx, selected_files))
            
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
                    file_bytes = file_dict[filename].getvalue()
                    return filename, load_excel_data(file_bytes, common_sheet, filename)

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
                            
                        with c2: y_axis = st.multiselect("Common Y-Axis", common_numeric, default=None)
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
                            with color_cols[i % len(color_cols)]: 
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
else:
    st.info("👈 Upload your Excel files in the sidebar to begin.")






# --- Sidebar: System Controls ---
st.sidebar.header("⚙️ System")
st.sidebar.caption("If you are done with your analysis, you can clear the server's memory to free up server RAM for other users. This will clear all cached data and uploaded files.")
if st.sidebar.button("🧹 Clear Server Memory"):
    st.cache_data.clear()
    st.sidebar.success("Cache cleared! RAM freed.")