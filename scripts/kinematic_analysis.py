import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import re
import pingouin as pg
import traceback
import statsmodels.formula.api as smf
import statsmodels.api as sm
import io
import zipfile
import scipy.stats as stats
import polars as pl
from joblib import Parallel, delayed
import json
from statsmodels.stats.multitest import multipletests

# Suppress warnings
import warnings
from statsmodels.tools.sm_exceptions import ConvergenceWarning

warnings.simplefilter('ignore', ConvergenceWarning)

# --- PLOTLY STATS FUNCTION (For Box Plots in Tab 5) ---
def add_plotly_significance_brackets(fig, df, posthocs_df, x_col, y_col, text_color="black"):
    """
    Custom function to draw statistical brackets and asterisks on Plotly grouped plots.
    Assumes exactly 2 groups are being compared.
    """
    if posthocs_df is None or posthocs_df.empty: 
        return fig

    p_col = next((c for c in posthocs_df.columns if 'p-' in c.lower() or 'p_' in c.lower() or c.lower() == 'pval' or c.lower() == 'p'), None)
    if not p_col: 
        return fig

    y_max_overall = df[y_col].max()
    y_min_overall = df[y_col].min()
    y_range = y_max_overall - y_min_overall
    if y_range == 0: y_range = y_max_overall
    
    step_y = y_range * 0.05  
    
    for _, row in posthocs_df.iterrows():
        if x_col not in row: continue
        
        x_val = row[x_col]
        tp_data = df[df[x_col] == x_val]
        if tp_data.empty: continue
        
        y_max_tp = tp_data[y_col].max()
        bracket_y = y_max_tp + step_y
        
        raw_pval = str(row[p_col])
        text = raw_pval
        num_str = raw_pval.replace('<', '').replace('>', '').replace('=', '').strip()
        
        try:
            val = float(num_str)
            if val < 0.001: text = "***"
            elif val < 0.01: text = "**"
            elif val < 0.05: text = "*"
            else: text = "ns"
        except ValueError:
            pass 
        
        try:
            x_center = float(x_val)
            x0 = x_center - 0.15 
            x1 = x_center + 0.15 
            
            # Apply user-selected color to brackets and text
            fig.add_shape(type="line", x0=x0, x1=x0, y0=bracket_y, y1=bracket_y + step_y * 0.5, line=dict(color=text_color, width=1.5))
            fig.add_shape(type="line", x0=x1, x1=x1, y0=bracket_y, y1=bracket_y + step_y * 0.5, line=dict(color=text_color, width=1.5))
            fig.add_shape(type="line", x0=x0, x1=x1, y0=bracket_y + step_y * 0.5, y1=bracket_y + step_y * 0.5, line=dict(color=text_color, width=1.5))
            
            fig.add_annotation(
                x=x_center, y=bracket_y + step_y * 1.5, text=text, showarrow=False, font=dict(size=14, color=text_color, family="Arial")
            )
        except ValueError:
            continue 
            
    return fig
# ---------------------------------

# --- CONFIGURATION ---
st.set_page_config(layout="wide") 
st.title("🐁 Kinematics Longitudinal Analyzer")

column_rename_map = {
    "Step Width (Hind)": "Step Width (Hind) (m)",
    "Step Width (Front)": "Step Width (Front) (m)",
    "Step Length (Left)": "Step Length (Left) (m)",
    "Step Length (Right)": "Step Length (Right) (m)",
    "Toe Clearance Forepaw (Right)": "Toe Clearance Forepaw (Right) (m)",
    "Toe Clearance Hindpaw (Right)": "Toe Clearance Hindpaw (Right) (m)",
    "Toe Clearance Forepaw (Left)": "Toe Clearance Forepaw (Left) (m)",
    "Toe Clearance Hindpaw (Left)": "Toe Clearance Hindpaw (Left) (m)",
    "Iliac Crest Height (Right)": "Iliac Crest Height (Right) (m)",
    "Iliac Crest Height (Left)": "Iliac Crest Height (Left) (m)",
    "Hip Height (Right)": "Hip Height (Right) (m)",
    "Hip Height (Left)": "Hip Height (Left) (m)",
    "Tail Base Height (Right)": "Tail Base Height (Right) (m)",
    "Tail Base Height (Left)": "Tail Base Height (Left) (m)",
    "Nose Height": "Nose Height (m)",
    "Tail Tip Height": "Tail Tip Height (m)",
    "Shoulder Height (Right)": "Shoulder Height (Right) (m)",
    "Shoulder Height (Left)": "Shoulder Height (Left) (m)",
    "Protraction/Retraction (Right)": "Protraction/Retraction (Right) (º)",
    "Protraction/Retraction (Left)": "Protraction/Retraction (Left) (º)",
    "Hip Angle (Right)": "Hip Angle (Right) (º)",
    "Knee Angle (Right)": "Knee Angle (Right) (º)",
    "Hip Angle (Left)": "Hip Angle (Left) (º)",
    "Knee Angle (Left)": "Knee Angle (Left) (º)",
    "Tail Angle (Side View)": "Tail Angle (Side View) (º)",
    "Front Right Ax (m/s^2)": "Front Right Ax (m/s²)",
    "Front Right Ay (m/s^2)": "Front Right Ay (m/s²)",
    "Front Right |Acc| (m/s^2)": "Front Right |Acc| (m/s²)",
    "Front Left Ax (m/s^2)": "Front Left Ax (m/s²)",
    "Front Left Ay (m/s^2)": "Front Left Ay (m/s²)",
    "Front Left |Acc| (m/s^2)": "Front Left |Acc| (m/s²)",
    "Hind Right Ax (m/s^2)": "Hind Right Ax (m/s²)",
    "Hind Right Ay (m/s^2)": "Hind Right Ay (m/s²)",
    "Hind Right |Acc| (m/s^2)": "Hind Right |Acc| (m/s²)",
    "Hind Left Ax (m/s^2)": "Hind Left Ax (m/s²)",
    "Hind Left Ay (m/s^2)": "Hind Left Ay (m/s²)",
    "Hind Left |Acc| (m/s^2)": "Hind Left |Acc| (m/s²)"
}

def format_pval(x):
    if pd.isna(x): return "NaN"
    try:
        val = float(x)
        return f"{val:.4f}" if val > 0.0001 else "<0.0001"
    except:
        return str(x)


# ---- Helper function for repeated measures tests ----#

def run_pairwise_contrasts(model, final_df, selected_timepoints, ref_group, test_group, method='sidak'):
    """
    Computes Group B - Group A contrasts at each timepoint using the pooled
    variance/covariance from the already-fitted omnibus model (OLS or MixedLM).

    Uses a numeric contrast (R-matrix) rather than a string hypothesis, because
    MixedLMResults.t_test() does not support patsy-style string formulas the way
    OLSResults.t_test() does (passing a string raises
    AttributeError: 'str' object has no attribute 'shape').

    Also restricts the contrast vector to fixed-effects parameters only
    (model.model.k_fe), since MixedLM's t_test() expects a vector matching
    just the fixed-effects covariance block, not the full params list that
    includes the random-effects variance component ("Subject_ID Var").
    """
    param_names = list(model.params.index)
    # OLS has no random-effects variance term; MixedLM does (k_fe < len(params)).
    k_fe = getattr(model.model, 'k_fe', len(param_names))
    fe_names = param_names[:k_fe]

    group_token = f"[T.{test_group}]"
    group_term = next((p for p in fe_names if group_token in p and ':' not in p), None)

    rows = []
    for tp in selected_timepoints:
        tp_str = str(tp)
        time_token = f"[T.{tp_str}]"
        interaction_term = next(
            (p for p in fe_names if group_token in p and time_token in p and ':' in p),
            None
        )

        if group_term is None:
            rows.append({'Timepoint_Weeks': tp, 'Group A': ref_group, 'Group B': test_group,
                         'Effect_Size': np.nan, 'SE': np.nan, 'p_unc': np.nan})
            continue

        r_matrix = np.zeros(k_fe)
        r_matrix[fe_names.index(group_term)] = 1.0
        if interaction_term is not None:
            r_matrix[fe_names.index(interaction_term)] = 1.0
        r_matrix = r_matrix.reshape(1, -1)

        try:
            contrast = model.t_test(r_matrix)
            rows.append({
                'Timepoint_Weeks': tp,
                'Group A': ref_group,
                'Group B': test_group,
                'Effect_Size': float(np.array(contrast.effect).flatten()[0]),
                'SE': float(np.array(contrast.sd).flatten()[0]),
                'p_unc': float(np.array(contrast.pvalue).flatten()[0])
            })
        except Exception:
            rows.append({'Timepoint_Weeks': tp, 'Group A': ref_group, 'Group B': test_group,
                         'Effect_Size': np.nan, 'SE': np.nan, 'p_unc': np.nan})

    out = pd.DataFrame(rows)
    out['p_corr'] = np.nan
    valid = out['p_unc'].notna()
    if valid.sum() > 0:
        _, p_corr, _, _ = multipletests(out.loc[valid, 'p_unc'].values, method=method)
        out.loc[valid, 'p_corr'] = p_corr
    return out

# --- CACHED DATA LOADER ---
@st.cache_data(show_spinner="Loading data (Optimized)...")
def load_data(file_bytes: bytes, filename: str) -> dict:
    """
    Cached by file content hash. Only re-runs if the file actually changes.
    Supports Excel, HDF5, single Parquet, or ZIP of Parquets.
    """
    file_io = io.BytesIO(file_bytes)
    
    if filename.endswith(".h5"):
        with pd.HDFStore(file_io, mode="r") as store:
            return {key.strip("/"): store[key] for key in store.keys()}
            
    elif filename.endswith(".parquet"):
        df = pd.read_parquet(file_io).rename(columns=column_rename_map)
        return {"Data": df}
        
    elif filename.endswith(".zip"):
        data_dict = {}
        with zipfile.ZipFile(file_io, "r") as z:
            for name in z.namelist():
                if name.endswith('.parquet'):
                    with z.open(name) as f:
                        sheet_name = name.replace('.parquet', '').split('/')[-1]
                        data_dict[sheet_name] = pd.read_parquet(f).rename(columns=column_rename_map)
        return data_dict
        
    else:  # Fallback to Excel
        xls = pd.ExcelFile(file_io)
        return {
            sheet: pd.read_excel(xls, sheet_name=sheet).rename(columns=column_rename_map) 
            for sheet in xls.sheet_names
        }

# --- CACHED STATS ENGINE ---
@st.cache_data(show_spinner="Running statistics (Cached)...")
def run_longitudinal_stats(final_df_json: str, plot_metric: str, selected_groups: tuple, selected_timepoints: tuple):
    """
    Cached statistical pipeline. Streamlit will replay the UI elements generated within this function.
    """
    import warnings
    warnings.filterwarnings("ignore", message=".*Random effects covariance is singular.*", category=UserWarning)
    final_df = pd.read_json(io.StringIO(final_df_json), orient='records')
    display_posthocs = pd.DataFrame()
    function_dict = {}
    
    # BRANCH 1: CROSS-SECTIONAL ANALYSIS (EXACTLY 1 TIMEPOINT)
    if len(selected_timepoints) == 1:
        with st.expander("📊 Cross-Sectional Stats (Click to Expand)", expanded=False):
            tp = selected_timepoints[0]
            st.markdown(f"### Analysis for Week {tp}")
            
            g1_data = final_df[final_df['Group'] == selected_groups[0]][plot_metric]
            g2_data = final_df[final_df['Group'] == selected_groups[1]][plot_metric]
            
            if len(g1_data) < 2 or len(g2_data) < 2:
                st.error(f"🚨 Not enough data at Week {tp}. Group {selected_groups[0]} has n={len(g1_data)}, Group {selected_groups[1]} has n={len(g2_data)}.")
            else:
                base_model = smf.ols("_metric_ ~ C(_group_)", data=final_df).fit()
                residuals = base_model.resid
                
                norm_test = pg.normality(residuals, method='normaltest')
                norm_pval = norm_test['pval'].iloc[0] if not norm_test.empty else 1.0
                is_normal_strict = norm_pval >= 0.05
                
                clt_safe = False
                skewness = 0.0
                if len(residuals) >= 100:
                    skewness = abs(stats.skew(residuals))
                    clt_safe = skewness < 1.0 
                
                use_parametric = is_normal_strict or clt_safe
                
                col_chk1, col_chk2 = st.columns(2)
                with col_chk1:
                    if is_normal_strict:
                        st.success(f"✔️ **Normality:** Passed (p={norm_pval:.4f})")
                        st.info("🚀 **Active Pipeline: Welch's T-Test**")
                    elif clt_safe:
                        st.warning(f"⚠️ **Normality:** Violated (p={norm_pval:.4f})")
                        st.caption(f"🛡️ *CLT Override: With n={len(residuals)} and mild skew ({skewness:.2f}), the T-Test remains mathematically robust.*")
                        st.info("🚀 **Active Pipeline: Welch's T-Test**")
                    else:
                        st.error(f"❌ **Normality:** Severely Violated (p={norm_pval:.4f}, Skew={skewness:.2f})")
                        st.warning("🚀 **Active Pipeline: Mann-Whitney U**")
                        
                with col_chk2:
                    st.info(f"📐 **Sample Sizes:** {selected_groups[0]} (n={len(g1_data)}), {selected_groups[1]} (n={len(g2_data)})")

                try:
                    if use_parametric: res = pg.ttest(g1_data, g2_data)
                    else: res = pg.mwu(g1_data, g2_data)
                        
                    st.markdown("**Results:**")
                    res_show = res.copy()
                    
                    p_col = next((c for c in res_show.columns if c.lower() in ['p-val', 'p_val', 'pval', 'p']), None)
                    eff_col = next((c for c in res_show.columns if 'cohen' in c.lower() or 'cles' in c.lower()), None)
                    
                    if p_col:
                        res_show[p_col] = res_show[p_col].apply(format_pval)
                    st.dataframe(res_show, width='stretch')
                    
                    if p_col:
                        p_val_raw = res[p_col].values[0]
                        d_val = res[eff_col].values[0] if eff_col else np.nan
                        display_posthocs = pd.DataFrame([{
                            'Timepoint_Weeks': tp, 
                            'Group A': selected_groups[0], 
                            'Group B': selected_groups[1], 
                            'p_unc': p_val_raw,
                            'p_corr': p_val_raw,
                            'Effect_Size': d_val
                        }])
                except Exception as e:
                    st.error(f"Test Failed: {e}")

    # BRANCH 2: LONGITUDINAL ANALYSIS (2+ TIMEPOINTS)
    else:
        with st.expander("📊 Statistical Tables, Assumptions & f(x) Functions", expanded=False):
            min_n = final_df.groupby('Group')['Subject_ID'].nunique().min()
            if min_n < 3:
                st.error(f"🚨 **Insufficient Data:** Longitudinal testing requires at least 3 subjects per group. Minimum detected: n={min_n}.")
            else:
                # ENGINE 1: CATEGORICAL STATS
                #OLD SETUP
                # try:
                #     #base_model_cat = smf.mixedlm("_metric_ ~ C(_time_) * C(_group_)", final_df, groups="Subject_ID").fit(method='cg')
                #     #base_model_cat = smf.mixedlm("_metric_ ~ C(_time_) * C(_group_)", final_df, groups="Subject_ID").fit(method='lbfgs')
                #     base_model_cat = smf.mixedlm("_metric_ ~ C(_time_) * C(_group_)", final_df, groups="Subject_ID").fit(method='powell')
                #     residuals = base_model_cat.resid
                # except:
                #     base_model_cat = smf.ols("_metric_ ~ C(_time_) * C(_group_)", data=final_df).fit()
                #     residuals = base_model_cat.resid
                try:
                    # Create a strict bubble to catch the statsmodels warning
                    with warnings.catch_warnings():
                        warnings.filterwarnings("ignore", category=UserWarning, message=".*Random effects covariance is singular.*")
                        base_model_cat = smf.mixedlm("_metric_ ~ C(_time_) * C(_group_)", final_df, groups="Subject_ID").fit(method='lbfgs')
                    residuals = base_model_cat.resid
                except:
                    base_model_cat = smf.ols("_metric_ ~ C(_time_) * C(_group_)", data=final_df).fit()
                    residuals = base_model_cat.resid
                
                norm_test = pg.normality(residuals, method='normaltest')
                norm_pval = norm_test['pval'].iloc[0] if not norm_test.empty else 1.0
                is_normal_strict = norm_pval >= 0.05
                
                clt_safe = False
                skewness = 0.0
                if len(residuals) >= 100:
                    skewness = abs(stats.skew(residuals))
                    clt_safe = skewness < 1.0 
                
                use_parametric = is_normal_strict or clt_safe
                
                expected_tps = len(selected_timepoints)
                subj_tps = final_df.groupby('Subject_ID')['Timepoint_Weeks'].nunique()
                is_balanced = (subj_tps == expected_tps).all()

                st.markdown("### 1. Model Assumptions & Pipeline Selection")
                
                col_chk1, col_chk2 = st.columns(2)
                with col_chk1:
                    if is_normal_strict: 
                        st.success(f"✔️ **Residual Normality:** Passed (p={norm_pval:.4f})")
                    elif clt_safe:
                        st.warning(f"⚠️ **Residual Normality:** Violated (p={norm_pval:.4f})")
                        st.caption(f"🛡️ *CLT Override: With n={len(residuals)} and mild skew ({skewness:.2f}), standard models remain mathematically robust.*")
                    else: 
                        st.error(f"❌ **Residual Normality:** Severely Violated (p={norm_pval:.4f}, Skew={skewness:.2f})")
                        
                with col_chk2:
                    if is_balanced:
                        st.success("✔️ **Design Balance:** Passed (No missing data)")
                    else:
                        st.error("⚠️ **Design Balance:** Violated (Missing timepoints)")
                        expected_tps_list = sorted(selected_timepoints)
                        subj_tps_list = final_df.groupby(['Subject_ID', 'Group'])['Timepoint_Weeks'].agg(list).reset_index()
                        subj_tps_list['Missing_Timepoints'] = subj_tps_list['Timepoint_Weeks'].apply(lambda tps: [t for t in expected_tps_list if t not in tps])
                        incomplete_subjs = subj_tps_list[subj_tps_list['Missing_Timepoints'].str.len() > 0].copy()
                        
                        if not incomplete_subjs.empty:
                            incomplete_subjs['Missing_Timepoints'] = incomplete_subjs['Missing_Timepoints'].apply(lambda x: ", ".join(map(str, x)) + " Weeks")
                            st.dataframe(incomplete_subjs[['Group', 'Subject_ID', 'Missing_Timepoints']].sort_values(['Group', 'Subject_ID']), hide_index=True, width='stretch')

                st.markdown("---")
                
                if use_parametric and is_balanced:
                    st.info("🚀 **Active Pipeline: A (2-Way Mixed-Design ANOVA)**")
                elif use_parametric and not is_balanced:
                    st.warning("🚀 **Active Pipeline: B (Linear Mixed-Effects Model)**")
                else:
                    st.error("🚀 **Active Pipeline: C (Generalized Estimating Equations - GEE)**")

                st.markdown("### 2. Statistical Results")

                if use_parametric and is_balanced:
                    # PIPELINE A: ANOVA
                    try:
                        spher, _, _, _, spher_pval = pg.sphericity(data=final_df, dv='_metric_', within='Timepoint_Weeks', subject='Subject_ID')
                        if not spher: st.warning(f"⚠️ **Sphericity Violated:** p={spher_pval:.4f}. Greenhouse-Geisser correction applied.")
                        
                        anova_res = pg.mixed_anova(dv=plot_metric, within='Timepoint_Weeks', between='Group', subject='Subject_ID', data=final_df)
                        st.markdown("**2-Way Mixed ANOVA (Main Effects & Interaction)**")
                        for col in ['p_unc', 'p_val', 'p_GG_corr']:
                            if col in anova_res.columns: anova_res[col] = anova_res[col].apply(format_pval)
                        st.dataframe(anova_res, width='stretch', hide_index=True)
                        
                        # Old version -- DONT DELETE

                        # st.markdown("**Pairwise T-Tests (Holm-Corrected for FDR)**")
                        # rows = []
                        # for tp in selected_timepoints:
                        #     tp_df = final_df[final_df['Timepoint_Weeks'] == tp]
                        #     g1 = tp_df[tp_df['Group'] == selected_groups[0]][plot_metric]
                        #     g2 = tp_df[tp_df['Group'] == selected_groups[1]][plot_metric]
                        #     if len(g1) > 1 and len(g2) > 1:
                        #         res = pg.ttest(g1, g2)
                        #         p_val_found = next((c for c in res.columns if c.lower() in ['p-val', 'pval', 'p_val', 'p']), None)
                        #         eff_col = next((c for c in res.columns if 'cohen' in c.lower()), None)
                        #         if p_val_found:
                        #             rows.append({'Timepoint_Weeks': tp, 'Group A': selected_groups[0], 'Group B': selected_groups[1], 'p_unc': res[p_val_found].values[0], 'Cohen_d': res[eff_col].values[0] if eff_col else np.nan})
                        # if rows:
                        #     display_posthocs = pd.DataFrame(rows)
                        #     _, p_corr = pg.multicomp(display_posthocs['p_unc'].values, method='holm')
                        #     display_posthocs['p_corr'] = p_corr

                        st.markdown("**Pairwise Contrasts (Model-Based, Šídák-Corrected)**")
                        groups_sorted = sorted(final_df['_group_'].unique())
                        
                        # 🔴 PRISM ALIGNMENT FIX: 
                        # We pass 'base_model_cat' (the MixedLM) instead of a new OLS model.
                        # This calculates contrasts using the repeated-measures pooled error term, 
                        # perfectly matching GraphPad Prism's marginal mean post-hoc methodology.
                        display_posthocs = run_pairwise_contrasts(
                            base_model_cat, final_df, selected_timepoints,
                            ref_group=groups_sorted[0], test_group=groups_sorted[1], method='sidak'
                        )
                    except Exception as e:
                        st.error(f"ANOVA Failed: {e}")

                elif use_parametric and not is_balanced:
                    # PIPELINE B: LMM
                    try:
                        st.markdown("**Linear Mixed-Effects Model (LMM)**")
                        
                        # Fix: Extract raw data from SimpleTable into a Pandas DataFrame
                        sm_table = base_model_cat.summary().tables[1]
                        df_lmm = pd.DataFrame(sm_table.data[1:], columns=sm_table.data[0])
                        
                        st.dataframe(df_lmm.astype(str), width='stretch', hide_index=True)

                        st.markdown("**Pairwise Contrasts (Model-Based, Šídák-Corrected)**")
                        groups_sorted = sorted(final_df['_group_'].unique())
                        display_posthocs = run_pairwise_contrasts(
                            base_model_cat, final_df, selected_timepoints,
                            ref_group=groups_sorted[0], test_group=groups_sorted[1], method='sidak'
                        )
                    except Exception as e:
                        st.error(f"LMM Failed: {e}")

                else:
                    # PIPELINE C: GEE
                    st.markdown("**Generalized Estimating Equations (GEE)**")
                    try:
                        # Extract the raw dependent variable data
                        metric_data = final_df['_metric_'].dropna()

                        # 1. Check for Count Data (All values are integers and >= 0)
                        is_count = (metric_data >= 0).all() and pd.api.types.is_integer_dtype(metric_data) or (metric_data % 1 == 0).all()

                        # 2. Check for Strictly Positive Continuous Data (Values > 0)
                        is_strictly_positive = (metric_data > 0).all()

                        # 3. Assess Skewness
                        skewness = stats.skew(metric_data)

                        # Dynamic Family Assignment
                        if is_count:
                            st.info("📊 **GEE Distribution:** Detected count data. Applying Poisson family.")
                            fam = sm.families.Poisson()
                        elif is_strictly_positive and skewness > 1.0:
                            st.info("📊 **GEE Distribution:** Detected heavily right-skewed positive data. Applying Gamma family.")
                            fam = sm.families.Gamma(link=sm.families.links.Log())
                        else:
                            st.info("📊 **GEE Distribution:** Defaulting to Gaussian family with robust standard errors.")
                            fam = sm.families.Gaussian()

                        # Fit the GEE with the dynamically selected family
                        cov_struct = sm.cov_struct.Autoregressive()
                        md = smf.gee("_metric_ ~ C(_time_) * C(_group_)", groups=final_df["Subject_ID"], data=final_df, cov_struct=cov_struct, family=fam)
                        mdf = md.fit()
                        
                        sm_table = mdf.summary().tables[1]
                        df_gee = pd.DataFrame(sm_table.data[1:], columns=sm_table.data[0])
                        st.dataframe(df_gee, width='stretch')
                        
                        st.markdown("**GEE Pairwise Contrasts (Model-Based, Holm-Corrected)**")
                        groups_sorted = sorted(final_df['_group_'].unique())

                        # Leverage your existing matrix-based helper function to bypass string parsing errors
                        display_posthocs = run_pairwise_contrasts(
                            mdf, final_df, selected_timepoints,
                            ref_group=groups_sorted[0], test_group=groups_sorted[1], method='holm'
                        )
                    except Exception as e:
                        st.error(f"GEE Failed: {e}")

                if not display_posthocs.empty:
                    df_show = display_posthocs.copy()
                    for col in ['p_unc', 'p_corr']:
                        if col in df_show.columns: df_show[col] = df_show[col].apply(format_pval)
                    for col in ['Cohen_d', 'Effect_Size']:
                        if col in df_show.columns: df_show[col] = df_show[col].apply(lambda x: f"{x:.3f}" if pd.notna(x) else "NaN")
                    st.dataframe(df_show, width='stretch', hide_index=True)

                st.markdown("---")

                # ENGINE 2: CONTINUOUS MATH --- Makes no sense in the scope of this project, but leaving it here for future reference.
                # try:
                #     # groups_sorted = sorted(final_df['_group_'].unique())
                #     # ref_group, test_group = groups_sorted[0], groups_sorted[1]
                #     # #base_model_cont = smf.mixedlm("_metric_ ~ _time_cont_ * C(_group_)", final_df, groups="Subject_ID").fit(method='lbfgs')
                #     # base_model_cont = smf.mixedlm("_metric_ ~ _time_cont_ * C(_group_)", final_df, groups="Subject_ID").fit(method='powell')
                #     # #base_model_cont = smf.mixedlm("_metric_ ~ _time_cont_ * C(_group_)", final_df, groups="Subject_ID").fit(method='cg')
                #     # params = base_model_cont.params
                #     groups_sorted = sorted(final_df['_group_'].unique())
                #     ref_group, test_group = groups_sorted[0], groups_sorted[1]
                    
                #     # Create the same strict bubble here
                #     with warnings.catch_warnings():
                #         warnings.filterwarnings("ignore", category=UserWarning, message=".*Random effects covariance is singular.*")
                #         base_model_cont = smf.mixedlm("_metric_ ~ _time_cont_ * C(_group_)", final_df, groups="Subject_ID").fit(method='lbfgs')
                    
                #     params = base_model_cont.params
                    
                #     b_ref = params.get('Intercept', 0)
                #     m_ref = params.get('_time_cont_', 0)
                    
                #     group_term = next((k for k in params.keys() if test_group in k and '_time_cont_' not in k), None)
                #     interaction_term = next((k for k in params.keys() if test_group in k and '_time_cont_' in k), None)
                    
                #     b_diff = params.get(group_term, 0) if group_term else 0
                #     m_diff = params.get(interaction_term, 0) if interaction_term else 0
                    
                #     b_test, m_test = b_ref + b_diff, m_ref + m_diff
                #     function_dict[ref_group] = {'m': m_ref, 'b': b_ref}
                #     function_dict[test_group] = {'m': m_test, 'b': b_test}

                #     st.markdown("### 3. Derived Growth Curve Functions $f(x)$")
                #     st.markdown("These continuous functions describe the overall trajectory of the data over time.")
                #     st.latex(f"f_{{{ref_group}}}(x) = {m_ref:.4f}x {'+' if b_ref >= 0 else '-'} {abs(b_ref):.4f}")
                #     st.latex(f"f_{{{test_group}}}(x) = {m_test:.4f}x {'+' if b_test >= 0 else '-'} {abs(b_test):.4f}")
                # except Exception as e:
                #     st.error(f"Failed to extract f(x) functions: {e}")
                    
    return display_posthocs, function_dict

# --- STREAMLIT FRAGMENT FOR PLOTTING ---
@st.fragment
def render_plot_section(final_df, display_posthocs, function_dict, color_map, plot_metric, selected_plot_timepoints, annotation_color):
    """Isolated rerun fragment for rendering plots instantly without recalculating stats/data."""
    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        plot_format = st.selectbox("Plot Format:", ["Line Plot", "Bar Plot", "Box Plot", "Violin Plot"])
    with col_p2:
        if plot_format in ["Line Plot", "Bar Plot"]:
            show_error_bars = st.checkbox("Show SEM error bars", value=True)
            show_points = False
        else:
            show_points = st.checkbox("Show all data points", value=True)
            show_error_bars = False

    # This is working with engine 2 - continuous math for growth curve functions, but it's not relevant to the current project. Leaving it commented out for future reference. 
    # ------------------------------------------------------------------------------------------------------------------------------------------------------------------------#       
    # with col_p3:
    #     show_pvals_on_line = st.checkbox("Draw significance asterisks on plot", value=True)
    #     if plot_format == "Line Plot":
    #         show_growth_curves = st.checkbox("Overlay continuous f(x) curve", value=True)
    #     else:
    #         show_growth_curves = False

    with col_p3:
        show_pvals_on_line = st.checkbox("Draw significance asterisks on plot", value=True)
    with st.expander("⚙️ Advanced Plot Settings", expanded=False):
        col_x1, col_x2 = st.columns(2)
        with col_x1:
            force_exact_ticks = st.checkbox("Force exact timepoint labels", value=True)
        with col_x2:
            custom_x_range = st.checkbox("Customize X-Axis Range", value=False)
        
        if custom_x_range:
            min_tp, max_tp = float(min(selected_plot_timepoints)), float(max(selected_plot_timepoints))
            margin = (max_tp - min_tp) * 0.1 if max_tp != min_tp else 1.0
            col_r1, col_r2 = st.columns(2)
            with col_r1: x_min = st.number_input("X-Axis Minimum", value=min_tp - margin)
            with col_r2: x_max = st.number_input("X-Axis Maximum", value=max_tp + margin)

    summary_df = final_df.groupby(['Group', 'Timepoint_Weeks'])[plot_metric].agg(['mean', 'sem']).reset_index()
    summary_df = summary_df.rename(columns={'mean': plot_metric, 'sem': 'SEM'}).sort_values(by='Timepoint_Weeks')
    title_text = f"Longitudinal Progression of {plot_metric}"

    if plot_format == "Line Plot":
        fig = px.line(summary_df, x='Timepoint_Weeks', y=plot_metric, color='Group', markers=True, error_y='SEM' if show_error_bars else None, title=title_text, color_discrete_map=color_map)
    elif plot_format == "Bar Plot":
        fig = px.bar(summary_df, x='Timepoint_Weeks', y=plot_metric, color='Group', barmode='group', error_y='SEM' if show_error_bars else None, title=title_text, color_discrete_map=color_map)
    elif plot_format == "Box Plot":
        fig = px.box(final_df, x='Timepoint_Weeks', y=plot_metric, color='Group', points="all" if show_points else False, title=title_text, color_discrete_map=color_map)
    elif plot_format == "Violin Plot":
        fig = px.violin(final_df, x='Timepoint_Weeks', y=plot_metric, color='Group', box=True, points="all" if show_points else False, title=title_text, color_discrete_map=color_map)
    
    # This is working with engine 2 - continuous math for growth curve functions, but it's not relevant to the current project. Leaving it commented out for future reference. 
    # ------------------------------------------------------------------------------------------------------------------------------------------------------------------------#   
    # if plot_format == "Line Plot" and show_growth_curves and function_dict:
    #     min_x, max_x = final_df['_time_cont_'].min(), final_df['_time_cont_'].max()
    #     x_continuous = np.linspace(min_x, max_x, 100)
    #     for grp, equation in function_dict.items():
    #         y_continuous = (equation['m'] * x_continuous) + equation['b']
    #         line_color = color_map.get(grp, 'gray')
    #         fig.add_scatter(x=x_continuous, y=y_continuous, mode='lines', name=f"{grp} f(x) Trend", line=dict(color=line_color, width=3, dash='dot'), showlegend=True)

    xaxis_dict = dict(type='linear')
    if force_exact_ticks: xaxis_dict['tickvals'] = sorted(final_df['Timepoint_Weeks'].unique())
    if custom_x_range: xaxis_dict['range'] = [x_min, x_max]
    fig.update_layout(xaxis=xaxis_dict)

    if show_pvals_on_line and not display_posthocs.empty:
        y_max_overall, y_min_overall = final_df[plot_metric].max(), final_df[plot_metric].min()
        offset = (y_max_overall - y_min_overall) * 0.08 if y_max_overall != y_min_overall else (y_max_overall * 0.05)
        valid_p_cols = ['p_corr', 'p-corr', 'p_unc', 'p-unc', 'p_val', 'pval', 'p', 'p-val']
        p_col = next((c for c in display_posthocs.columns if c.lower() in valid_p_cols), None)

        if p_col:
            highest_drawn_y = y_max_overall
            for _, row in display_posthocs.iterrows():
                tp = row['Timepoint_Weeks']
                raw_pval = str(row[p_col]).replace('<', '').replace('>', '').replace('=', '').strip()
                try:
                    pval = float(raw_pval)
                    if pval < 0.001: star = "***"
                    elif pval < 0.01: star = "**"
                    elif pval < 0.05: star = "*"
                    else: star = "ns" 
                    
                    if plot_format in ["Line Plot", "Bar Plot"] and show_error_bars:
                        tp_summary = summary_df[summary_df['Timepoint_Weeks'].astype(str) == str(tp)]
                        if tp_summary.empty: continue
                        y_highest_tp = (tp_summary[plot_metric] + tp_summary['SEM'].fillna(0)).max()
                    else:
                        tp_raw = final_df[final_df['Timepoint_Weeks'].astype(str) == str(tp)][plot_metric]
                        if tp_raw.empty: continue
                        y_highest_tp = tp_raw.max()

                    y_pos = y_highest_tp + offset
                    if y_pos > highest_drawn_y: highest_drawn_y = y_pos

                    fig.add_annotation(x=tp, y=y_pos, text=star, showarrow=False, font=dict(size=14 if star == "ns" else 22, color=annotation_color, family="Arial"))
                except Exception as e: pass
                    
            fig.update_layout(yaxis=dict(range=[y_min_overall - (offset * 0.5), highest_drawn_y + (offset * 1.5)]))

    fig.update_layout(margin=dict(t=30))
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes()

    st.plotly_chart(fig, width='stretch')

# --- JOBLIB THREADING FUNCTION FOR EXPORT ---
def render_single_metric_job(metric, df_to_plot, mapping_filtered, selected_plot_timepoints, selected_plot_groups, color_map, xaxis_dict):
    """Isolated function for multithreading the export sequence."""
    loop_merged = pd.merge(df_to_plot[['Ids', metric]], mapping_filtered, on='Ids')
    loop_merged[metric] = pd.to_numeric(loop_merged[metric], errors='coerce')
    loop_df = loop_merged.dropna(subset=[metric]).copy()
    
    if loop_df.empty or loop_df['Group'].nunique() < 2:
        return None, None
    
    loop_summary = loop_df.groupby(['Group', 'Timepoint_Weeks'])[metric].agg(['mean', 'sem']).reset_index()
    loop_summary = loop_summary.rename(columns={'mean': metric, 'sem': 'SEM'}).sort_values(by='Timepoint_Weeks')
    title_text = f"Longitudinal Progression of {metric}"
    
    batch_posthocs = pd.DataFrame()
    rows = []
    loop_df['_tp_numeric_'] = pd.to_numeric(loop_df['Timepoint_Weeks'], errors='coerce')
    
    for tp in selected_plot_timepoints:
        try: tp_num = float(tp)
        except ValueError: continue 
            
        tp_df = loop_df[loop_df['_tp_numeric_'] == tp_num]
        g1 = pd.to_numeric(tp_df[tp_df['Group'] == selected_plot_groups[0]][metric], errors='coerce').dropna()
        g2 = pd.to_numeric(tp_df[tp_df['Group'] == selected_plot_groups[1]][metric], errors='coerce').dropna()
        
        if len(g1) > 1 and len(g2) > 1:
            try:
                res = pg.ttest(g1, g2)
                p_col = next((c for c in res.columns if c.lower() in ['p-val', 'pval', 'p_val', 'p']), None)
                if p_col: rows.append({'Timepoint_Weeks': tp_num, 'p_val': float(res[p_col].iloc[0])})
            except: 
                try:
                    res = pg.mwu(g1, g2)
                    p_col = next((c for c in res.columns if c.lower() in ['p-val', 'pval', 'p_val', 'p']), None)
                    if p_col: rows.append({'Timepoint_Weeks': tp_num, 'p_val': float(res[p_col].iloc[0])})
                except: pass
    
    if rows:
        batch_posthocs = pd.DataFrame(rows)
        if len(batch_posthocs) > 1:
            _, p_corr = pg.multicomp(batch_posthocs['p_val'].values, method='holm')
            batch_posthocs['p_val'] = p_corr

    loop_fig = px.line(loop_summary, x='Timepoint_Weeks', y=metric, color='Group', markers=True, error_y='SEM', title=title_text, labels={'Timepoint_Weeks': 'Timepoint (Weeks)'}, color_discrete_map=color_map)
    loop_fig.update_layout(xaxis=xaxis_dict)
    
    if not batch_posthocs.empty:
        y_max_overall, y_min_overall = loop_df[metric].max(), loop_df[metric].min()
        offset = (y_max_overall - y_min_overall) * 0.08 if y_max_overall != y_min_overall else (y_max_overall * 0.05)
        highest_drawn_y = y_max_overall
        loop_summary['_tp_numeric_'] = pd.to_numeric(loop_summary['Timepoint_Weeks'], errors='coerce')

        for _, row in batch_posthocs.iterrows():
            tp_num, pval = float(row['Timepoint_Weeks']), float(row['p_val'])
            if pval < 0.001: star = "***"
            elif pval < 0.01: star = "**"
            elif pval < 0.05: star = "*"
            else: star = "ns"

            tp_summary = loop_summary[loop_summary['_tp_numeric_'] == tp_num]
            if tp_summary.empty: continue
            y_highest_tp = float((tp_summary[metric] + tp_summary['SEM'].fillna(0)).max())

            y_pos = y_highest_tp + offset
            if y_pos > highest_drawn_y: highest_drawn_y = y_pos

            loop_fig.add_annotation(x=tp_num, y=float(y_pos), text=star, showarrow=False, font=dict(size=14 if star == "ns" else 22, color="#000000", family="Arial"))

        loop_fig.update_layout(yaxis=dict(range=[y_min_overall - (offset * 0.5), highest_drawn_y + (offset * 1.5)]))

    loop_fig.update_layout(margin=dict(t=30), paper_bgcolor="white", plot_bgcolor="white", font=dict(color="black"))
    loop_fig.update_xaxes(showline=True, linewidth=1, linecolor='black', gridcolor='lightgrey')
    loop_fig.update_yaxes(showline=True, linewidth=1, linecolor='black', gridcolor='lightgrey')
    
    img_bytes = loop_fig.to_image(format="png", width=1200, height=800, scale=2)
    safe_metric = "".join([c for c in metric if c.isalpha() or c.isdigit() or c==' ']).rstrip()
    return safe_metric, img_bytes

# --- 1. FILE UPLOAD ---
uploaded_file = st.file_uploader("Upload your Cleaned Data File", type=['xlsx', 'h5', 'parquet', 'zip'])

if uploaded_file:
    file_bytes = uploaded_file.read()
    
    if 'data_dict' not in st.session_state or st.session_state.get('uploaded_filename') != uploaded_file.name:
        st.session_state.data_dict = load_data(file_bytes, uploaded_file.name)
        st.session_state.sheet_names = list(st.session_state.data_dict.keys())
        st.session_state.uploaded_filename = uploaded_file.name
        
        # Cleanup old session states
        keys_to_delete = ['mapping_df', 'group_definitions_final', 'run_stats']
        for key in keys_to_delete:
            if key in st.session_state:
                del st.session_state[key]
        
    data_dict = st.session_state.data_dict
    sheet_names = st.session_state.sheet_names

    # --- SIDEBAR SETTINGS ---
    st.sidebar.header("🎨 Custom Group Colors")
    color_map = {}
    if 'mapping_df' in st.session_state:
        extracted_groups = [g for g in st.session_state.mapping_df['Group'].unique() if g != "Unknown"]
        default_colors = px.colors.qualitative.Plotly + px.colors.qualitative.D3
        for i, grp in enumerate(sorted(extracted_groups)):
            default_hex = default_colors[i % len(default_colors)]
            color_map[grp] = st.sidebar.color_picker(f"{grp} Color", default_hex, key=f"color_{grp}")
            
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Global Plot Settings")
    annotation_color = st.sidebar.color_picker(
        "Significance Annotation Color", 
        "#000000", 
        help="Change this to White (#FFFFFF) if you are using Streamlit's Dark Mode so the asterisks are visible."
    )

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 Data Viewer", 
        "🆔 ID Overview", 
        "🧪 Experimental Groups Setup", 
        "🧮 2-Group Analysis ➡️ Longitudinal Plotting 📈",
        "🌐 Multi-Group Omnibus Analysis",
        "🕸️ Radar Plots"
    ])

    # --- TAB 1: DATA VIEWER ---
    with tab1:
        st.subheader("View Individual Sheets")
        selected_sheet = st.selectbox("Select a sheet to display:", sheet_names, key="viewer_sheet_select")
        st.dataframe(data_dict[selected_sheet], width='stretch')

    # --- TAB 2: ID OVERVIEW ---
    with tab2:
        st.subheader("Extracted IDs")
        first_sheet_df = data_dict[sheet_names[0]]
        if 'Ids' in first_sheet_df.columns:
            unique_ids = first_sheet_df['Ids'].unique()
            st.write(f"**Total unique rows/trials found:** {len(unique_ids)}")
            st.dataframe(pd.DataFrame(unique_ids, columns=["Subject IDs"]), width='stretch')
        else:
            st.error("Could not find an 'Ids' column. Please check your file format.")

    # --- TAB 3: EXPERIMENTAL GROUPS SETUP ---
    with tab3:
        st.subheader("Define Groups and Parse Timepoints")
        st.markdown("""
        Manually define your experimental groups below. 
        * **Group Name**: The clean name displayed on plots.
        * **Tag in ID**: The exact text snippet the program should look for in the Subject ID.
        """)
        
        if 'group_definitions' not in st.session_state:
            st.session_state.group_definitions = pd.DataFrame({
                "Group Name": ["Wildtype", "Transgenic", "WT Male", "WT Female", "TG Male", "TG Female"],
                "Tag in ID": ["WT", "TG", "WT_M", "WT_F", "TG_M", "TG_F"]
            })
        
        edited_groups = st.data_editor(
            st.session_state.group_definitions,
            num_rows="dynamic",
            width='stretch',
            hide_index=True,
            key="groups_editor"
        )

        if st.button("Extract Variables from IDs", type="secondary", key="extract_vars_btn"):
            if 'unique_ids' not in locals():
                first_sheet_df = data_dict[sheet_names[0]]
                if 'Ids' in first_sheet_df.columns:
                    unique_ids = first_sheet_df['Ids'].unique()
                else:
                    st.error("Could not find an 'Ids' column to extract from.")
                    st.stop()

            valid_groups = edited_groups.dropna(how='all').copy()
            valid_groups["Tag in ID"] = valid_groups["Tag in ID"].astype(str).str.strip()
            valid_groups["Group Name"] = valid_groups["Group Name"].astype(str).str.strip()
            valid_groups = valid_groups[valid_groups["Tag in ID"] != ""]
            valid_groups['tag_length'] = valid_groups['Tag in ID'].apply(len)
            valid_groups = valid_groups.sort_values('tag_length', ascending=False).drop(columns=['tag_length'])

            def extract_timepoint(id_str):
                match_w = re.search(r'(\d+)[Ww]', str(id_str))
                if match_w: return int(match_w.group(1))
                match_t = re.search(r'[Tt](\d+)', str(id_str))
                if match_t: return int(match_t.group(1))
                return None
            
            def extract_subject_id(id_str):
                tokens = str(id_str).split('_')
                for i, token in enumerate(tokens):
                    if re.fullmatch(r'(?:[Ww]eek\s*)?\d+\s*[Ww]|[Ww]\s*\d+|[Tt]\s*\d+|\d+\s*[Tt]', token):
                        return "_".join(tokens[:i])
                return tokens[0]

            mapping_records = []
            for id_str in unique_ids:
                timepoint = extract_timepoint(id_str)
                subject_id = extract_subject_id(id_str)
                id_upper = str(id_str).upper()
                
                matched_groups = []
                for _, row in valid_groups.iterrows():
                    tag = row["Tag in ID"].upper()
                    if tag and tag in id_upper:
                        matched_groups.append(row["Group Name"])
                
                if not matched_groups:
                    matched_groups.append("Unknown")
                    
                for grp in matched_groups:
                    mapping_records.append({
                        "Ids": id_str,
                        "Timepoint_Weeks": timepoint,
                        "Subject_ID": subject_id,
                        "Group": grp
                    })
            
            mapping_df = pd.DataFrame(mapping_records)
            st.session_state.mapping_df = mapping_df
            st.session_state.group_definitions_final = valid_groups 
            
            st.success("Variables extracted successfully! You can now choose your group colors in the sidebar.")
            st.rerun()
        
        if 'mapping_df' in st.session_state:
            st.markdown("### 🚫 Exclude Specific Subjects")
            all_extracted_subjects = sorted(st.session_state.mapping_df['Subject_ID'].dropna().unique())
            
            subjects_to_exclude = st.multiselect(
                "Select any subjects you want to completely remove from all plots and stats (e.g., outliers, dropouts):", 
                options=all_extracted_subjects,
                key="exclude_subjects_ui"
            )
            
            map_df_clean = st.session_state.mapping_df.copy()
            if subjects_to_exclude:
                map_df_clean = map_df_clean[~map_df_clean['Subject_ID'].isin(subjects_to_exclude)]
                st.warning(f"Excluded {len(subjects_to_exclude)} subjects from the dataset.")

            st.markdown("### 📋 Group Summary (N)")
            if not map_df_clean.empty and 'Group' in map_df_clean.columns:
                group_counts = map_df_clean[map_df_clean['Group'] != 'Unknown'].groupby('Group')['Subject_ID'].nunique().reset_index()
                if not group_counts.empty:
                    group_counts.columns = ['Experimental Group', 'Number of Unique Subjects (N)']
                    st.dataframe(group_counts, width='stretch', hide_index=True)

        if 'mapping_df' in st.session_state:
            with st.expander("🚨 Troubleshooting: Unmatched IDs & Missing Timepoints", expanded=True):
                debug_df = st.session_state.mapping_df
                
                unknown_groups = debug_df[debug_df['Group'] == 'Unknown']
                missing_timepoints = debug_df[debug_df['Timepoint_Weeks'].isna()]
                
                col_d1, col_d2 = st.columns(2)
                
                with col_d1:
                    st.markdown("#### ❌ Failed Group Match")
                    st.caption("These IDs didn't contain any of your defined tags.")
                    if unknown_groups.empty:
                        st.success("All IDs successfully mapped to groups!")
                    else:
                        st.dataframe(unknown_groups[['Ids', 'Subject_ID']].drop_duplicates(), width='stretch', hide_index=True)
                        
                with col_d2:
                    st.markdown("#### ⏱️ Failed Timepoint Extraction")
                    st.caption("The regex could not find a valid week/time in these IDs.")
                    if missing_timepoints.empty:
                        st.success("All IDs have a valid timepoint!")
                    else:
                        st.dataframe(missing_timepoints[['Ids', 'Group']].drop_duplicates(), width='stretch', hide_index=True)

    # --- TAB 4: LONGITUDINAL ANALYSIS & STATS ---
    with tab4:
        st.subheader("Longitudinal Progression & Statistical Analysis")
        
        if 'mapping_df' not in st.session_state:
            st.warning("⚠️ Please go to the 'Experimental Groups Setup' tab and extract variables first.")
        else:
            mapping_df = st.session_state.mapping_df.copy()
            if st.session_state.get('exclude_subjects_ui'):
                mapping_df = mapping_df[~mapping_df['Subject_ID'].isin(st.session_state.exclude_subjects_ui)]
            
            col1, col2 = st.columns(2)
            with col1:
                plot_sheet = st.selectbox("Select Statistic (Sheet):", sheet_names, key="plot_sheet")
            
            df_to_plot = data_dict[plot_sheet]
            numeric_cols = [col for col in df_to_plot.columns if col != 'Ids']
            
            with col2:
                plot_metric = st.selectbox("Select Measurement to Analyze:", numeric_cols, key="plot_metric_select")
            
            all_groups = sorted([g for g in mapping_df['Group'].unique() if g != "Unknown"])
            all_timepoints = sorted(mapping_df['Timepoint_Weeks'].dropna().unique())
            
            col_grp, col_tp = st.columns(2)
            with col_grp:
                selected_plot_groups = st.multiselect(
                    "Select EXACTLY 2 Groups for ANOVA & Plotting:", 
                    all_groups, 
                    default=all_groups[:2] if len(all_groups) >= 2 else all_groups,
                    key="plot_groups_multiselect"
                )
            with col_tp:
                selected_plot_timepoints = st.multiselect(
                    "Select Timepoints to Display:", 
                    all_timepoints, 
                    default=all_timepoints,
                    key="plot_tps_multiselect"
                )

            if len(selected_plot_groups) != 2:
                st.error("🚨 Statistical significance requires exactly 2 groups selected.")
            elif len(selected_plot_timepoints) == 0:
                st.error("🚨 Please select at least 1 timepoint to analyze.")
            else:
                # --- DATA PREPARATION (Optimized with Polars) ---
                mapping_filtered = mapping_df[
                    (mapping_df['Group'].isin(selected_plot_groups)) & 
                    (mapping_df['Timepoint_Weeks'].isin(selected_plot_timepoints))
                ]
                
                merged_pl = (
                    pl.from_pandas(df_to_plot[['Ids', plot_metric]])
                    .join(pl.from_pandas(mapping_filtered), on='Ids', how='inner')
                    .with_columns(pl.col(plot_metric).cast(pl.Float64, strict=False))
                    .drop_nulls(subset=[plot_metric])
                    .group_by(['Subject_ID', 'Group', 'Timepoint_Weeks'])
                    .agg(pl.col(plot_metric).mean())
                )
                final_df = merged_pl.to_pandas()

                final_df['_metric_'] = final_df[plot_metric].astype(float)
                final_df['_time_'] = final_df['Timepoint_Weeks'].astype(str)
                final_df['_time_cont_'] = final_df['Timepoint_Weeks'].astype(float) 
                final_df['_group_'] = final_df['Group'].astype(str)

                # --- CALL CACHED STATS ENGINE (AUTO-RUN) ---
                display_posthocs, function_dict = run_longitudinal_stats(
                    final_df.to_json(orient='records'),
                    plot_metric,
                    tuple(selected_plot_groups),
                    tuple(selected_plot_timepoints)
                )

                # --- RENDER ISOLATED PLOTTING FRAGMENT ---
                if not final_df.empty:
                    render_plot_section(
                        final_df, 
                        display_posthocs, 
                        function_dict, 
                        color_map, 
                        plot_metric, 
                        selected_plot_timepoints, 
                        annotation_color
                    )


                # --- SECTION 4: BATCH EXPORT (Parallelized via joblib) ---
                st.markdown("---")
                st.subheader("📦 Batch Export All Measurements")
                st.write("Generate and download a ZIP archive containing high-resolution **PNG** plots (with statistical significance) for **all** measurements in the current sheet.")
                
                if st.button("Generate All Plots (ZIP)", type="secondary"):
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    status_text.text("Parallelizing Image Renders...")
                    
                    zip_buffer = io.BytesIO()
                    
                    xaxis_dict = dict(type='linear', tickvals=sorted(selected_plot_timepoints))
                    
                    results = Parallel(n_jobs=-1, backend="threading")(
                        delayed(render_single_metric_job)(
                            metric, df_to_plot, mapping_filtered, 
                            selected_plot_timepoints, selected_plot_groups, color_map, xaxis_dict
                        ) for metric in numeric_cols
                    )
                    
                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                        for idx, (safe_metric, img_bytes) in enumerate(results):
                            if img_bytes:
                                zip_file.writestr(f"{safe_metric}.png", img_bytes)
                            progress_bar.progress((idx + 1) / len(numeric_cols))
                            
                    status_text.success("✅ All plots generated successfully! Ready for download.")
                    
                    st.download_button(
                        label="📥 Download PNG ZIP",
                        data=zip_buffer.getvalue(),
                        file_name=f"All_Kinematic_PNGs_{plot_sheet}.zip",
                        mime="application/zip"
                    )

    # --- TAB 5: MULTI-GROUP OMNIBUS ANALYSIS ---
    with tab5:
        st.subheader("Multi-Group Omnibus Analysis (3+ Groups)")
        
        if 'mapping_df' not in st.session_state:
            st.warning("⚠️ Please go to the 'Experimental Groups Setup' tab and extract variables first.")
        else:
            mapping_df = st.session_state.mapping_df.copy()
            if st.session_state.get('exclude_subjects_ui'):
                mapping_df = mapping_df[~mapping_df['Subject_ID'].isin(st.session_state.exclude_subjects_ui)]
            
            col1_m, col2_m = st.columns(2)
            with col1_m:
                plot_sheet_m = st.selectbox("Select Statistic (Sheet):", sheet_names, key="plot_sheet_multi")
            
            df_to_plot_m = data_dict[plot_sheet_m]
            numeric_cols_m = [col for col in df_to_plot_m.columns if col != 'Ids']
            
            with col2_m:
                plot_metric_m = st.selectbox("Select Measurement to Analyze:", numeric_cols_m, key="plot_metric_select_multi")
            
            all_groups_m = sorted([g for g in mapping_df['Group'].unique() if g != "Unknown"])
            all_timepoints_m = sorted(mapping_df['Timepoint_Weeks'].dropna().unique())
            
            col_grp_m, col_tp_m = st.columns(2)
            with col_grp_m:
                selected_multi_groups = st.multiselect(
                    "Select 3 or more Groups:", 
                    all_groups_m, 
                    default=all_groups_m if len(all_groups_m) >= 3 else None,
                    key="plot_groups_multiselect_multi"
                )
            with col_tp_m:
                selected_multi_tps = st.multiselect(
                    "Select Timepoints:", 
                    all_timepoints_m, 
                    default=all_timepoints_m,
                    key="plot_tps_multiselect_multi"
                )

            if len(selected_multi_groups) < 3:
                st.info("💡 Please select at least 3 groups to use the Multi-Group analysis engine. For 2 groups, use Tab 4.")
            elif len(selected_multi_tps) == 0:
                st.error("🚨 Please select at least 1 timepoint to analyze.")
            else:
                # --- DATA PREP ---
                mapping_filt_m = mapping_df[
                    (mapping_df['Group'].isin(selected_multi_groups)) & 
                    (mapping_df['Timepoint_Weeks'].isin(selected_multi_tps))
                ]
                
                merged_pl_m = (
                    pl.from_pandas(df_to_plot_m[['Ids', plot_metric_m]])
                    .join(pl.from_pandas(mapping_filt_m), on='Ids', how='inner')
                    .with_columns(pl.col(plot_metric_m).cast(pl.Float64, strict=False))
                    .drop_nulls(subset=[plot_metric_m])
                    .group_by(['Subject_ID', 'Group', 'Timepoint_Weeks'])
                    .agg(pl.col(plot_metric_m).mean())
                )
                final_df_m = merged_pl_m.to_pandas()
                final_df_m['_metric_'] = final_df_m[plot_metric_m].astype(float)
                
                # --- VISUALIZATION (Clean Plot, No Asterisks) ---
                col_pm1, col_pm2 = st.columns(2)
                with col_pm1:
                    plot_format_m = st.selectbox("Plot Format:", ["Line Plot", "Box Plot"], key="multi_format")
                with col_pm2:
                    if plot_format_m == "Line Plot":
                        show_error_m = st.checkbox("Show SEM error bars", value=True, key="multi_err")
                    else:
                        show_pts_m = st.checkbox("Show all data points", value=False, key="multi_pts")

                summary_df_m = final_df_m.groupby(['Group', 'Timepoint_Weeks'])[plot_metric_m].agg(['mean', 'sem']).reset_index()
                summary_df_m = summary_df_m.rename(columns={'mean': plot_metric_m, 'sem': 'SEM'}).sort_values(by='Timepoint_Weeks')
                title_text_m = f"Omnibus Progression of {plot_metric_m}"

                if plot_format_m == "Line Plot":
                    fig_m = px.line(summary_df_m, x='Timepoint_Weeks', y=plot_metric_m, color='Group', markers=True, error_y='SEM' if show_error_m else None, title=title_text_m, color_discrete_map=color_map)
                else:
                    fig_m = px.box(final_df_m, x='Timepoint_Weeks', y=plot_metric_m, color='Group', points="all" if show_pts_m else False, title=title_text_m, color_discrete_map=color_map)

                fig_m.update_layout(margin=dict(t=30), xaxis=dict(type='linear', tickvals=sorted(selected_multi_tps)))
                st.plotly_chart(fig_m, width='stretch')

                # --- STATS: OMNIBUS & POST-HOC HEATMAP TABLE ---
                st.markdown("### Post-Hoc Pairwise Comparisons (FDR-Corrected)")
                st.write("This table shows every pairwise comparison at each timepoint. P-values are corrected for multiple comparisons to prevent false positives.")
                
                posthoc_rows = []
                for tp in selected_multi_tps:
                    tp_data = final_df_m[final_df_m['Timepoint_Weeks'] == tp]
                    if tp_data['Group'].nunique() >= 2:
                        try:
                            # Use pingouin's pairwise tests for quick, comprehensive multi-group post-hocs
                            pt = pg.pairwise_tests(data=tp_data, dv='_metric_', between='Group', padjust='fdr_bh')
                            
                            # Dynamically find the p-value columns to prevent KeyError
                            p_unc_col = next((c for c in pt.columns if c.lower() in ['p-unc', 'p_unc', 'p-val', 'pval', 'p_val', 'p']), None)
                            p_corr_col = next((c for c in pt.columns if c.lower() in ['p-corr', 'p_corr']), None)
                            
                            if p_unc_col:
                                for _, row in pt.iterrows():
                                    posthoc_rows.append({
                                        'Timepoint_Weeks': tp,
                                        'Group A': row['A'],
                                        'Group B': row['B'],
                                        'p_uncorrected': row[p_unc_col],
                                        'p_FDR_corrected': row[p_corr_col] if p_corr_col and pd.notna(row[p_corr_col]) else row[p_unc_col]
                                    })
                        except Exception as e:
                            pass # Silently skip math errors (e.g., zero variance or n=1)
                            
                if posthoc_rows:
                    ph_df = pd.DataFrame(posthoc_rows)
                    # Create a "Significance" flag for easy reading
                    ph_df['Significant?'] = ph_df['p_FDR_corrected'].apply(lambda p: "⭐ Yes" if p < 0.05 else "No")
                    
                    # Format p-values beautifully
                    ph_df['p_uncorrected'] = ph_df['p_uncorrected'].apply(format_pval)
                    ph_df['p_FDR_corrected'] = ph_df['p_FDR_corrected'].apply(format_pval)
                    
                    # Highlight significant rows using Pandas styling
                    def highlight_sig(row):
                        if row['Significant?'] == "⭐ Yes":
                            return ['background-color: rgba(46, 204, 113, 0.2)'] * len(row)
                        return [''] * len(row)

                    st.dataframe(ph_df.style.apply(highlight_sig, axis=1), width='stretch', hide_index=True)
                else:
                    st.info("Not enough data to run post-hoc comparisons.")

    # --- TAB 6: RADAR PLOTS (Previously Tab 5) ---
    with tab6:
        st.subheader("Multivariate Radar Plot Analysis")
        
        if 'mapping_df' not in st.session_state:
            st.warning("⚠️ Please go to the 'Experimental Groups Setup' tab and extract variables first.")
        else:
            radar_sheet = st.selectbox("Select Statistic (Sheet) for Radar Data:", sheet_names, key="radar_sheet")
            df_radar = data_dict[radar_sheet]
            radar_num_cols = [col for col in df_radar.columns if col != 'Ids']
            
            st.markdown("Select at least 3 measurements to form a valid radar chart.")
            default_radar_metrics = radar_num_cols[:4] if len(radar_num_cols) >= 4 else radar_num_cols
            radar_metrics = st.multiselect(
                "Select Measurements:", 
                radar_num_cols, 
                default=default_radar_metrics,
                key="radar_metrics_select"
            )
            
            all_groups = st.session_state.mapping_df['Group'].unique()
            all_groups = sorted([g for g in all_groups if g != "Unknown"])
            all_timepoints = sorted(st.session_state.mapping_df['Timepoint_Weeks'].dropna().unique())
            
            col_rg, col_rt = st.columns(2)
            with col_rg:
                radar_groups = st.multiselect(
                    "Select Groups to Display:", 
                    all_groups, 
                    default=all_groups,
                    key="radar_groups" 
                )
            with col_rt:
                radar_tp = st.selectbox(
                    "Select a single Timepoint (Weeks):", 
                    all_timepoints,
                    key="radar_timepoint" 
                )
            
            tooltip_text = (
                "Highly recommended! Since angles and distances use different scales, raw values skew the plot. Measurements with larger means will also dominate the shape, making it hard to compare groups across metrics."
                "Proportional normalization divides each metric by its highest group mean. The highest group reaches the outer edge (1.0), "
                "and other groups are plotted proportionally (e.g., 0.85). This preserves the true ratios between your groups!"
            )
            normalize_radar = st.checkbox("Normalize Data (Proportional to Maximum)", value=True, help=tooltip_text)

            if st.button("Generate Radar Plot", type="primary", key="generate_radar_btn"):
                if len(radar_metrics) < 3:
                    st.error("Please select at least 3 metrics for a valid radar plot.")
                elif not radar_groups:
                    st.error("Please select at least one group.")
                else:
                    mapping_df = st.session_state.mapping_df.copy()
                    if st.session_state.get('exclude_subjects_ui'):
                        mapping_df = mapping_df[~mapping_df['Subject_ID'].isin(st.session_state.exclude_subjects_ui)]
                    mapping_radar = mapping_df[(mapping_df['Group'].isin(radar_groups)) & (mapping_df['Timepoint_Weeks'] == radar_tp)]
                    
                    if mapping_radar.empty:
                        st.warning(f"No valid group mappings found for timepoint {radar_tp} Weeks.")
                        st.stop()

                    merged_r = pd.merge(df_radar[['Ids'] + radar_metrics], mapping_radar, on='Ids')
                    for m in radar_metrics:
                        merged_r[m] = pd.to_numeric(merged_r[m], errors='coerce')
                    merged_r = merged_r.dropna(subset=radar_metrics)
                    
                    if merged_r.empty:
                        st.warning("No data found for the selected metrics, timepoint, and groups.")
                    else:
                        agg_r = merged_r.groupby('Group')[radar_metrics].mean().reset_index()
                        
                        if normalize_radar:
                            for m in radar_metrics:
                                max_val = agg_r[m].max()
                                if max_val != 0 and pd.notna(max_val):
                                    agg_r[m] = agg_r[m] / max_val 
                                else:
                                    agg_r[m] = 0.0

                        melted_r = pd.melt(
                            agg_r, 
                            id_vars=['Group'], 
                            value_vars=radar_metrics, 
                            var_name='Measurement', 
                            value_name='Value'
                        )
                        
                        dfs_to_concat = []
                        for group in radar_groups:
                            group_data = melted_r[melted_r['Group'] == group]
                            if not group_data.empty:
                                closed_loop = pd.concat([group_data, group_data.iloc[[0]]])
                                dfs_to_concat.append(closed_loop)
                        
                        if not dfs_to_concat:
                            st.warning("Could not build plot data.")
                            st.stop()

                        melted_r_closed = pd.concat(dfs_to_concat)
                        groups_str = " vs. ".join(radar_groups)
                        
                        fig_radar = px.line_polar(
                            melted_r_closed, 
                            r='Value', 
                            theta='Measurement', 
                            color='Group', 
                            line_close=True,
                            color_discrete_map=color_map
                        )
                        fig_radar.update_traces(fill='toself', opacity=0.3)
                        
                        polar_config = dict(
                            angularaxis=dict(
                                tickfont=dict(color="black", size=12) 
                            ),
                            radialaxis=dict(
                                tickfont=dict(color="black"),
                                gridcolor="lightgrey", 
                                visible=True
                            )
                        )
                        
                        if normalize_radar:
                            polar_config['radialaxis']['range'] = [0, 1]
                            
                        fig_radar.update_layout(
                            paper_bgcolor="white", 
                            plot_bgcolor="white",
                            polar=polar_config,
                            title=dict(
                                text=f"Kinematic Profile at {radar_tp} Weeks {'(Normalized ' + radar_sheet + ')' if normalize_radar else '(Raw Values ' + radar_sheet + ')'}<br><sup style='color: dimgrey;'>{groups_str}</sup>",
                                font=dict(color="black", size=18)
                            ),
                            legend=dict(
                                title=dict(text="Group", font=dict(color="black", size=14, weight="bold")),
                                font=dict(color="black", size=12)
                            )
                        )
                        
                        st.plotly_chart(fig_radar, width='stretch')
            st.markdown("---")
            st.markdown("##### ❗Important Note:")
            st.markdown("Every time any color, group, timepoint, or metric selection is changed, your current radar plot generated will disappear and you will need to generate the radar plot again using the **Generate Radar Plot** button to update the visualization. This ensures that the plot accurately reflects your current selections and allows you to explore different combinations of metrics and groups effectively.", text_alignment="justify")

else:
    st.info("Please upload your Excel, HDF5, or Parquet file to get started.")