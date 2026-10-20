import io
import os
import re
import tempfile
import warnings
import zipfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from joblib import Parallel, delayed
from statsmodels.tools.sm_exceptions import ConvergenceWarning

try:
    from scripts.utils.data_mappings import column_rename_map
    from scripts.utils import stats_engine as se
except ImportError:
    from utils.data_mappings import column_rename_map
    from utils import stats_engine as se

warnings.simplefilter('ignore', ConvergenceWarning)

TP = se.TP
LEVEL_UI = {'error': st.error, 'warning': st.warning, 'info': st.info}

try:
    st.set_page_config(layout="wide")
except Exception:
    pass


# ---------------------------------------------------------------------------
# Data loading & preparation
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="Loading data...")
def load_data(file_bytes: bytes, filename: str) -> dict:
    """Cached by file content. Supports Excel, HDF5, single Parquet, or ZIP of Parquets."""
    file_io = io.BytesIO(file_bytes)
    name = filename.lower()
    if name.endswith((".h5", ".hdf5")):
        # HDFStore needs a real file path, not a buffer.
        with tempfile.NamedTemporaryFile(delete=False, suffix=".h5") as tmp:
            tmp.write(file_bytes)
        try:
            with pd.HDFStore(tmp.name, mode="r") as store:
                return {k.strip("/"): store[k].rename(columns=column_rename_map) for k in store.keys()}
        finally:
            os.remove(tmp.name)
    if name.endswith(".parquet"):
        return {"Data": pd.read_parquet(file_io).rename(columns=column_rename_map)}
    if name.endswith(".zip"):
        out = {}
        with zipfile.ZipFile(file_io, "r") as z:
            for member in z.namelist():
                if member.endswith(".parquet"):
                    with z.open(member) as f:
                        out[member.split("/")[-1][:-8]] = pd.read_parquet(f).rename(columns=column_rename_map)
        return out
    xls = pd.ExcelFile(file_io)
    return {s: pd.read_excel(xls, sheet_name=s).rename(columns=column_rename_map) for s in xls.sheet_names}


@st.cache_data(show_spinner=False)
def convert_units(_raw: dict, filename: str, unit: str) -> dict:
    """m -> mm conversion, cached per file + unit (the raw dict is keyed by filename)."""
    if unit != "Millimeters (mm)":
        return _raw
    out = {}
    for sheet, df in _raw.items():
        df = df.copy()
        rename = {}
        for col in df.columns:
            if isinstance(col, str) and col.endswith(("(m)", "(m/s)", "(m/s²)")):
                df[col] = pd.to_numeric(df[col], errors='coerce') * 1000
                rename[col] = col.replace("(m)", "(mm)").replace("(m/s)", "(mm/s)").replace("(m/s²)", "(mm/s²)")
        out[sheet] = df.rename(columns=rename)
    return out


def build_final_df(df_sheet, mapping, metric, group_order):
    """Join measurements to the ID mapping and average trials per subject x timepoint."""
    # Plain pandas: pl.from_pandas segfaulted under Streamlit with polars 2.0 + pandas 3.
    out = pd.merge(df_sheet[['Ids', metric]].astype({'Ids': str}), mapping.astype({'Ids': str}), on='Ids')
    out[metric] = pd.to_numeric(out[metric], errors='coerce')
    out = out.dropna(subset=[metric]).groupby(['Subject_ID', 'Group', TP], as_index=False)[metric].mean()
    out['_metric_'] = out[metric].astype(float)
    out['Group'] = pd.Categorical(out['Group'], categories=group_order)
    return out.sort_values([TP, 'Group'])


@st.cache_data(show_spinner="Checking assumptions...")
def cached_assumptions(final_df, alpha):
    return se.check_assumptions(final_df, alpha)


@st.cache_data(show_spinner="Running statistics...")
def cached_analysis(final_df, test, posthoc, correction, alpha, gee_family, gee_cov, metric, _assumptions):
    return se.run_analysis(final_df, test, posthoc, correction, alpha, gee_family, gee_cov, metric, _assumptions)


def active_mapping():
    mapping = st.session_state.mapping_df
    excluded = st.session_state.get('exclude_subjects_ui')
    return mapping[~mapping['Subject_ID'].isin(excluded)] if excluded else mapping


def metric_columns(df):
    return [c for c in df.columns if c != 'Ids']


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------
@st.fragment
def render_plot_section(final_df, comparisons, color_map, plot_metric, timepoints, annotation_color,
                        plot_width, plot_height):
    """Isolated rerun fragment: changing plot options never re-runs the statistics."""
    two_groups = final_df['Group'].nunique() == 2
    c1, c2, c3 = st.columns(3)
    plot_format = c1.selectbox("Plot type", ["Line Plot", "Bar Plot", "Box Plot", "Violin Plot"])
    if plot_format in ["Line Plot", "Bar Plot"]:
        show_error_bars, show_points = c2.checkbox("Show SEM error bars", value=True), False
    else:
        show_error_bars, show_points = False, c2.checkbox("Show all data points", value=True)
    show_stars = c3.checkbox("Show significance on plot", value=two_groups, disabled=not two_groups,
                             help="Available for 2-group comparisons. With 3+ groups see the "
                                  "Multiple comparisons tab.")

    with st.expander("Axis settings", expanded=False):
        x1, x2 = st.columns(2)
        force_exact_ticks = x1.checkbox("Label every timepoint", value=True)
        custom_x_range = x2.checkbox("Custom X-axis range", value=False)
        if custom_x_range:
            lo, hi = float(min(timepoints)), float(max(timepoints))
            margin = (hi - lo) * 0.1 if hi != lo else 1.0
            r1, r2 = st.columns(2)
            x_min = r1.number_input("X min", value=lo - margin)
            x_max = r2.number_input("X max", value=hi + margin)

    plot_df = final_df.assign(Group=final_df['Group'].astype(str))
    summary_df = (plot_df.groupby(['Group', TP])[plot_metric].agg(['mean', 'sem']).reset_index()
                  .rename(columns={'mean': plot_metric, 'sem': 'SEM'}).sort_values(TP))
    order = {'Group': [str(g) for g in final_df['Group'].cat.categories]}
    common = dict(color='Group', color_discrete_map=color_map, category_orders=order,
                  title=f"Longitudinal progression of {plot_metric}")

    if plot_format == "Line Plot":
        fig = px.line(summary_df, x=TP, y=plot_metric, markers=True,
                      error_y='SEM' if show_error_bars else None, **common)
    elif plot_format == "Bar Plot":
        fig = px.bar(summary_df, x=TP, y=plot_metric, barmode='group',
                     error_y='SEM' if show_error_bars else None, **common)
    elif plot_format == "Box Plot":
        fig = px.box(plot_df, x=TP, y=plot_metric, points="all" if show_points else False, **common)
    else:
        fig = px.violin(plot_df, x=TP, y=plot_metric, box=True, points="all" if show_points else False, **common)

    xaxis = dict(type='linear')
    if force_exact_ticks:
        xaxis['tickvals'] = sorted(plot_df[TP].unique())
    if custom_x_range:
        xaxis['range'] = [x_min, x_max]
    fig.update_layout(xaxis=xaxis)

    if show_stars and two_groups and not comparisons.empty:
        y_max, y_min = plot_df[plot_metric].max(), plot_df[plot_metric].min()
        offset = (y_max - y_min) * 0.08 if y_max != y_min else abs(y_max) * 0.05
        top = y_max
        for _, row in comparisons.dropna(subset=['p_corr']).iterrows():
            tp = row[TP]
            if plot_format in ["Line Plot", "Bar Plot"] and show_error_bars:
                cell = summary_df[summary_df[TP] == tp]
                y_tp = (cell[plot_metric] + cell['SEM'].fillna(0)).max()
            else:
                y_tp = plot_df.loc[plot_df[TP] == tp, plot_metric].max()
            if pd.isna(y_tp):
                continue
            star = row['Summary']
            top = max(top, y_tp + offset)
            fig.add_annotation(x=tp, y=y_tp + offset, text=star, showarrow=False,
                               font=dict(size=14 if star == "ns" else 22, color=annotation_color, family="Arial"))
        fig.update_layout(yaxis=dict(range=[y_min - offset * 0.5, top + offset * 1.5]))

    fig.update_layout(margin=dict(t=50), width=plot_width, height=plot_height,
                      font=dict(family="Segoe UI Semibold", size=16))
    st.plotly_chart(fig, width=plot_width)  # "stretch" overrides the layout width


def render_single_metric_job(metric, df_sheet, mapping, timepoints, group_order, color_map,
                             plot_width, plot_height, test, posthoc, correction, alpha, gee_family, gee_cov):
    """Headless Matplotlib PNG renderer + statistics for one measurement (runs in a worker process)."""
    loop = pd.merge(df_sheet[['Ids', metric]].astype({'Ids': str}), mapping.astype({'Ids': str}), on='Ids')
    loop[metric] = pd.to_numeric(loop[metric], errors='coerce')
    loop = loop.dropna(subset=[metric]).groupby(['Subject_ID', 'Group', TP], as_index=False)[metric].mean()
    if loop.empty or loop['Group'].nunique() < 2:
        return None, None, None
    loop['_metric_'] = loop[metric].astype(float)
    loop['Group'] = pd.Categorical(loop['Group'], categories=group_order)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = se.run_analysis(loop, test, posthoc, correction, alpha, gee_family, gee_cov, metric)
        comps = res['comparisons'] if res['error'] is None else pd.DataFrame()
        stats_rows = comps.assign(Measurement=metric, Test=se.label(res['test'])) if not comps.empty else None
    except Exception:
        comps, stats_rows = pd.DataFrame(), None

    summary = (loop.groupby(['Group', TP], observed=True)[metric].agg(['mean', 'sem']).reset_index()
               .rename(columns={'mean': metric, 'sem': 'SEM'}).sort_values(TP))

    fig, ax = plt.subplots(figsize=(plot_width / 100, plot_height / 100), dpi=100)
    for group in group_order:
        g = summary[summary['Group'] == group]
        if not g.empty:
            ax.errorbar(g[TP], g[metric], yerr=g['SEM'], marker='o', linewidth=2, markersize=6, capsize=4,
                        label=group, color=color_map.get(group))
    ax.set_title(f"Longitudinal progression of {metric}", fontsize=13)
    ax.set_xlabel("Timepoint (Weeks)")
    ax.set_ylabel(metric)
    ax.set_xticks(sorted(timepoints))
    ax.grid(True, color="lightgrey", linewidth=0.8)
    ax.spines[['top', 'right']].set_visible(False)
    ax.legend(frameon=False)

    if len(group_order) == 2 and not comps.empty:
        y_max, y_min = loop[metric].max(), loop[metric].min()
        offset = (y_max - y_min) * 0.08 if y_max != y_min else abs(y_max) * 0.05
        top = y_max
        for _, row in comps.dropna(subset=['p_corr']).iterrows():
            cell = summary[summary[TP] == row[TP]]
            if cell.empty:
                continue
            y_pos = float((cell[metric] + cell['SEM'].fillna(0)).max()) + offset
            top = max(top, y_pos)
            ax.text(float(row[TP]), y_pos, row['Summary'], ha='center', va='bottom',
                    fontsize=12 if row['Summary'] == "ns" else 16)
        ax.set_ylim(y_min - offset * 0.5, top + offset * 1.5)

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    safe = "".join(c for c in metric if c.isalnum() or c == ' ').rstrip()
    return safe, buf.getvalue(), stats_rows


def tidy(df):
    """Round floats and print timepoints without trailing .0 for display."""
    show = df.copy()
    if TP in show.columns:
        show[TP] = show[TP].map(lambda v: f"{v:g}")
    num = show.select_dtypes('float').columns
    show[num] = show[num].round(4)
    return show


def format_comparisons(comps):
    show = tidy(comps)
    show['p (unadjusted)'] = show.pop('p_unc').apply(se.fmt_p)
    show['p (adjusted)'] = show.pop('p_corr').apply(se.fmt_p)
    show['Significant'] = show['Significant'].map({True: "Yes", False: "No"})
    return show


def highlight_significant(row):
    color = 'background-color: rgba(46, 204, 113, 0.18)' if row.get('Significant') == "Yes" else ''
    return [color] * len(row)


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
st.title("🐁 Kinematics Longitudinal Analyzer")
st.caption("Upload a cleaned kinematics file, define your groups, then choose and run the statistical analysis.")

uploaded_file = st.file_uploader("Upload your cleaned data file", type=['xlsx', 'h5', 'hdf5', 'parquet', 'zip'])

if not uploaded_file:
    st.info("Upload an Excel, HDF5, Parquet or ZIP-of-Parquet file to get started. "
            "See **Tutorial - Kinematics** in the sidebar for the expected format.")
    st.stop()

file_bytes = uploaded_file.getvalue()
if st.session_state.get('uploaded_filename') != uploaded_file.name:
    st.session_state.data_dict = load_data(file_bytes, uploaded_file.name)
    st.session_state.uploaded_filename = uploaded_file.name
    for key in ('mapping_df', 'group_definitions_final', 'exclude_subjects_ui'):
        st.session_state.pop(key, None)

raw_data_dict = st.session_state.data_dict
sheet_names = list(raw_data_dict.keys())
if not sheet_names:
    st.error("No readable sheets/tables were found in this file.")
    st.stop()

# --- Sidebar (grouped so it stays short) ---
with st.sidebar:
    st.header("Display settings")
    with st.expander("📏 Units", expanded=False):
        distance_unit = st.radio("Distance units", ["Meters (m)", "Millimeters (mm)"],
                                 help="Converts distance, velocity and acceleration. "
                                      "Statistical significance is unaffected.")
    color_map = {}
    if 'mapping_df' in st.session_state:
        with st.expander("🎨 Group colors", expanded=False):
            groups_found = sorted(g for g in st.session_state.mapping_df['Group'].unique() if g != "Unknown")
            palette = px.colors.qualitative.Plotly + px.colors.qualitative.D3
            for i, grp in enumerate(groups_found):
                color_map[grp] = st.color_picker(grp, palette[i % len(palette)], key=f"color_{grp}")
    with st.expander("📐 Plot appearance", expanded=False):
        annotation_color = st.color_picker("Significance marker color", "#000000",
                                           help="Use white (#FFFFFF) in dark mode.")
        plot_width = st.slider("Plot width (px)", 600, 2400, 1000, 50,
                               help="Applies to on-screen plots and exported PNGs.")
        plot_height = st.slider("Plot height (px)", 400, 1600, 600, 50)

data_dict = convert_units(raw_data_dict, uploaded_file.name, distance_unit)

tab_data, tab_groups, tab_stats, tab_radar = st.tabs([
    "📂 Data", "🧪 Groups & Subjects", "🧮 Statistical Analysis", "🕸️ Radar Profile"])

# --- TAB: DATA ---
with tab_data:
    first_df = data_dict[sheet_names[0]]
    n_ids = first_df['Ids'].nunique() if 'Ids' in first_df.columns else 0
    k1, k2, k3 = st.columns(3)
    k1.metric("Sheets", len(sheet_names))
    k2.metric("Measurements", len(metric_columns(first_df)))
    k3.metric("Unique trial IDs", n_ids)

    selected_sheet = st.selectbox("Sheet", sheet_names, key="viewer_sheet_select")
    st.dataframe(data_dict[selected_sheet], width='stretch', height=420)
    with st.expander("Trial IDs found", expanded=False):
        if 'Ids' in first_df.columns:
            st.dataframe(pd.DataFrame({"Ids": first_df['Ids'].unique()}), width='stretch', hide_index=True)
        else:
            st.error("No 'Ids' column found. Please check your file format.")

# --- TAB: GROUPS & SUBJECTS ---
with tab_groups:
    st.subheader("Define groups and parse timepoints")
    st.markdown("**Group Name** is shown on plots. **Tag in ID** is the text searched for in each trial ID "
                "(longest tags are matched first).")

    if 'group_definitions' not in st.session_state:
        st.session_state.group_definitions = pd.DataFrame({
            "Group Name": ["Wildtype", "Transgenic", "WT Male", "WT Female", "TG Male", "TG Female"],
            "Tag in ID": ["WT", "TG", "WT_M", "WT_F", "TG_M", "TG_F"],
        })
    edited_groups = st.data_editor(st.session_state.group_definitions, num_rows="dynamic", width='stretch',
                                   hide_index=True, key="groups_editor")

    first_df = data_dict[sheet_names[0]]
    clicked = st.button("Extract variables from IDs", type="primary", key="extract_vars_btn")
    if clicked and 'Ids' not in first_df.columns:
        st.error("Could not find an 'Ids' column to extract from.")
    elif clicked:
        valid_groups = edited_groups.dropna(how='all').copy()
        valid_groups["Tag in ID"] = valid_groups["Tag in ID"].astype(str).str.strip()
        valid_groups["Group Name"] = valid_groups["Group Name"].astype(str).str.strip()
        valid_groups = valid_groups[valid_groups["Tag in ID"] != ""]
        valid_groups = valid_groups.sort_values("Tag in ID", key=lambda c: c.str.len(), ascending=False)

        def extract_timepoint(id_str):
            m = re.search(r'(\d+)[Ww]', id_str) or re.search(r'[Tt](\d+)', id_str)
            return int(m.group(1)) if m else None

        def extract_subject_id(id_str):
            tokens = id_str.split('_')
            for i, token in enumerate(tokens):
                if re.fullmatch(r'(?:[Ww]eek\s*)?\d+\s*[Ww]|[Ww]\s*\d+|[Tt]\s*\d+|\d+\s*[Tt]', token):
                    return "_".join(tokens[:i])
            return tokens[0]

        records = []
        for id_str in first_df['Ids'].unique():
            s = str(id_str)
            matched = [r["Group Name"] for _, r in valid_groups.iterrows() if r["Tag in ID"].upper() in s.upper()]
            for grp in matched or ["Unknown"]:
                records.append({"Ids": id_str, TP: extract_timepoint(s), "Subject_ID": extract_subject_id(s),
                                "Group": grp})
        st.session_state.mapping_df = pd.DataFrame(records)
        st.session_state.group_definitions_final = valid_groups
        st.rerun()

    if 'mapping_df' in st.session_state:
        mapping_all = st.session_state.mapping_df
        st.success("Variables extracted. Group colors are now available in the sidebar.")

        st.markdown("#### Exclude subjects")
        st.multiselect("Subjects removed from every plot and statistic (e.g., outliers, dropouts):",
                       options=sorted(mapping_all['Subject_ID'].dropna().unique()), key="exclude_subjects_ui")

        clean = active_mapping()
        counts = (clean[clean['Group'] != 'Unknown'].groupby('Group')
                  .agg(**{'Subjects (N)': ('Subject_ID', 'nunique'), 'Timepoints': (TP, 'nunique'),
                          'Trials': ('Ids', 'nunique')}).reset_index())
        st.markdown("#### Group summary")
        st.dataframe(counts, width='stretch', hide_index=True)

        unknown = mapping_all[mapping_all['Group'] == 'Unknown']
        no_tp = mapping_all[mapping_all[TP].isna()]
        with st.expander(f"Troubleshooting — {len(unknown)} unmatched IDs, {len(no_tp)} IDs without timepoint",
                         expanded=bool(len(unknown) or len(no_tp))):
            d1, d2 = st.columns(2)
            with d1:
                st.markdown("**No group tag matched**")
                if unknown.empty:
                    st.success("All IDs matched a group.")
                else:
                    st.dataframe(unknown[['Ids', 'Subject_ID']].drop_duplicates(), width='stretch', hide_index=True)
            with d2:
                st.markdown("**No timepoint found** (expects e.g. `8W` or `T2`)")
                if no_tp.empty:
                    st.success("All IDs have a timepoint.")
                else:
                    st.dataframe(no_tp[['Ids', 'Group']].drop_duplicates(), width='stretch', hide_index=True)

# --- TAB: STATISTICAL ANALYSIS ---
def analysis_tab():
    if 'mapping_df' not in st.session_state:
        st.info("Go to **Groups & Subjects** and click **Extract variables from IDs** first.")
        return
    mapping_df = active_mapping()
    all_groups = sorted(g for g in mapping_df['Group'].unique() if g != "Unknown")
    all_timepoints = sorted(mapping_df[TP].dropna().unique())

    s1, s2 = st.columns(2)
    plot_sheet = s1.selectbox("Statistic (sheet)", sheet_names, key="plot_sheet")
    df_to_plot = data_dict[plot_sheet]
    numeric_cols = metric_columns(df_to_plot)
    plot_metric = s2.selectbox("Measurement", numeric_cols, key="plot_metric_select")

    g1, g2 = st.columns(2)
    selected_groups = g1.multiselect(
        "Groups (first selected = reference group)", all_groups,
        default=all_groups[:2], key="plot_groups_multiselect",
        help="Pick 2 groups for a two-group comparison or 3+ for a multi-group analysis.")
    selected_tps = g2.multiselect("Timepoints (weeks)", all_timepoints, default=all_timepoints,
                                  key="plot_tps_multiselect",
                                  help="One timepoint = cross-sectional test; several = longitudinal model.")

    if len(selected_groups) < 2:
        st.warning("Select at least 2 groups.")
        return
    if not selected_tps:
        st.warning("Select at least 1 timepoint.")
        return

    mapping_filtered = mapping_df[mapping_df['Group'].isin(selected_groups) & mapping_df[TP].isin(selected_tps)]
    final_df = build_final_df(df_to_plot, mapping_filtered, plot_metric, selected_groups)
    if final_df.empty or final_df['Group'].nunique() < 2:
        st.error("No numeric data for this measurement in at least two of the selected groups.")
        return

    alpha_default = st.session_state.get('stat_alpha', 0.05)
    a = cached_assumptions(final_df, alpha_default)

    # --- KPI header ---
    k = st.columns(5)
    k[0].metric("Subjects", a['n_subjects'],
                help=", ".join(f"{g}: n={n}" for g, n in a['n_per_group'].items()))
    k[1].metric("Groups", a['n_groups'])
    k[2].metric("Timepoints", a['n_timepoints'])
    k[3].metric("Residual normality", "Pass" if a['normal'] else "Fail",
                help=f"{a['normality_test']} p = {se.fmt_p(a['normality_p'])}" if a['normality_test'] else None)
    k[4].metric("Design", "Balanced" if a['balanced'] else f"{len(a['incomplete'])} incomplete",
                help="Balanced = every subject measured at every selected timepoint.")

    # --- Analysis setup (Prism-style) ---
    rec_test, rec_post, rec_reason = se.recommend(a)
    tests = se.available_tests(a['n_groups'], a['n_timepoints'])
    with st.container(border=True):
        st.markdown("#### Analysis setup")
        c1, c2, c3, c4 = st.columns([3, 3, 3, 1.3])
        test_choice = c1.selectbox(
            "Statistical test", ['auto'] + tests, key="stat_test",
            format_func=lambda t: f"Auto — {se.label(rec_test)}" if t == 'auto'
            else se.label(t) + ("  ★ recommended" if t == rec_test else ""),
            help="Auto follows the decision tree for each measurement. Pick a test to apply it to every "
                 "measurement (also used by Batch export).")
        test = rec_test if test_choice == 'auto' else test_choice

        posthocs = se.available_posthocs(test)
        default_post = rec_post if rec_post in posthocs else posthocs[0]
        posthoc = c2.selectbox("Multiple comparisons", posthocs, index=posthocs.index(default_post),
                               key=f"stat_posthoc_{test}", format_func=lambda p: se.POSTHOCS[p],
                               disabled=len(posthocs) == 1)
        correction = c3.selectbox("Correction", list(se.CORRECTIONS), key="stat_correction",
                                  disabled=not se.uses_correction(posthoc),
                                  help="Family = every comparison in the results table. Tukey and "
                                       "Games-Howell already control the error rate per timepoint.")
        alpha = c4.selectbox("α", [0.05, 0.01, 0.001, 0.1], key="stat_alpha")

        gee_family, gee_cov = 'auto', 'auto'
        if test == 'gee':
            with st.expander("GEE options", expanded=False):
                e1, e2 = st.columns(2)
                gee_family = e1.selectbox("Distribution family", se.GEE_FAMILIES, key="gee_family",
                                          format_func=str.title)
                gee_cov = e2.selectbox("Working correlation", se.GEE_COVS, key="gee_cov",
                                       format_func=str.title)

        st.caption(f"★ Recommended for this measurement: **{se.label(rec_test)}** — {rec_reason}.")
        fit_notes = se.assess_fit(test, posthoc, correction, a)
        problems = [n for n in fit_notes if n[0] in ('error', 'warning')]
        if problems:
            st.markdown("**⚠️ This choice may not fit your data:**")
        else:
            st.success("✔️ No assumption problems detected for this choice.")
        for level, msg in fit_notes:
            LEVEL_UI[level](msg)

    if any(level == 'error' for level, _ in fit_notes):
        return
    result = cached_analysis(final_df, test, posthoc, correction, alpha, gee_family, gee_cov, plot_metric, a)
    comps = result['comparisons']
    if result['error']:
        st.error(result['error'])
    for level, msg in result['notes']:
        if (level, msg) not in fit_notes:
            LEVEL_UI[level](msg)

    r_plot, r_comp, r_omni, r_assume, r_methods = st.tabs(
        ["📈 Graph", "🔬 Multiple comparisons", "📋 Omnibus / model", "✅ Assumptions", "📝 Methods text"])

    with r_plot:
        render_plot_section(final_df, comps, color_map, plot_metric, selected_tps, annotation_color,
                            plot_width, plot_height)

    with r_comp:
        if comps.empty:
            st.info("No comparisons available for this selection.")
        else:
            n_sig = int(comps['Significant'].sum())
            st.markdown(f"**{se.POSTHOCS[result['posthoc']]}** · "
                        f"{'adjusted: ' + result['correction'] if se.uses_correction(result['posthoc']) else 'adjusted within each timepoint'}"
                        f" · {n_sig} of {len(comps)} significant at α = {alpha}")
            show = format_comparisons(comps)
            st.dataframe(show.style.apply(highlight_significant, axis=1),
                         width='stretch', hide_index=True)
            st.download_button("Download comparisons (CSV)", comps.to_csv(index=False).encode(),
                               file_name=f"comparisons_{plot_metric}.csv", mime="text/csv")

    with r_omni:
        omni = result['omnibus']
        if omni is None or omni.empty:
            st.info("No omnibus test for a direct two-group comparison — see **Multiple comparisons**.")
        else:
            st.markdown(f"**{se.label(result['test'])}**")
            st.dataframe(tidy(omni.assign(p=omni['p'].apply(se.fmt_p))),
                         width='stretch', hide_index=True)
            if result['details'].get('n_dropped'):
                st.caption(f"{result['details']['n_dropped']} incomplete subject(s) excluded by listwise deletion.")

    with r_assume:
        checks = pd.DataFrame([
            {"Check": f"Residual normality ({a['normality_test'] or 'n/a'})",
             "p-value": se.fmt_p(a['normality_p']), "Result": "Pass" if a['normal'] else "Fail",
             "Detail": f"skew = {a['skew']:.2f}, n = {a['n_residuals']}"
                       + (" (CLT override)" if a['clt_safe'] and a['normality_p'] < alpha else "")},
            {"Check": "Equal variances (Levene, worst timepoint)", "p-value": se.fmt_p(a['levene_p']),
             "Result": "Pass" if a['equal_var'] else "Fail", "Detail": ""},
            {"Check": "Design balance", "p-value": "", "Result": "Pass" if a['balanced'] else "Fail",
             "Detail": f"{len(a['incomplete'])} subject(s) with missing timepoints"},
            {"Check": "Sphericity (Mauchly)", "p-value": se.fmt_p(a['sphericity_p']),
             "Result": "Pass" if a['sphericity'] else "Fail",
             "Detail": "needs 3+ timepoints" if a['n_timepoints'] < 3 else ""},
        ])
        st.dataframe(checks, width='stretch', hide_index=True)
        if not a['incomplete'].empty:
            st.markdown("**Subjects with missing timepoints**")
            st.dataframe(a['incomplete'], width='stretch', hide_index=True)

    with r_methods:
        st.caption("Starting point for your manuscript's statistics section — review before use.")
        st.code(result.get('methods', ''), language=None, wrap_lines=True)

    # --- Batch export ---
    with st.expander("📦 Batch export — all measurements in this sheet", expanded=False):
        st.write(f"Renders a 300-dpi PNG per measurement in **{plot_sheet}** and a CSV with every comparison, "
                 f"using the current setup (**{'Auto' if test_choice == 'auto' else se.label(test)}**, "
                 f"{result['correction']}).")
        if st.button("Generate ZIP", type="primary", key="batch_export_btn"):
            progress = st.progress(0.0)
            status = st.empty()
            zip_buffer = io.BytesIO()
            total = len(numeric_cols)
            job_test = 'auto' if test_choice == 'auto' else test
            job_post = 'auto' if test_choice == 'auto' else posthoc
            jobs = (delayed(render_single_metric_job)(
                m, df_to_plot, mapping_filtered, selected_tps, list(selected_groups), color_map,
                plot_width, plot_height, job_test, job_post, correction, alpha, gee_family, gee_cov)
                for m in numeric_cols)
            all_stats = []
            # ponytail: 2 workers fit the Streamlit Cloud free tier (1 GB RAM); raise on bigger hosts.
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for i, (safe, png, rows) in enumerate(
                        Parallel(n_jobs=2, backend="loky", return_as="generator")(jobs)):
                    if png:
                        zf.writestr(f"{safe}.png", png)
                    if rows is not None:
                        all_stats.append(rows)
                    progress.progress((i + 1) / total)
                    status.text(f"Rendered {i + 1} / {total}")
                if all_stats:
                    zf.writestr("statistics_summary.csv", pd.concat(all_stats).to_csv(index=False))
            status.success("Export ready.")
            st.download_button("📥 Download ZIP", zip_buffer.getvalue(),
                               file_name=f"Kinematics_{plot_sheet}.zip", mime="application/zip")


with tab_stats:
    analysis_tab()

# --- TAB: RADAR ---
with tab_radar:
    if 'mapping_df' not in st.session_state:
        st.info("Go to **Groups & Subjects** and click **Extract variables from IDs** first.")
    else:
        mapping_df = active_mapping()
        radar_sheet = st.selectbox("Statistic (sheet)", sheet_names, key="radar_sheet")
        df_radar = data_dict[radar_sheet]
        radar_cols = metric_columns(df_radar)
        radar_metrics = st.multiselect("Measurements (3 or more)", radar_cols, default=radar_cols[:4],
                                       key="radar_metrics_select")
        groups_r = sorted(g for g in mapping_df['Group'].unique() if g != "Unknown")
        tps_r = sorted(mapping_df[TP].dropna().unique())
        r1, r2 = st.columns(2)
        radar_groups = r1.multiselect("Groups", groups_r, default=groups_r, key="radar_groups")
        radar_tp = r2.selectbox("Timepoint (weeks)", tps_r, key="radar_timepoint")
        normalize_radar = st.checkbox(
            "Normalize (proportional to maximum)", value=True,
            help="Divides each measurement by its highest group mean so metrics on different scales "
                 "(degrees vs meters) are comparable. The highest group reaches 1.0; ratios are preserved.")

        if len(radar_metrics) < 3:
            st.info("Select at least 3 measurements.")
        elif not radar_groups:
            st.info("Select at least one group.")
        else:
            mapping_r = mapping_df[mapping_df['Group'].isin(radar_groups) & (mapping_df[TP] == radar_tp)]
            merged = pd.merge(df_radar[['Ids'] + radar_metrics].astype({'Ids': str}),
                              mapping_r.astype({'Ids': str}), on='Ids')
            merged[radar_metrics] = merged[radar_metrics].apply(pd.to_numeric, errors='coerce')
            merged = merged.dropna(subset=radar_metrics)
            if merged.empty:
                st.warning(f"No data for the selected measurements and groups at week {radar_tp}.")
            else:
                agg = merged.groupby('Group')[radar_metrics].mean()
                if normalize_radar:
                    agg = agg / agg.max().replace(0, np.nan)
                    agg = agg.fillna(0.0)
                long = agg.reset_index().melt(id_vars='Group', var_name='Measurement', value_name='Value')
                fig_radar = px.line_polar(long, r='Value', theta='Measurement', color='Group', line_close=True,
                                          color_discrete_map=color_map, category_orders={'Group': radar_groups})
                fig_radar.update_traces(fill='toself', opacity=0.35)
                polar = dict(radialaxis=dict(visible=True, gridcolor="lightgrey"))
                if normalize_radar:
                    polar['radialaxis']['range'] = [0, 1]
                fig_radar.update_layout(
                    polar=polar, width=plot_width, height=plot_height,
                    title=f"Kinematic profile at week {radar_tp} — {radar_sheet} "
                          f"({'normalized' if normalize_radar else 'raw values'})")
                st.plotly_chart(fig_radar, width=plot_width)
