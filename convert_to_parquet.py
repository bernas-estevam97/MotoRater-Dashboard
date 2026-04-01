import streamlit as st
import pandas as pd
import os
import time
import io
import zipfile

# --- Page Configuration ---
# st.set_page_config(page_title="MotoRater Parquet Converter", page_icon="⚡")

st.title("⚡ Excel to Parquet Converter")
st.markdown("Convert your heavy Excel files into blazing-fast Parquet folders for the MotoRater Dashboard.")

# --- 1. File Upload ---
st.subheader("1. Source Files")
# Updated caption to explicitly mention dragging and dropping folders
st.caption("Upload your .xlsx files here. **Tip: You can drag and drop an entire folder directly into this box!**")
uploaded_files = st.file_uploader(
    "Choose Excel files", 
    type=['xlsx', 'xls'], 
    accept_multiple_files=True,
    label_visibility="collapsed"
)

st.divider()

# --- 2. Conversion Logic ---
st.subheader("2. Convert & Download")

# We use session state to hold the zip file so the download button doesn't vanish on refresh
if 'zip_data' not in st.session_state:
    st.session_state.zip_data = None

if st.button("🚀 Start Conversion", type="primary"):
    if not uploaded_files:
        st.error("⚠️ Please upload at least one Excel file first.")
    else:
        st.info(f"Found {len(uploaded_files)} Excel files. Starting conversion...")
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        with st.expander("Conversion Logs", expanded=True):
            log_container = st.container()

        start_time = time.time()
        success_count = 0

        # Create a BytesIO buffer to hold the ZIP file in memory
        zip_buffer = io.BytesIO()
        
        # Open the ZIP file in write mode
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED, False) as zip_file:
            
            # Iterate through uploaded files
            for i, file in enumerate(uploaded_files):
                file_base_name = os.path.splitext(file.name)[0]
                
                status_text.text(f"⚙️ Processing ({i+1}/{len(uploaded_files)}): {file.name}")
                
                try:
                    # Load the Excel file directly from the uploaded bytes
                    xls = pd.ExcelFile(io.BytesIO(file.getvalue()), engine='calamine')
                    
                    for sheet in xls.sheet_names:
                        df = pd.read_excel(xls, sheet_name=sheet)
                        
                        # --- NEW: DIRECT SLICING LOGIC ---
                        # If the sheet is 'Kinematics' (adjust name if needed) and has enough rows
                        if sheet == "Kinematics" and len(df) > 7:
                            # Simply drop the last 7 rows
                            df = df.iloc[:-7]
                            
                        # If you want this to apply to ALL sheets regardless of name, 
                        # you can change the above to just:
                        # if len(df) > 7:
                        #     df = df.iloc[:-7]
                        # Vectorized conversion for any remaining object columns
                        for col in df.select_dtypes(include=['object']):
                            df[col] = pd.to_numeric(df[col])
                        
                        # Save to Parquet in memory!
                        parquet_buffer = io.BytesIO()
                        df.to_parquet(parquet_buffer, engine='pyarrow', index=False)
                        
                        # Write the parquet bytes into our ZIP archive
                        # NEW: We append the original file name to the sheet name!
                        archive_path = f"{file_base_name}/{file_base_name}_{sheet}.parquet"
                        zip_file.writestr(archive_path, parquet_buffer.getvalue())
                    
                    log_container.success(f"✅ Converted: {file.name} ({len(xls.sheet_names)} sheets)")
                    success_count += 1
                except Exception as e:
                    log_container.error(f"❌ Error converting {file.name}: {e}")
                
                progress_bar.progress((i + 1) / len(uploaded_files))

        end_time = time.time()
        status_text.text("✅ Conversion Complete!")
        st.success(f"🎉 Successfully converted {success_count} out of {len(uploaded_files)} files in {end_time - start_time:.2f} seconds.")
        
        # Save the final zip bytes into session state
        st.session_state.zip_data = zip_buffer.getvalue()

# --- 3. Download & Memory Management ---
# If the zip data exists in session state, show the download AND clear buttons
if st.session_state.zip_data is not None:
    st.markdown("---")
    st.success("Your files are ready! Please clear the memory once you have downloaded your data.")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.download_button(
            label="📥 Download Converted Parquet Files (.zip)",
            data=st.session_state.zip_data,
            file_name="MotoRater_Parquet_Data.zip",
            mime="application/zip",
            type="primary"
        )
        
    with col2:
        # The Clear button wipes the data from the server's RAM and reruns the app to reset the UI
        if st.button("🗑️ Clear Memory & Reset"):
            st.session_state.zip_data = None
            st.rerun()