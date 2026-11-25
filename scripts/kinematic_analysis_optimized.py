import hashlib
import io
import os
import re
import tempfile
import warnings
import zipfile
from itertools import combinations

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
            # '(m/s^2)' too: the rename map only covers groundwalk names, not 'Front Right Paw Ax (m/s^2)'.
            if isinstance(col, str) and col.endswith(("(m)", "(m/s)", "(m/s²)", "(m/s^2)")):
                df[col] = pd.to_numeric(df[col], errors='coerce') * 1000
                rename[col] = (col.replace("(m)", "(mm)").replace("(m/s)", "(mm/s)").replace("(m/s²)", "(mm/s²)")
                               .replace("(m/s^2)", "(mm/s²)"))
        out[sheet] = df.rename(columns=rename)
    return out


@st.cache_data(show_spinner=False)
def add_lr_means(_data: dict, key: str, enabled: bool) -> dict:
    """Add '(L/R mean)' columns averaging every Left/Right measurement pair (cached per file + unit)."""
    if not enabled:
        return _data
    out = {}
    for sheet, df in _data.items():
        new = {}
        for col in df.columns:
            other = col.replace('Left', 'Right') if isinstance(col, str) else None
            if other and other != col and other in df.columns:
                name = col.replace('(Left)', '(L/R mean)') if '(Left)' in col else col.replace('Left', 'L/R mean')
                new[name] = (pd.to_numeric(df[col], errors='coerce') + pd.to_numeric(df[other], errors='coerce')) / 2
        out[sheet] = df.assign(**new) if new else df
    return out


def is_variability_sheet(name: str) -> bool:
    """Sheets holding SD / CV / variance values (skewed and positive: log-transform by default)."""
    return bool(re.search(r'\b(std|sd|cv|var|variance)\b', str(name), re.IGNORECASE))


def row_key(df: pd.DataFrame, cfg: dict) -> pd.Series:
    """Metadata mode: one key per subject x timepoint row ('2199_1R|3'), shared by every sheet."""
    return df[cfg['subject']].astype(str).str.strip() + '|' + df[cfg['timepoint']].astype(str).str.strip()


@st.cache_data(show_spinner=False)
def with_row_keys(_data: dict, key: str, cfg_items: tuple) -> dict:
    """Metadata mode: replace 'Ids' by the subject|timepoint key in every sheet that has the metadata
    columns, so the rest of the page can keep joining on 'Ids'. ID mode: unchanged."""
    cfg = dict(cfg_items)
    if not cfg:
        return _data
    need = [cfg['subject'], cfg['timepoint']]
    return {s: (df.assign(Ids=row_key(df, cfg)) if all(c in df.columns for c in need) else df)
            for s, df in _data.items()}


def extract_sex(id_str: str):
    """'M' / 'F' from a '_M_' / '_Female' style token in a trial ID, else None."""
    for tok in re.split(r'[_\-\s]+', str(id_str).upper()):
        if tok in ('M', 'MALE'):
            return 'M'
        if tok in ('F', 'FEMALE'):
            return 'F'
    return None


def session_label(mapping: pd.DataFrame) -> pd.Series:
    return mapping['Subject_ID'].astype(str) + ' @ ' + mapping[TP].map(lambda v: f"{v:g}" if pd.notna(v) else "?")


def lr_disagreement(df_sheet, metric):
    """For an '(L/R mean)' measurement: (correlation, relative mean difference) of its two sides."""
    left = metric.replace('(L/R mean)', '(Left)') if '(L/R mean)' in metric else metric.replace('L/R mean', 'Left')
    right = left.replace('(Left)', '(Right)') if '(Left)' in left else left.replace('Left', 'Right')
    if left not in df_sheet or right not in df_sheet:
        return None
    lv, rv = pd.to_numeric(df_sheet[left], errors='coerce'), pd.to_numeric(df_sheet[right], errors='coerce')
    scale = (abs(lv.mean()) + abs(rv.mean())) / 2
    return lv.corr(rv), (abs(lv.mean() - rv.mean()) / scale if scale else np.nan)


def build_final_df(df_sheet, mapping, metric, group_order, cov=None):
    """Join measurements to the ID mapping and average trials per subject x timepoint.
    cov: optional DataFrame ['Ids', se.COV] merged in as a covariate (also averaged)."""
    # Plain pandas: pl.from_pandas segfaulted under Streamlit with polars 2.0 + pandas 3.
    out = pd.merge(df_sheet[['Ids', metric]].astype({'Ids': str}), mapping.astype({'Ids': str}), on='Ids')
    out[metric] = pd.to_numeric(out[metric], errors='coerce')
    values = [metric]
    if cov is not None:
        out = out.merge(cov.astype({'Ids': str}).drop_duplicates('Ids'), on='Ids', how='left')
        values.append(se.COV)
    keys = ['Subject_ID', 'Group', TP] + [c for c in (se.COHORT, se.SETUP, se.SEX) if c in mapping.columns]
    out = out.dropna(subset=[metric]).groupby(keys, as_index=False)[values].mean()
    out['_metric_'] = out[metric].astype(float)
    out['Group'] = pd.Categorical(out['Group'], categories=group_order)
    return out.sort_values([TP, 'Group'])


@st.cache_data(show_spinner="Checking assumptions...")
def cached_assumptions(final_df, alpha):
    return se.check_assumptions(final_df, alpha)


@st.cache_data(show_spinner="Running statistics...")
def cached_analysis(final_df, test, posthoc, correction, alpha, gee_family, gee_cov, metric, _assumptions, log_y,
                    adjust_sex):
    return se.run_analysis(final_df, test, posthoc, correction, alpha, gee_family, gee_cov, metric, _assumptions,
                           log_y, adjust_sex)


def apply_cohorts(mapping, table):
    """Add 'Cohort' and 'Setup' columns from the optional cohort table. An animal ID matches a
    Subject_ID equal to it or starting with it plus '_' (so '2273' covers '2273_1L', '2273_2R')."""
    if table is None or table.dropna(how='all').empty:
        return mapping
    out = mapping.copy()
    out[se.COHORT], out[se.SETUP] = 'Unassigned', 'Original'
    subj = out['Subject_ID'].astype(str)
    for _, row in table.dropna(how='all').iterrows():
        ids = [s.strip() for s in re.split(r'[,;\s]+', str(row.get('Animal IDs') or '')) if s.strip()]
        if not ids or pd.isna(row.get('Cohort')) or not str(row['Cohort']).strip():
            continue
        hit = subj.apply(lambda s: any(s == i or s.startswith(i + '_') for i in ids))
        out.loc[hit, se.COHORT] = str(row['Cohort']).strip()
        week = pd.to_numeric(row.get('New setup from week'), errors='coerce')
        if pd.notna(week):
            out.loc[hit & (out[TP] >= week), se.SETUP] = 'New'
    return out


def active_mapping():
    mapping = apply_cohorts(st.session_state.mapping_df, st.session_state.get('cohort_table'))
    excluded = st.session_state.get('exclude_subjects_ui')
    if excluded:
        mapping = mapping[~mapping['Subject_ID'].isin(excluded)]
    sessions = st.session_state.get('exclude_sessions_ui')
    if sessions:
        mapping = mapping[~session_label(mapping).isin(sessions)]
    return mapping


def screen_width(px):
    """On-screen plot width: fill the page unless the user turned 'Fill available width' off."""
    return 'stretch' if st.session_state.get('fill_width', True) else px


def metric_columns(df):
    """Numeric measurement columns (metadata columns such as group, sex or timepoint excluded).
    'QC ...' columns rate the tracking quality, not the animal, so they are hidden too."""
    meta = set(st.session_state.get('meta_cols', ())) | {'Ids'}
    # "Mostly numeric" rather than dtype, so a stray text cell does not hide a measurement.
    return [c for c in df.columns if c not in meta and not str(c).startswith('QC ')
            and (pd.api.types.is_numeric_dtype(df[c]) or pd.to_numeric(df[c], errors='coerce').notna().mean() > 0.5)]


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------
@st.fragment
def render_plot_section(final_df, comparisons, color_map, plot_metric, timepoints, annotation_color,
                        plot_width, plot_height, trend=None):
    """Isolated rerun fragment: changing plot options never re-runs the statistics.
    trend: optional fitted progression curve (Group, TP, Fit) drawn as dashed lines."""
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

    show_trend = trend is not None and st.checkbox(
        "Show fitted progression trend", value=True, key="show_trend",
        help="Dashed lines: the progression model's average curve per group (what the Level and Rate tests compare).")

    with st.expander("Axis settings", expanded=False):
        x1, x2, x3 = st.columns(3)
        force_exact_ticks = x1.checkbox("Label every timepoint", value=True)
        custom_x_range = x2.checkbox("Custom X-axis range", value=False)
        positive = bool((final_df[plot_metric] > 0).all())
        log_axis = x3.checkbox("Log-scale Y axis", value=False, disabled=not positive, key="log_axis",
                               help="Original units, logarithmic spacing: equal % differences look equally "
                                    "large. Needs strictly positive values.") and positive
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
    if log_axis:
        fig.update_yaxes(type='log')

    if show_trend:
        for g, cur in trend.assign(Group=trend['Group'].astype(str)).groupby('Group', sort=False):
            cur = cur.sort_values(TP)
            fig.add_scatter(x=cur[TP], y=cur['Fit'], mode='lines', name=f"{g} (model)",
                            line=dict(dash='dash', width=2, color=color_map.get(g)))

    if show_stars and two_groups and not comparisons.empty and TP in comparisons.columns:
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
        lo_hi = [y_min - offset * 0.5, top + offset * 1.5]
        if log_axis:   # plotly expects log10 bounds on a log axis
            lo_hi = [np.log10(max(y_min * 0.9, 1e-12)), np.log10(top + offset * 1.5)]
        fig.update_layout(yaxis=dict(range=lo_hi))

    fig.update_layout(margin=dict(t=50), width=plot_width, height=plot_height,
                      font=dict(family="Segoe UI Semibold", size=16))
    st.plotly_chart(fig, width=screen_width(plot_width))  # "stretch" overrides the layout width


def render_single_metric_job(metric, df_sheet, mapping, timepoints, group_order, color_map,
                             plot_width, plot_height, test, posthoc, correction, alpha, gee_family, gee_cov,
                             log_y=False, adjust_sex=False, cov=None):
    """Headless Matplotlib PNG renderer + statistics for one measurement (runs in a worker process)."""
    loop = build_final_df(df_sheet, mapping, metric, group_order, cov)
    if loop.empty or loop['Group'].nunique() < 2:
        return None, None, None
    # Log needs positive values; a metric that crosses zero is analysed on the raw scale.
    log_y = log_y and bool((loop['_metric_'] > 0).all())

    trend = None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = se.run_analysis(loop, test, posthoc, correction, alpha, gee_family, gee_cov, metric, log_y=log_y,
                                  adjust_sex=adjust_sex)
        comps = res['comparisons'] if res['error'] is None else pd.DataFrame()
        stats_rows = comps.assign(Measurement=metric, Test=se.label(res['test'])) if not comps.empty else None
        trend = res['details'].get('trend')
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
        if trend is not None:
            cur = trend[trend['Group'].astype(str) == str(group)].sort_values(TP)
            if not cur.empty:
                ax.plot(cur[TP], cur['Fit'], linestyle='--', linewidth=1.8, color=color_map.get(group),
                        label=f"{group} (model)")
    ax.set_title(f"Longitudinal progression of {metric}", fontsize=13)
    ax.set_xlabel("Timepoint (Weeks)")
    ax.set_ylabel(metric)
    ax.set_xticks(sorted(timepoints))
    ax.grid(True, color="lightgrey", linewidth=0.8)
    ax.spines[['top', 'right']].set_visible(False)
    ax.legend(frameon=False)

    if len(group_order) == 2 and not comps.empty and TP in comps.columns:
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
    # 4 significant digits: fixed rounding showed small effects (metres, per-week rates) as 0.0000.
    show[num] = show[num].apply(lambda col: col.map(lambda v: float(f"{v:.4g}") if pd.notna(v) else v))
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
# Key on content, not name: re-uploading a corrected file with the same name must reset everything.
file_key = f"{uploaded_file.name}:{hashlib.md5(file_bytes).hexdigest()}"
if st.session_state.get('uploaded_filename') != file_key:
    st.session_state.data_dict = load_data(file_bytes, uploaded_file.name)
    st.session_state.uploaded_filename = file_key
    for key in ('mapping_df', 'group_definitions_final', 'exclude_subjects_ui', 'exclude_sessions_ui',
                'meta_cfg', 'meta_cols'):
        st.session_state.pop(key, None)

raw_data_dict = st.session_state.data_dict
sheet_names = list(raw_data_dict.keys())
if not sheet_names:
    st.error("No readable sheets/tables were found in this file.")
    st.stop()

# --- Sidebar (grouped so it stays short) ---
with st.sidebar:
    st.header("Display settings")
    with st.expander("📏 Units & measurements", expanded=False):
        distance_unit = st.radio("Distance units", ["Meters (m)", "Millimeters (mm)"],
                                 help="Converts distance, velocity and acceleration. "
                                      "Statistical significance is unaffected.")
        lr_means = st.checkbox("Add left/right averages", value=False, key="lr_means",
                               help="Adds an '(L/R mean)' measurement for every Left/Right pair. Fewer "
                                    "measurements means less multiple-testing penalty.")
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
        st.checkbox("Fill available width", value=True, key="fill_width",
                    help="On-screen plots stretch to the page. Turn off to use the width below on screen too.")
        plot_width = st.slider("Plot width (px)", 600, 2400, 1000, 50,
                               help="Width of exported PNGs, and of on-screen plots when "
                                    "'Fill available width' is off.")
        plot_height = st.slider("Plot height (px)", 400, 1600, 600, 50)

data_base = add_lr_means(convert_units(raw_data_dict, file_key, distance_unit),
                         f"{file_key}:{distance_unit}", lr_means)
# Metadata mode: every sheet gets a subject|timepoint row key in 'Ids' (set when variables are extracted).
meta_cfg = st.session_state.get('meta_cfg') or {}
data_dict = with_row_keys(data_base, f"{file_key}:{distance_unit}:{lr_means}",
                          tuple((k, meta_cfg[k]) for k in ('subject', 'timepoint') if k in meta_cfg))

tab_data, tab_groups, tab_stats, tab_radar = st.tabs([
    "📂 Data", "🧪 Groups & Subjects", "🧮 Statistical Analysis", "🕸️ Radar Profile"])

# --- TAB: DATA ---
with tab_data:
    first_df = data_base[sheet_names[0]]
    n_ids = first_df['Ids'].nunique() if 'Ids' in first_df.columns else 0
    k1, k2, k3 = st.columns(3)
    k1.metric("Sheets", len(sheet_names))
    k2.metric("Measurements", len(metric_columns(first_df)))
    k3.metric("Unique trial IDs", n_ids)

    selected_sheet = st.selectbox("Sheet", sheet_names, key="viewer_sheet_select")
    st.dataframe(data_base[selected_sheet], width='stretch', height=420)
    with st.expander("Trial IDs found", expanded=False):
        if 'Ids' in first_df.columns:
            st.dataframe(pd.DataFrame({"Ids": first_df['Ids'].unique()}), width='stretch', hide_index=True)
        else:
            st.error("No 'Ids' column found. Please check your file format.")

# --- TAB: GROUPS & SUBJECTS ---
with tab_groups:
    st.subheader("Define groups and timepoints")
    first_raw = data_base[sheet_names[0]]
    text_cols = [c for c in first_raw.columns
                 if c != 'Ids' and not pd.api.types.is_numeric_dtype(first_raw[c])]
    modes = ["Trial IDs (tags inside each ID)", "Metadata columns"]
    mode = st.radio("Extract variables from", modes, index=1 if text_cols else 0, horizontal=True,
                    key="extract_mode",
                    help="Trial IDs: group, timepoint and sex are read from IDs like 2199_1R_44W_FOOTPRINT_WT_F. "
                         "Metadata columns: the file has columns such as animal, group, sex and timepoint.")

    if mode == modes[0]:
        st.markdown("**Group Name** is shown on plots. **Tag in ID** is matched as a whole part of the ID "
                    "between `_` separators (e.g. `TG` matches `..._TG_F` but not `ATG1`; `TG_F` matches "
                    "`..._TG_F`). Sex is read from an `M`/`F` part of the ID when present.")
        if 'group_definitions' not in st.session_state:
            st.session_state.group_definitions = pd.DataFrame({
                "Group Name": ["Wildtype", "Transgenic", "WT Male", "WT Female", "TG Male", "TG Female"],
                "Tag in ID": ["WT", "TG", "WT_M", "WT_F", "TG_M", "TG_F"],
            })
        edited_groups = st.data_editor(st.session_state.group_definitions, num_rows="dynamic", width='stretch',
                                       hide_index=True, key="groups_editor")

        clicked = st.button("Extract variables", type="primary", key="extract_vars_btn")
        if clicked and 'Ids' not in first_raw.columns:
            st.error("Could not find an 'Ids' column to extract from. Try **Metadata columns**.")
        elif clicked:
            valid_groups = edited_groups.dropna(how='all').copy()
            valid_groups["Tag in ID"] = valid_groups["Tag in ID"].astype(str).str.strip()
            valid_groups["Group Name"] = valid_groups["Group Name"].astype(str).str.strip()
            valid_groups = valid_groups[valid_groups["Tag in ID"] != ""]

            def norm(s):
                return "_" + re.sub(r'[\-\s]+', '_', str(s).upper()) + "_"

            def extract_timepoint(id_str):
                m = re.search(r'(\d+)[Ww]', id_str) or re.search(r'[Tt](\d+)', id_str)
                return int(m.group(1)) if m else None

            def extract_subject_id(id_str):
                tokens = id_str.split('_')
                for i, token in enumerate(tokens):
                    if re.fullmatch(r'(?:[Ww]eek\s*)?\d+\s*[Ww]|[Ww]\s*\d+|[Tt]\s*\d+|\d+\s*[Tt]', token):
                        return "_".join(tokens[:i])
                return tokens[0]

            tags = [(r["Group Name"], norm(r["Tag in ID"])) for _, r in valid_groups.iterrows()]
            records = []
            for id_str in first_raw['Ids'].unique():
                s = str(id_str)
                matched = [name for name, tag in tags if tag in norm(s)]
                for grp in matched or ["Unknown"]:
                    records.append({"Ids": id_str, TP: extract_timepoint(s), "Subject_ID": extract_subject_id(s),
                                    "Group": grp, se.SEX: extract_sex(s)})
            mapping = pd.DataFrame(records)
            if mapping[se.SEX].notna().any():
                mapping[se.SEX] = mapping[se.SEX].fillna('Unknown')
            else:
                mapping = mapping.drop(columns=se.SEX)
            st.session_state.mapping_df = mapping
            st.session_state.group_definitions_final = valid_groups
            st.session_state.meta_cfg, st.session_state.meta_cols = {}, []
            st.rerun()
    else:
        cols = list(first_raw.columns)

        def guess(words, default=None):
            return next((c for c in cols if any(w in str(c).lower() for w in words)), default)

        st.markdown("Pick which columns describe each row. With several group columns, every combination "
                    "becomes a group (e.g. *Experimental Group* + *Gender* → `WT`, `TG`, `F`, `M`, `WT F`, …). "
                    "Rows of the same animal and timepoint "
                    "(several trials) are averaged.")
        m1, m2, m3 = st.columns(3)
        subj_col = m1.selectbox("Animal / subject column", cols,
                                index=cols.index(guess(['animal', 'subject', 'ids', 'id'], cols[0])), key="meta_subject")
        tp_guess = guess(['timepoint', 'week', 'time', 'age'])
        tp_col = m2.selectbox("Timepoint column", cols, index=cols.index(tp_guess) if tp_guess else 0,
                              key="meta_tp")
        weeks_per = m3.number_input("Weeks per timepoint unit", min_value=0.001, value=1.0, step=1.0,
                                    key="meta_weeks_per",
                                    help="Converts the timepoint column to weeks. 1 if it already holds weeks; "
                                         "4 if timepoint 1 = week 4, 2 = week 8, …")
        m4, m5 = st.columns(2)
        grp_guess = guess(['group', 'genotype', 'condition'])
        group_cols = m4.multiselect("Group column(s)", cols, default=[grp_guess] if grp_guess else [],
                                    key="meta_groups")
        sex_guess = guess(['sex', 'gender'])
        sex_opts = ["None"] + cols
        sex_col = m5.selectbox("Sex column (optional)", sex_opts,
                               index=sex_opts.index(sex_guess) if sex_guess else 0, key="meta_sex",
                               help="Enables 'Adjust for sex' in the progression model.")

        clicked = st.button("Extract variables", type="primary", key="extract_vars_btn")
        if clicked and not group_cols:
            st.error("Pick at least one group column.")
        elif clicked:
            cfg = {'subject': subj_col, 'timepoint': tp_col}
            base = pd.DataFrame({
                'Ids': row_key(first_raw, cfg),
                TP: pd.to_numeric(first_raw[tp_col], errors='coerce') * weeks_per,
                'Subject_ID': first_raw[subj_col].astype(str).str.strip(),
            })
            if sex_col != "None":
                sx = first_raw[sex_col].astype(str).str.strip().str.upper()
                base[se.SEX] = sx.replace({'MALE': 'M', 'FEMALE': 'F', 'NAN': 'Unknown', '': 'Unknown'})
            # Every combination of the group columns is a group (Group, Gender, Group + Gender),
            # so a row belongs to several groups at once, like overlapping tags in ID mode.
            vals = first_raw[group_cols].fillna('').astype(str).apply(lambda c: c.str.strip())
            parts = []
            for k in range(len(group_cols), 0, -1):
                for combo in combinations(group_cols, k):
                    combo = list(combo)
                    part = base.assign(Group=vals[combo].agg(" ".join, axis=1))
                    missing = first_raw[combo].isna().any(axis=1)
                    if k == len(group_cols):
                        part.loc[missing, 'Group'] = "Unknown"
                        cfg['full_groups'] = sorted(part['Group'].unique())
                    else:
                        part = part[~missing]
                    parts.append(part)
            mapping = pd.concat(parts, ignore_index=True)
            st.session_state.mapping_df = mapping.drop_duplicates(['Ids', 'Group']).reset_index(drop=True)
            st.session_state.meta_cfg = cfg
            st.session_state.meta_cols = [subj_col, tp_col, *group_cols] + ([sex_col] if sex_col != "None" else [])
            st.rerun()

    if 'mapping_df' in st.session_state:
        mapping_all = st.session_state.mapping_df
        st.success("Variables extracted. Group colors are now available in the sidebar.")
        if st.session_state.get('meta_cfg'):
            # Each row has one full-combination group, so an animal in two of those is a labelling error.
            full = mapping_all[mapping_all['Group'].isin(st.session_state.meta_cfg.get('full_groups', []))]
            n_grp = full.groupby('Subject_ID')['Group'].transform('nunique')
            odd = full[n_grp > 1]
            if not odd.empty:
                main = odd.groupby('Subject_ID')['Group'].agg(lambda g: g.value_counts().index[0])
                wrong = odd[odd['Group'] != odd['Subject_ID'].map(main)]
                st.error("Animals labelled with different groups in different rows — probably a typo in the file. "
                         "Rows that disagree with the animal's usual group:")
                st.dataframe(tidy(wrong[['Subject_ID', TP, 'Group']].assign(
                    **{'Usual group': wrong['Subject_ID'].map(main)})), width='stretch', hide_index=True)
                st.caption("Fix the file, or remove these sessions below under *Single sessions removed*.")

        st.markdown("#### Exclude subjects or sessions")
        e1, e2 = st.columns(2)
        e1.multiselect("Whole animals removed from every plot and statistic (e.g. dropouts):",
                       options=sorted(mapping_all['Subject_ID'].dropna().unique()), key="exclude_subjects_ui")
        e2.multiselect("Single sessions removed (animal @ week), e.g. a failed recording:",
                       options=sorted(session_label(mapping_all).unique()), key="exclude_sessions_ui",
                       help="The Statistical Analysis tab lists likely outlier sessions for each measurement.")

        with st.expander("Cohorts & recording setup (optional)", expanded=False):
            st.markdown("Fill this in when animals started the experiment at different times or the camera setup "
                        "changed. Only the **Progression model** uses it: recording sessions (cohort × week) and "
                        "the setup change are then accounted for, so day-to-day recording differences are not "
                        "mistaken for group effects. Leave empty to ignore.")
            if 'cohort_definitions' not in st.session_state:
                st.session_state.cohort_definitions = pd.DataFrame(
                    {"Cohort": pd.Series(dtype=str), "Animal IDs": pd.Series(dtype=str),
                     "New setup from week": pd.Series(dtype=float)})
            st.session_state.cohort_table = st.data_editor(
                st.session_state.cohort_definitions, num_rows="dynamic", width='stretch', hide_index=True,
                key="cohort_editor",
                column_config={
                    "Animal IDs": st.column_config.TextColumn(
                        help="Comma-separated. '2273' matches 2273, 2273_1L, 2273_2R..."),
                    "New setup from week": st.column_config.NumberColumn(
                        help="First week recorded with the new camera setup (leave empty if unchanged)."),
                })
            assigned = apply_cohorts(mapping_all, st.session_state.cohort_table)
            if se.COHORT in assigned.columns:
                per = assigned.drop_duplicates('Subject_ID').groupby(se.COHORT)['Subject_ID'].nunique()
                st.caption(" · ".join(f"{c}: {n} subjects" for c, n in per.items()))
                missing = sorted(assigned.loc[assigned[se.COHORT] == 'Unassigned', 'Subject_ID'].unique())
                if missing:
                    st.warning(f"{len(missing)} subject(s) match no cohort and form an 'Unassigned' cohort: "
                               + ", ".join(map(str, missing[:15])) + ("..." if len(missing) > 15 else ""))

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
        st.info("Go to **Groups & Subjects** and click **Extract variables** first.")
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

    if is_variability_sheet(plot_sheet) and (final_df['_metric_'] < 0).any():
        st.warning(f"**{plot_metric}** has negative values in **{plot_sheet}**: the underlying measurement crosses "
                   "zero (e.g. signed velocity/acceleration components, toe clearance), so a coefficient of "
                   "variation is not meaningful. Use the SD sheet for this measurement instead.")
    if 'L/R mean' in plot_metric:
        agree = lr_disagreement(df_to_plot, plot_metric)
        if agree and (agree[0] < 0.5 or agree[1] > 0.2):
            st.warning(f"Left and right disagree for this measurement (correlation r = {agree[0]:.2f}, means differ "
                       f"by {agree[1]:.0%}). They probably do not measure the same thing (different camera, "
                       "calibration or floor reference), so their average is hard to interpret. Analyse each side "
                       "separately.")
        else:
            st.caption("Left and right were averaged per trial. If the two sides are filmed by different cameras "
                       "or were affected differently by a setup change, also check each side separately.")

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

    # --- Outlier sessions: far from what is expected for that animal at that age ---
    # Expected = group x week median (follows growth / disease course) + the animal's own typical offset.
    r1 = final_df['_metric_'] - final_df.groupby(['Group', TP], observed=True)['_metric_'].transform('median')
    dev = r1 - r1.groupby(final_df['Subject_ID']).transform('median')
    mad = 1.4826 * dev.abs().median()
    if mad > 0:
        flagged = final_df.assign(**{'Robust z': dev / mad})
        flagged = flagged[flagged['Robust z'].abs() > 5]
        if not flagged.empty:
            labels = session_label(flagged).tolist()
            with st.expander(f"⚠️ {len(flagged)} possible outlier session(s) for this measurement", expanded=False):
                st.caption("Sessions more than 5 robust SDs away from what is expected for that animal at that "
                           "week (its group's median at that week plus the animal's usual offset) — often a "
                           "tracking or calibration failure. Check the video before excluding.")
                st.dataframe(tidy(flagged[['Subject_ID', 'Group', TP, plot_metric, 'Robust z']]),
                             width='stretch', hide_index=True)

                def _exclude(new=labels):
                    st.session_state.exclude_sessions_ui = sorted(
                        set(st.session_state.get('exclude_sessions_ui') or []) | set(new))
                st.button("Exclude these sessions (all measurements)", key="exclude_outliers_btn", on_click=_exclude,
                          help="Adds them to Groups & Subjects → Single sessions removed, where you can undo it.")

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

        log_y, adjust_sex, cov_df, model_df = False, False, None, final_df
        if test == 'progression':
            positive = bool((final_df['_metric_'] > 0).all())
            q1, q2 = st.columns([1, 2])
            has_sex = se.SEX in final_df.columns and final_df[se.SEX].nunique() > 1
            adjust_sex = q1.checkbox(
                "Adjust for sex", value=False, disabled=not has_sex, key="adjust_sex",
                help="Adds sex as a covariate, so you can compare e.g. WT vs TG with both sexes pooled instead of "
                     "splitting into 4 groups. Needs sex information and both sexes in the selection.") and has_sex
            cov_map = {f"{s} → {c}": (s, c) for s in sheet_names for c in metric_columns(data_dict[s])}
            cov_choice = q2.selectbox(
                "Covariate (optional)", ["None"] + list(cov_map), key="prog_cov",
                help="E.g. walking speed or run duration: removes its influence from the group comparison. "
                     "Avoid covariates the genotype itself changes (that would remove part of the real effect).")
            if cov_choice in cov_map:
                cs, cc = cov_map[cov_choice]
                cov_df = pd.DataFrame({'Ids': data_dict[cs]['Ids'],
                                       se.COV: pd.to_numeric(data_dict[cs][cc], errors='coerce')})
                model_df = build_final_df(df_to_plot, mapping_filtered, plot_metric, selected_groups, cov_df)
            p1, p2 = st.columns([1, 2])
            log_y = p1.checkbox(
                "Log-transform", value=positive and is_variability_sheet(plot_sheet), disabled=not positive,
                key=f"log_y_{plot_sheet}",
                help="Recommended for SD / CV sheets (skewed, positive). Differences are then reported as % "
                     "differences. Not available when values are zero or negative.") and positive
            if se.COHORT in final_df.columns:
                n_coh = final_df[se.COHORT].nunique()
                setup = final_df[se.SETUP].nunique() > 1
                p2.caption(f"Using {n_coh} cohort(s)" + (" with recording sessions" if n_coh >= 2 else "")
                           + (" and the camera setup change" if setup else "") + ".")
            else:
                p2.caption("No cohort information — add it under **Groups & Subjects → Cohorts & recording setup** "
                           "if animals started at different times or the setup changed.")

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
    result = cached_analysis(model_df, test, posthoc, correction, alpha, gee_family, gee_cov, plot_metric, a, log_y,
                             adjust_sex)
    comps = result['comparisons']
    if result['error']:
        st.error(result['error'])
    for level, msg in result['notes']:
        if (level, msg) not in fit_notes:
            LEVEL_UI[level](msg)

    r_plot, r_comp, r_omni, r_assume, r_methods = st.tabs(
        ["📈 Graph", "🔬 Multiple comparisons", "📋 Model effects", "✅ Assumptions", "📝 Methods text"])

    with r_plot:
        if result['details'].get('log'):
            st.caption("The graph shows raw values (mean ± SEM). Log-transform only affects the statistics: "
                       "the model was fitted on log values and differences are reported as % differences.")
        render_plot_section(final_df, comps, color_map, plot_metric, selected_tps, annotation_color,
                            plot_width, plot_height, result['details'].get('trend'))

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
            if se.CI_LO in comps and comps[se.CI_LO].notna().any():
                st.caption("95% CI: range of plausible values for the difference (not adjusted for multiple "
                           "comparisons). Empty for rank-based tests and Tukey / Games-Howell.")
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
        batch_metrics = st.multiselect(
            "Measurements (pick your primary outcomes)", numeric_cols, default=numeric_cols,
            key=f"batch_metrics_{plot_sheet}_{lr_means}",  # options change with sheet / L-R toggle
            help="The CSV adds 'p_corr_all_measurements': p-values adjusted with the chosen correction across "
                 "every comparison of every selected measurement. Fewer, pre-chosen outcomes = more power.")
        if st.button("Generate ZIP", type="primary", key="batch_export_btn", disabled=not batch_metrics):
            progress = st.progress(0.0)
            status = st.empty()
            zip_buffer = io.BytesIO()
            total = len(batch_metrics)
            job_test = 'auto' if test_choice == 'auto' else test
            job_post = 'auto' if test_choice == 'auto' else posthoc
            # Log setting follows the sheet type (per-metric checkbox only covers the metric on screen).
            job_log = test == 'progression' and is_variability_sheet(plot_sheet)
            jobs = (delayed(render_single_metric_job)(
                m, df_to_plot, mapping_filtered, selected_tps, list(selected_groups), color_map,
                plot_width, plot_height, job_test, job_post, correction, alpha, gee_family, gee_cov, job_log,
                adjust_sex, cov_df)
                for m in batch_metrics)
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
                    summary = pd.concat(all_stats, ignore_index=True)
                    summary['p_corr_all_measurements'] = se._adjust(summary['p_unc'], se.CORRECTIONS.get(correction))
                    zf.writestr("statistics_summary.csv", summary.to_csv(index=False))
            status.success("Export ready.")
            st.download_button("📥 Download ZIP", zip_buffer.getvalue(),
                               file_name=f"Kinematics_{plot_sheet}.zip", mime="application/zip")


with tab_stats:
    analysis_tab()

# --- TAB: RADAR ---
with tab_radar:
    if 'mapping_df' not in st.session_state:
        st.info("Go to **Groups & Subjects** and click **Extract variables** first.")
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
                # Average trials per animal first (as in the statistics), so animals with more trials
                # do not weigh more in their group mean.
                agg = merged.groupby(['Group', 'Subject_ID'])[radar_metrics].mean().groupby('Group').mean()
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
                st.plotly_chart(fig_radar, width=screen_width(plot_width))
