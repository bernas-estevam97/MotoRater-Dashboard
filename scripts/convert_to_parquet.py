import streamlit as st
import pandas as pd
import os
import time
import zipfile
from scripts.utils.file_utils import is_gui_available, safe_select_folder, safe_select_files

# --- Page Configuration ---
try:
    st.set_page_config(page_title="MotoRater Converter", page_icon="⚡", layout="wide")
except Exception:
    pass

st.title("⚡ Excel to Parquet/HDF5 Converter - Faster data formats for analysis")
st.markdown("Convert your heavy Excel files into blazing-fast formats for the MotoRater Dashboard.")

gui_ok = is_gui_available()
if not gui_ok:
    st.warning("ℹ️ **Local Tool Note:** Native file/folder selection dialogs require running locally on your workstation. When using Streamlit Cloud, you can upload and analyze files directly in the Time-Series and Kinematics tabs.")

# --- Session State ---
if 'source_paths' not in st.session_state:
    st.session_state.source_paths = []
if 'target_dir' not in st.session_state:
    st.session_state.target_dir = ''

# --- UI Controls ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("1. Source Data")
    
    selection_mode = st.radio("Selection Mode:", ["Entire Folder", "Specific File(s)"], horizontal=True)
    
    if selection_mode == "Entire Folder":
        if st.button("📂 Select Source Folder", disabled=not gui_ok):
            folder = safe_select_folder("Select Source Folder containing Excel files")
            if folder:
                st.session_state.source_paths = [
                    os.path.join(folder, f) for f in os.listdir(folder) 
                    if f.endswith(('.xlsx', '.xls'))
                ]
    else:
        if st.button("📄 Select Specific File(s)", disabled=not gui_ok):
            files = safe_select_files("Select Excel Files", filetypes=[("Excel files", "*.xlsx *.xls")])
            if files:
                st.session_state.source_paths = files

    # Display what is currently selected
    file_count = len(st.session_state.source_paths)
    st.text_input("Files Selected", value=f"{file_count} Excel file(s) queued", disabled=True)

with col2:
    st.subheader("2. Target Destination & Format")
    
    output_format = st.selectbox("Select Output Format:", ["Parquet", "HDF5"])
    
    if st.button("📂 Select Target Folder", disabled=not gui_ok):
        st.session_state.target_dir = safe_select_folder("Select Destination Folder")
        
    st.text_input("Target Path", value=st.session_state.target_dir, disabled=True)

st.divider()


def _convert_objects_to_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """Safely converts object columns to numeric without using deprecated errors='ignore'."""
    for col in df.select_dtypes(include=['object']).columns:
        try:
            df[col] = pd.to_numeric(df[col])
        except (ValueError, TypeError):
            pass
    return df


# --- Conversion Logic ---
if st.button("🚀 Start Conversion", type="primary", width="stretch"):
    if not st.session_state.source_paths:
        st.error("⚠️ Please select source files or a source folder first.")
    elif not st.session_state.target_dir:
        st.error("⚠️ Please select a target folder.")
    else:
        source_files = st.session_state.source_paths
        target_dir = st.session_state.target_dir

        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)

        st.info(f"Starting {output_format} conversion for {len(source_files)} files...")
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        with st.expander("Conversion Logs", expanded=True):
            log_container = st.container()

        start_time = time.time()
        success_count = 0

        for i, file_path in enumerate(source_files):
            file_name = os.path.basename(file_path)
            file_base_name = os.path.splitext(file_name)[0]
            
            status_text.text(f"⚙️ Processing ({i+1}/{len(source_files)}): {file_name}")

            try:
                # Load Excel via calamine if available, else openpyxl
                try:
                    xls = pd.ExcelFile(file_path, engine='calamine')
                except Exception:
                    xls = pd.ExcelFile(file_path)

                sheet_names = xls.sheet_names
                
                if output_format == "Parquet":
                    if len(sheet_names) > 1:
                        # Multiple sheets: Create a ZIP file containing the parquets
                        zip_path = os.path.join(target_dir, f"{file_base_name}_parquet.zip")
                        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                            for sheet in sheet_names:
                                df = pd.read_excel(xls, sheet_name=sheet)
                                
                                # MotoRater Filter Logic
                                if "_filtered" in file_base_name and sheet == "kinematics":
                                    df = df.iloc[:-7]
                                
                                df = _convert_objects_to_numeric(df)
                                
                                # Write to temp file, zip it, then remove temp
                                temp_pq = os.path.join(target_dir, f"temp_{sheet}.parquet")
                                df.to_parquet(temp_pq, engine='pyarrow', index=False)
                                zipf.write(temp_pq, arcname=f"{file_base_name}_{sheet}.parquet")
                                if os.path.exists(temp_pq):
                                    os.remove(temp_pq)
                                
                        log_container.success(f"✅ Converted & Zipped: {file_name} ({len(sheet_names)} sheets)")
                    else:
                        # Single sheet: Just write the Parquet file directly
                        sheet = sheet_names[0]
                        df = pd.read_excel(xls, sheet_name=sheet)
                        
                        if "_filtered" in file_base_name and sheet == "kinematics":
                            df = df.iloc[:-7]
                        df = _convert_objects_to_numeric(df)
                            
                        pq_path = os.path.join(target_dir, f"{file_base_name}.parquet")
                        df.to_parquet(pq_path, engine='pyarrow', index=False)
                        log_container.success(f"✅ Converted: {file_name} to Parquet")

                elif output_format == "HDF5":
                    hdf5_path = os.path.join(target_dir, f"{file_base_name}.h5")
                    for sheet in sheet_names:
                        df = pd.read_excel(xls, sheet_name=sheet)
                        
                        if "_filtered" in file_base_name and sheet == "kinematics":
                            df = df.iloc[:-7]
                        df = _convert_objects_to_numeric(df)
                        
                        safe_sheet_name = sheet.replace(" ", "_").replace("-", "_")
                        df.to_hdf(hdf5_path, key=safe_sheet_name, mode='a', format='table')
                        
                    log_container.success(f"✅ Converted: {file_name} to HDF5 ({len(sheet_names)} datasets)")

                success_count += 1

            except Exception as e:
                log_container.error(f"❌ Error converting {file_name}: {e}")
            
            progress_bar.progress((i + 1) / len(source_files))

        end_time = time.time()
        status_text.text("✅ Conversion Complete!")
        st.success(f"🎉 Successfully converted {success_count} out of {len(source_files)} files to {output_format} in {end_time - start_time:.2f} seconds.")