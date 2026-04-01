import streamlit as st

# --- Landing Page Content ---
st.title("❓ MotoRater Suite - Tutorial and help")
st.markdown("---")

st.markdown("""
        # 📈 MotoRater Time series analysis: User Guide & Tutorial

---

## 📂 1. Getting Started
1. Go to the **Data Source** section in the left sidebar.
2. Click the 📂 button to open a folder picker. 
3. Select the local folder on your computer that contains your MotoRater `.xlsx`, `.xls` or '.parquet' files if you used the converter.
4. Once loaded, the sidebar will confirm how many files were found.

---

## 🔍 2. Analysis Modes

You can switch between two main modes using the **"🔄 Compare Multiple Files"** checkbox in the sidebar.

### 👤 Single File Mode
Use this mode to deep-dive into a specific session.
* **Select a File & Sheet:** Choose the specific Excel file and worksheet (e.g., `Kinematics`) you want to analyze.
* **📈 Chart Tab:** Select one or more **Y-Axis** variables to plot against **Time**. 
* **🧮 Statistics Tab:** Automatically calculates total session duration, descriptive statistics (mean, median, min, max), and displays a **Correlation Matrix** to see which behaviors or movements happen together.

### ⚖️ Compare Multiple Files Mode
Use this mode to overlay data from different subjects, trials, or days.
* Select two or more files from the sidebar.
* The app will automatically find **common sheets** and **common numeric columns** across all selected files.
* Charts will automatically group and color-code your data by the source file so you can easily spot differences in behavior.

---

## 📊 3. Choosing the Right Chart Type

Depending on the behavior you are analyzing, different charts will reveal different patterns:

* **Line & Scatter Plots:** Best for viewing raw, continuous measurements (like velocity or distance) over the entire session. 
* **Bar Chart:** Great for comparing distinct, aggregated values.
* **Polar (Angles):**  Essential for directional data like head angles or body orientation. It plots the angle on a circle and the time/magnitude as the distance from the center, preventing confusing line jumps when an angle wraps from 359° to 0°.
* **Density Heatmap:**  Shows the concentration of data points. Perfect for identifying where an animal spent the most time or what measurement ranges were most common during the session.
* **Box Plot:** 

[Image of Box plot distribution]
 Drops the timeline entirely to show the statistical distribution (median, quartiles, and outliers) of your selected measurements. Highly recommended when comparing multiple files!

---

## 💡 Pro Tips

* **🌊 Noise Reduction:** Behavioral tracking data can be incredibly noisy. If your **Line Chart** looks like a messy scribble, use the **Noise Reduction (Rolling Avg)** slider. This smooths out micro-jitters in the tracking data, making macro-trends much easier to see.
* **Smart Filtering:** If you are analyzing a "filtered" Kinematics file, the dashboard automatically removes the bottom 6 rows of metadata to prevent the app from crashing and ensures your data types are clean.
        """)