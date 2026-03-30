import streamlit as st
import pandas as pd
import os
import time
import tkinter as tk
from tkinter import filedialog

# --- Page Configuration ---
# st.set_page_config(page_title="MotoRater Parquet Converter", page_icon="⚡")

st.title("⚡ Excel to Parquet Converter")
st.markdown("Convert your heavy Excel files into blazing-fast Parquet folders for the MotoRater Dashboard.")

# --- Helper: Folder Picker ---
def select_folder():
    root = tk.Tk()
    root.withdraw()
    root.wm_attributes('-topmost', 1)
    folder_path = filedialog.askdirectory(master=root)
    root.destroy()
    return folder_path

# --- Session State ---
if 'source_dir' not in st.session_state:
    st.session_state.source_dir = ''
if 'target_dir' not in st.session_state:
    st.session_state.target_dir = ''

# --- UI Controls ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("1. Source Folder")
    st.caption("Folder containing your .xlsx files")
    if st.button("📂 Select Source Excel Folder"):
        st.session_state.source_dir = select_folder()
    st.text_input("Source Path", value=st.session_state.source_dir, disabled=True)

with col2:
    st.subheader("2. Target Folder")
    st.caption("Where to save the new Parquet data")
    if st.button("📂 Select Target Destination"):
        st.session_state.target_dir = select_folder()
    st.text_input("Target Path", value=st.session_state.target_dir, disabled=True)

st.divider()

# --- Conversion Logic ---
if st.button("🚀 Start Conversion", type="primary", use_container_width=True):
    if not st.session_state.source_dir or not st.session_state.target_dir:
        st.error("⚠️ Please select both a Source and Target folder first.")
    else:
        source_dir = st.session_state.source_dir
        target_dir = st.session_state.target_dir

        if not os.path.exists(target_dir):
            os.makedirs(target_dir)

        excel_files = [f for f in os.listdir(source_dir) if f.endswith(('.xlsx', '.xls'))]
        
        if not excel_files:
            st.warning(f"No Excel files found in {source_dir}")
        else:
            # Set up UI elements for feedback
            st.info(f"Found {len(excel_files)} Excel files. Starting conversion...")
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Create an expander to hide the verbose logs so the UI stays clean
            with st.expander("Conversion Logs", expanded=True):
                log_container = st.container()

            start_time = time.time()
            success_count = 0

            # Iterate through files
            for i, file in enumerate(excel_files):
                file_path = os.path.join(source_dir, file)
                file_base_name = os.path.splitext(file)[0]
                file_target_dir = os.path.join(target_dir, file_base_name)
                
                # Update status
                status_text.text(f"⚙️ Processing ({i+1}/{len(excel_files)}): {file}")
                
                if not os.path.exists(file_target_dir):
                    os.makedirs(file_target_dir)

                try:
                    # Load the Excel file using the fast calamine engine
                    xls = pd.ExcelFile(file_path, engine='calamine')
                    
                    for sheet in xls.sheet_names:
                        df = pd.read_excel(xls, sheet_name=sheet)
                        
                        # Vectorized conversion for object columns
                        for col in df.select_dtypes(include=['object']):
                            df[col] = pd.to_numeric(df[col], errors='ignore')
                        
                        # Save to Parquet
                        parquet_path = os.path.join(file_target_dir, f"{sheet}.parquet")
                        df.to_parquet(parquet_path, engine='pyarrow', index=False)
                    
                    log_container.success(f"✅ Converted: {file} ({len(xls.sheet_names)} sheets)")
                    success_count += 1
                except Exception as e:
                    log_container.error(f"❌ Error converting {file}: {e}")
                
                # Update progress bar
                progress_bar.progress((i + 1) / len(excel_files))

            # Final Summary
            end_time = time.time()
            status_text.text("✅ Conversion Complete!")
            # st.balloons() 
            st.success(f"🎉 Successfully converted {success_count} out of {len(excel_files)} files in {end_time - start_time:.2f} seconds.")