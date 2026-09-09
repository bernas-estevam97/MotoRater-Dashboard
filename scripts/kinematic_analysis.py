"""
Kinematics Longitudinal Analysis Page.
Proxies to the optimized engine (kinematic_analysis_optimized.py) to ensure
all performance optimizations, caching, and multi-format support are utilized.
"""

import runpy
from pathlib import Path
import streamlit as st

_optimized_path = Path(__file__).parent / "kinematic_analysis_optimized.py"

if _optimized_path.exists():
    runpy.run_path(str(_optimized_path), run_name="__main__")
else:
    st.error("Error: scripts/kinematic_analysis_optimized.py could not be found.")