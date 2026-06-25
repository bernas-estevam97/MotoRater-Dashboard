import streamlit as st
import pandas as pd
import os
import time
import zipfile
import tempfile
from io import BytesIO

# --- Page Configuration ---
st.set_page_config(page_title="MotoRater Converter", page_icon="⚡", layout="wide")

st.title("⚡ Excel to Parquet/HDF5 Converter")
st.markdown("Upload your heavy Excel files and convert them into blazing-fast formats for the MotoRater Dashboard.")

# --- UI Controls ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("1. Source Data")
    # Replaced tkinter with Streamlit's native file uploader
    uploaded_files = st.file_uploader(
        "Upload Excel Files", 
        type=["xlsx", "xls"], 
        accept_multiple_files=True
    )

with col2:
    st.subheader("2. Output Format")
    # Target directory removed; cloud apps return files via download buttons instead
    output_format = st.selectbox("Select Output Format:", ["Parquet", "HDF5"])

st.divider()

# --- Conversion Logic ---
if st.button("🚀 Start Conversion", type="primary", use_container_width=True):
    if not uploaded_files:
        st.error("⚠️ Please upload at least one Excel file first.")
    else:
        st.info(f"Starting {output_format} conversion for {len(uploaded_files)} files...")
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        with st.expander("Conversion Logs", expanded=True):
            log_container = st.container()

        start_time = time.time()
        success_count = 0

        # Create an in-memory buffer to hold the final ZIP file we will let the user download
        final_zip_buffer = BytesIO()
        
        # Use a temporary directory on the cloud server to store files while processing
        with tempfile.TemporaryDirectory() as temp_dir:
            with zipfile.ZipFile(final_zip_buffer, 'w', zipfile.ZIP_DEFLATED) as final_zip:
                
                for i, uploaded_file in enumerate(uploaded_files):
                    file_name = uploaded_file.name
                    file_base_name = os.path.splitext(file_name)[0]
                    
                    status_text.text(f"⚙️ Processing ({i+1}/{len(uploaded_files)}): {file_name}")

                    try:
                        # Load Excel directly from the uploaded file buffer via calamine
                        xls = pd.ExcelFile(uploaded_file, engine='calamine')
                        sheet_names = xls.sheet_names
                        
                        if output_format == "Parquet":
                            # --- PARQUET LOGIC ---
                            if len(sheet_names) > 1:
                                # Multiple sheets: Create an internal ZIP for these sheets
                                internal_zip_name = f"{file_base_name}_parquet.zip"
                                internal_zip_path = os.path.join(temp_dir, internal_zip_name)
                                
                                with zipfile.ZipFile(internal_zip_path, 'w', zipfile.ZIP_DEFLATED) as sheet_zip:
                                    for sheet in sheet_names:
                                        df = pd.read_excel(xls, sheet_name=sheet)
                                        
                                        # MotoRater Filter Logic
                                        if "_filtered" in file_base_name and sheet == "kinematics":
                                            df = df.iloc[:-7]
                                        
                                        # Object to Numeric
                                        for col in df.select_dtypes(include=['object']):
                                            df[col] = pd.to_numeric(df[col], errors='ignore')
                                        
                                        temp_pq = os.path.join(temp_dir, f"temp_{sheet}.parquet")
                                        df.to_parquet(temp_pq, engine='pyarrow', index=False)
                                        sheet_zip.write(temp_pq, arcname=f"{file_base_name}_{sheet}.parquet")
                                        os.remove(temp_pq)
                                        
                                # Add the multi-sheet zip to the final master zip
                                final_zip.write(internal_zip_path, arcname=internal_zip_name)
                                log_container.success(f"✅ Converted & Zipped: {file_name} ({len(sheet_names)} sheets)")
                            else:
                                # Single sheet Parquet
                                sheet = sheet_names[0]
                                df = pd.read_excel(xls, sheet_name=sheet)
                                
                                if "_filtered" in file_base_name and sheet == "kinematics":
                                    df = df.iloc[:-7]
                                for col in df.select_dtypes(include=['object']):
                                    df[col] = pd.to_numeric(df[col], errors='ignore')
                                    
                                pq_path = os.path.join(temp_dir, f"{file_base_name}.parquet")
                                df.to_parquet(pq_path, engine='pyarrow', index=False)
                                
                                # Add direct parquet to master zip
                                final_zip.write(pq_path, arcname=f"{file_base_name}.parquet")
                                log_container.success(f"✅ Converted: {file_name} to Parquet")

                        elif output_format == "HDF5":
                            # --- HDF5 LOGIC ---
                            hdf5_path = os.path.join(temp_dir, f"{file_base_name}.h5")
                            for sheet in sheet_names:
                                df = pd.read_excel(xls, sheet_name=sheet)
                                
                                if "_filtered" in file_base_name and sheet == "kinematics":
                                    df = df.iloc[:-7]
                                for col in df.select_dtypes(include=['object']):
                                    df[col] = pd.to_numeric(df[col], errors='ignore')
                                
                                safe_sheet_name = sheet.replace(" ", "_").replace("-", "_")
                                df.to_hdf(hdf5_path, key=safe_sheet_name, mode='a', format='table')
                                
                            final_zip.write(hdf5_path, arcname=f"{file_base_name}.h5")
                            log_container.success(f"✅ Converted: {file_name} to HDF5 ({len(sheet_names)} datasets)")

                        success_count += 1

                    except Exception as e:
                        log_container.error(f"❌ Error converting {file_name}: {e}")
                    
                    progress_bar.progress((i + 1) / len(uploaded_files))

        end_time = time.time()
        status_text.text("✅ Processing Complete!")
        st.success(f"🎉 Successfully converted {success_count} out of {len(uploaded_files)} files to {output_format} in {end_time - start_time:.2f} seconds.")
        
        # --- Provide Download Button ---
        if success_count > 0:
            final_zip_buffer.seek(0)
            st.download_button(
                label="⬇️ Download Converted Files (ZIP)",
                data=final_zip_buffer,
                file_name=f"converted_files_{output_format.lower()}.zip",
                mime="application/zip",
                type="primary",
                use_container_width=True
            )