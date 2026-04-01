import streamlit as st
import pandas as pd
import plotly.express as px
import concurrent.futures
import threading
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
import io

# --- Page Configuration ---
# st.set_page_config(page_title="MotoRater Data Dashboard", layout="wide")

st.title("⏱️ MotoRater Time-Series analysis dashboard  - Parquet")
st.markdown("Visualize and compare time-series data from uploaded MotoRater Parquet files.")

# --- Sidebar: File Upload ---
st.sidebar.header("1. Data Source")
st.sidebar.info("Upload one or multiple Parquet files below.")

# NEW: Web-friendly file uploader
uploaded_files = st.sidebar.file_uploader(
    "Choose Parquet files", 
    type=['parquet'], 
    accept_multiple_files=True,
    label_visibility="collapsed"
)

# Create a dictionary to easily access files by their name
file_dict = {file.name: file for file in uploaded_files} if uploaded_files else {}
files = list(file_dict.keys())

# --- Helpers: Parquet Loading ---
@st.cache_data
def load_parquet_data(file_bytes, file_name):
    try:
        # NEW: Read directly from browser memory
        df = pd.read_parquet(io.BytesIO(file_bytes), engine='pyarrow')
        
        # Filter logic adapted to look at the filename
        if "filtered" in file_name.lower() and "kinematics" in file_name.lower():
            if len(df) > 6:
                df = df.iloc[:-6]
                
        return df
    except Exception as e:
        return None

# --- Main Logic ---
if len(files) > 0:
    st.sidebar.success(f"Loaded {len(files)} Parquet files.")
    
    st.sidebar.header("2. Analysis Mode")
    compare_mode = st.sidebar.checkbox("🔄 Compare Multiple Files")

    # ==========================================
    # SINGLE FILE MODE
    # ==========================================
    if not compare_mode:
        selected_file = st.sidebar.selectbox("Select Parquet File:", files)
        
        file_bytes = file_dict[selected_file].getvalue()
        df = load_parquet_data(file_bytes, selected_file)
        
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

                if "kinematics" in selected_file.lower() and "Time" in df.columns:
                    valid_times = pd.to_numeric(df["Time"]).dropna()
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
            "Select Parquet Files to Compare:", 
            files, 
            default=files[:2] if len(files) >= 2 else files
        )

        if len(selected_files) < 2:
            st.info("👈 Please select at least two files from the sidebar to compare.")
        else:
            ctx = get_script_run_ctx()
            dfs = {}
            
            def fetch_file_data_with_ctx(filename):
                add_script_run_ctx(threading.current_thread(), ctx) 
                file_bytes = file_dict[filename].getvalue()
                return filename, load_parquet_data(file_bytes, filename)

            with concurrent.futures.ThreadPoolExecutor() as executor:
                results = executor.map(fetch_file_data_with_ctx, selected_files)
                for filename, df in results:
                    if df is not None:
                        dfs[filename] = df
            
            if len(dfs) > 1:
                st.subheader(f"⚖️ Comparing {len(dfs)} Files")

                # Display time metadata if applicable
                time_cols = st.columns(len(dfs))
                for i, (filename, data) in enumerate(dfs.items()):
                    with time_cols[i]:
                        if "Time" in data.columns:
                            valid_times = pd.to_numeric(data["Time"]).dropna()
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
                    with c3: chart_type = st.selectbox("Chart Type", ["Line", "Scatter", "Polar (Angles)", "Box Plot"])

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
                        
                        if chart_type == "Line":
                            fig = px.line(melted_df, x=x_axis, y='Value', color='Legend', title=title)
                        elif chart_type == "Scatter":
                            fig = px.scatter(melted_df, x=x_axis, y='Value', color='Legend', title=title)
                        elif chart_type == "Polar (Angles)":
                            fig = px.scatter_polar(melted_df, r=x_axis, theta='Value', color='Legend', title=title)
                            fig.update_layout(polar=dict(angularaxis=dict(direction="clockwise")))
                        elif chart_type == "Box Plot":
                            fig = px.box(melted_df, x='Metric', y='Value', color='Source', title=title)

                        st.plotly_chart(fig, width='stretch')
                    elif not y_axis:
                        st.info("👈 Select common Y axes to compare the files.")
else:
    st.info("👈 Upload your Parquet files in the sidebar to begin.")