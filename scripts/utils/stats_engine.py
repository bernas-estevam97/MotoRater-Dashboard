"""
Statistical engine for the Kinematics Longitudinal Analyzer.

Pure pandas / scipy / statsmodels / pingouin code (no Streamlit calls), so the
interactive page, the Streamlit cache and the parallel batch exporter all run
exactly the same analysis.

Workflow (mirrors GraphPad Prism):
    1. check_assumptions(df)            -> normality, variances, balance, sphericity
    2. recommend(assumptions)           -> suggested test + post-hoc
    3. user picks test / post-hoc / correction (or keeps the recommendation)
    4. assess_fit(test, posthoc, ...)   -> warnings when the choice does not fit the data
    5. run_analysis(df, ...)            -> omnibus table, multiple comparisons, methods text

Input frame columns: 'Subject_ID', 'Group', 'Timepoint Weeks', '_metric_'
(one row per subject x timepoint, trials already averaged).
"""

import itertools
import warnings

import numpy as np
import pandas as pd
import pingouin as pg
import scipy.stats as stats
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.stats.multitest import multipletests

TP, GRP, SUBJ, Y = 'Timepoint Weeks', 'Group', 'Subject_ID', '_metric_'

# key -> (label, design, parametric). design: 'two' = 2 groups per timepoint,
# 'multi' = 3+ groups per timepoint, 'long' = repeated-measures model over all timepoints.
TESTS = {
    'welch_t': ("Welch's unpaired t-test", 'two', True),
    'student_t': ("Unpaired t-test (equal variances)", 'two', True),
    'mwu': ("Mann-Whitney U test", 'two', False),
    'anova1': ("Ordinary one-way ANOVA", 'multi', True),
    'welch_anova': ("Welch's one-way ANOVA", 'multi', True),
    'kruskal': ("Kruskal-Wallis test", 'multi', False),
    'mixed_anova': ("Two-way repeated-measures ANOVA (mixed design)", 'long', True),
    'lmm': ("Mixed-effects model (REML)", 'long', True),
    'gee': ("Generalized estimating equations (GEE)", 'long', False),
}

POSTHOCS = {
    'model': "Model-based group contrasts at each timepoint",
    'direct': "Direct two-group comparison",
    'tukey': "Tukey's HSD",
    'games_howell': "Games-Howell",
    'dunn': "Dunn's test",
    'pairwise_t': "Pairwise unpaired t-tests",
    'pairwise_welch': "Pairwise Welch t-tests",
    'pairwise_mwu': "Pairwise Mann-Whitney U tests",
}

# Post-hocs that already control the family-wise error within each timepoint.
SELF_ADJUSTED = {'tukey', 'games_howell'}

# label -> statsmodels.multipletests method (None = no correction, Fisher's LSD style)
CORRECTIONS = {
    "Holm (step-down)": 'holm',
    "Šídák": 'sidak',
    "Holm-Šídák": 'holm-sidak',
    "Bonferroni": 'bonferroni',
    "Benjamini-Hochberg (FDR)": 'fdr_bh',
    "Two-stage step-up, Benjamini-Krieger-Yekutieli (FDR)": 'fdr_tsbky',
    "None (uncorrected, Fisher's LSD)": None,
}
DEFAULT_CORRECTION = "Holm (step-down)"

# Below this many subjects GEE uses Mancl-DeRouen bias-reduced sandwich standard errors.
GEE_SMALL_N = 40
GEE_FAMILIES = ['auto', 'gaussian', 'gamma', 'poisson']
GEE_COVS = ['auto', 'autoregressive', 'exchangeable', 'independence']

_NONPARAM_ALT = {'welch_t': 'mwu', 'student_t': 'mwu', 'anova1': 'kruskal', 'welch_anova': 'kruskal',
                 'mixed_anova': 'gee', 'lmm': 'gee'}
_PARAM_ALT = {'mwu': 'welch_t', 'kruskal': 'anova1'}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def p_to_stars(p) -> str:
    """GraphPad Prism style significance summary."""
    if p is None or pd.isna(p):
        return ""
    if p < 0.0001:
        return "****"
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return "ns"


def fmt_p(p) -> str:
    if p is None or pd.isna(p):
        return "n/a"
    return "<0.0001" if p < 0.0001 else f"{p:.4f}"


def label(test: str) -> str:
    return TESTS[test][0]


def available_tests(n_groups: int, n_timepoints: int) -> list:
    """Tests valid for the current design, in display order."""
    cross = ['welch_t', 'student_t', 'mwu'] if n_groups == 2 else ['anova1', 'welch_anova', 'kruskal']
    if n_timepoints > 1:
        return ['mixed_anova', 'lmm', 'gee'] + cross
    return cross


def available_posthocs(test: str) -> list:
    design = TESTS[test][1]
    if design == 'long':
        return ['model']
    if design == 'two':
        return ['direct']
    return {'anova1': ['tukey', 'pairwise_t', 'pairwise_welch'],
            'welch_anova': ['games_howell', 'pairwise_welch'],
            'kruskal': ['dunn', 'pairwise_mwu']}[test]


def uses_correction(posthoc: str) -> bool:
    return posthoc not in SELF_ADJUSTED


def _prep(df: pd.DataFrame) -> pd.DataFrame:
    out = df[[SUBJ, GRP, TP, Y]].dropna().copy()
    out[Y] = out[Y].astype(float)
    out[GRP] = out[GRP].astype(str)
    out['_time_'] = out[TP].astype(str)
    out['_group_'] = out[GRP].astype(str)
    return out.sort_values([SUBJ, TP]).reset_index(drop=True)


def _adjust(pvals, method):
    """Multiplicity correction over the non-NaN p-values (method None = uncorrected)."""
    p = np.asarray(pvals, dtype=float)
    out = p.copy()
    ok = ~np.isnan(p)
    if method and ok.sum() > 1:
        out[ok] = multipletests(p[ok], method=method)[1]
    return out


def _fit_mixedlm(df, formula):
    """Fit a random-intercept LMM, trying several optimizers (lbfgs alone is often singular)."""
    model = smf.mixedlm(formula, df, groups=SUBJ)
    last_err, fallback = None, None
    for method in ('lbfgs', 'bfgs', 'powell', 'nm'):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                res = model.fit(reml=True, method=method)
            if res.converged:
                return res
            fallback = fallback or res
        except Exception as e:  # singular matrices etc. -> try next optimizer
            last_err = e
    if fallback is not None:
        return fallback
    raise RuntimeError(f"Mixed-effects model failed to fit: {last_err}")


# ---------------------------------------------------------------------------
# 1. Assumptions
# ---------------------------------------------------------------------------
def check_assumptions(df: pd.DataFrame, alpha: float = 0.05) -> dict:
    d = _prep(df)
    # A categorical 'Group' keeps the user's order (first group = reference, Group A).
    present = set(d[GRP])
    groups = ([g for g in df[GRP].cat.categories if g in present]
              if isinstance(df[GRP].dtype, pd.CategoricalDtype) else sorted(present))
    tps = sorted(d[TP].unique())
    n_per_group = d.groupby(GRP)[SUBJ].nunique().to_dict()
    a = {
        'groups': groups, 'timepoints': tps,
        'n_groups': len(groups), 'n_timepoints': len(tps),
        'n_obs': len(d), 'n_subjects': d[SUBJ].nunique(),
        'n_per_group': n_per_group, 'min_n': min(n_per_group.values()) if n_per_group else 0,
    }

    # Overlapping tags (e.g. 'Transgenic' and 'TG Female') put one subject in several groups.
    per_subj = d.groupby(SUBJ)[GRP].nunique()
    a['overlapping_subjects'] = sorted(per_subj[per_subj > 1].index)

    # Residual normality: residuals of the model that matches the design.
    resid = None
    if len(tps) > 1 and a['min_n'] >= 2:
        try:
            resid = _fit_mixedlm(d, "_metric_ ~ C(_time_) * C(_group_)").resid
        except Exception:
            resid = None
    if resid is None and len(d) > len(groups):
        formula = "_metric_ ~ C(_time_) * C(_group_)" if len(tps) > 1 else "_metric_ ~ C(_group_)"
        resid = smf.ols(formula, data=d).fit().resid

    a['normality_test'], a['normality_p'], a['skew'] = None, np.nan, np.nan
    n_res = 0 if resid is None else len(resid)
    if n_res >= 3:
        # Shapiro-Wilk has better power for small samples; D'Agostino-Pearson
        # (Prism's default) needs n >= 20 to be reliable.
        method = 'shapiro' if n_res < 20 else 'normaltest'
        a['normality_test'] = "Shapiro-Wilk" if method == 'shapiro' else "D'Agostino-Pearson"
        a['normality_p'] = float(pg.normality(resid, method=method)['pval'].iloc[0])
        a['skew'] = float(stats.skew(resid))
    a['n_residuals'] = n_res
    a['small_sample'] = n_res < 20
    a['clt_safe'] = n_res >= 100 and abs(a['skew']) < 1.0
    a['normal'] = bool(np.isnan(a['normality_p']) or a['normality_p'] >= alpha or a['clt_safe'])

    # Homogeneity of variances (Levene) at each timepoint; report the worst one.
    lev = []
    for tp in tps:
        sub = d[d[TP] == tp]
        if (sub.groupby(GRP)[Y].count() >= 2).sum() >= 2:
            try:
                lev.append(float(pg.homoscedasticity(sub, dv=Y, group=GRP)['pval'].iloc[0]))
            except Exception:
                pass
    a['levene_p'] = min(lev) if lev else np.nan
    a['equal_var'] = bool(np.isnan(a['levene_p']) or a['levene_p'] >= alpha)

    # Design balance (every subject measured at every selected timepoint).
    subj_tps = d.groupby([SUBJ, GRP])[TP].agg(list).reset_index()
    subj_tps['Missing timepoints'] = subj_tps[TP].apply(lambda have: [t for t in tps if t not in have])
    incomplete = subj_tps[subj_tps['Missing timepoints'].str.len() > 0]
    a['balanced'] = incomplete.empty
    a['incomplete'] = incomplete[[GRP, SUBJ, 'Missing timepoints']].assign(
        **{'Missing timepoints': lambda x: x['Missing timepoints'].apply(lambda v: ", ".join(map(str, v)))}
    ).sort_values([GRP, SUBJ]).reset_index(drop=True)

    # Sphericity (only meaningful with 3+ repeated levels and complete data).
    a['sphericity_p'], a['sphericity'] = np.nan, True
    if len(tps) >= 3:
        complete = d[~d[SUBJ].isin(incomplete[SUBJ])]
        try:
            sph = pg.sphericity(complete, dv=Y, within=TP, subject=SUBJ)
            a['sphericity_p'], a['sphericity'] = float(sph.pval), bool(sph.spher)
        except Exception:
            pass

    # Raw data shape (drives the GEE family when set to auto).
    y = d[Y]
    a['is_count'] = bool(len(y) and (y >= 0).all() and np.allclose(y % 1, 0))
    a['strictly_positive'] = bool(len(y) and (y > 0).all())
    a['raw_skew'] = float(stats.skew(y)) if len(y) > 2 else 0.0
    return a


# ---------------------------------------------------------------------------
# 2. Recommendation & 3. fit warnings
# ---------------------------------------------------------------------------
def recommend(a: dict) -> tuple:
    """Return (test, posthoc, reason) following the original automatic decision tree."""
    normal, eq = a['normal'], a['equal_var']
    if a['n_timepoints'] > 1 and a['min_n'] >= 3:
        if normal and a['balanced']:
            return 'mixed_anova', 'model', "residuals are normal and every subject has every timepoint"
        if normal:
            return 'lmm', 'model', "residuals are normal but some subjects miss timepoints (keeps all data)"
        return 'gee', 'model', "residuals are not normally distributed"
    if a['n_groups'] == 2:
        rec = (('welch_t', 'direct', "residuals are normal (Welch's is robust to unequal variances)") if normal
               else ('mwu', 'direct', "residuals are not normally distributed"))
    elif normal and eq:
        rec = 'anova1', 'tukey', "residuals are normal and variances are equal"
    elif normal:
        rec = 'welch_anova', 'games_howell', "residuals are normal but variances are unequal"
    else:
        rec = 'kruskal', 'dunn', "residuals are not normally distributed"
    if a['n_timepoints'] > 1:
        # Repeated-measures models need 3+ subjects per group (see assess_fit).
        rec = rec[:2] + (rec[2] + "; a group has fewer than 3 subjects, too few for a repeated-measures model, "
                                  "so each timepoint is tested separately",)
    return rec


def assess_fit(test: str, posthoc: str, correction: str, a: dict) -> list:
    """Return [(level, message)] explaining where the chosen analysis may not fit the data.
    level is 'error' (cannot run), 'warning' (assumption violated) or 'info'."""
    out = []
    name, design, parametric = TESTS[test]
    np_ = a['normality_p']

    if a['overlapping_subjects']:
        shown = ", ".join(map(str, a['overlapping_subjects'][:5]))
        return [('error', f"{len(a['overlapping_subjects'])} subject(s) belong to more than one selected group "
                          f"({shown}...). Groups must not overlap — e.g. do not combine 'Transgenic' with "
                          "'TG Female'.")]
    if a['min_n'] < 2:
        return [('error', f"At least one group has fewer than 2 subjects (min n = {a['min_n']}). No test can be run.")]
    if design == 'long' and a['min_n'] < 3:
        out.append(('error', f"Repeated-measures models need at least 3 subjects per group (min n = {a['min_n']})."))

    if parametric and not a['normal']:
        alt = _NONPARAM_ALT.get(test)
        out.append(('warning', f"Residuals are not normally distributed ({a['normality_test']} p = {fmt_p(np_)}, "
                               f"skew = {a['skew']:.2f}). {name} assumes normality, so p-values may be unreliable."
                               + (f" Consider **{label(alt)}**." if alt else "")))
    if not parametric and test != 'gee' and a['normal']:
        out.append(('info', f"Residuals look normal; a non-parametric test has less power. "
                            f"**{label(_PARAM_ALT[test])}** would be more sensitive."))
    if test == 'gee' and a['normal']:
        out.append(('info', "Residuals look normal; a mixed-effects model or RM ANOVA usually has more power than GEE."))
    if test == 'gee' and a['n_subjects'] < GEE_SMALL_N:
        out.append(('info', f"With only {a['n_subjects']} subjects, GEE uses Mancl-DeRouen bias-reduced sandwich "
                            "standard errors (plain sandwich errors are too small in small samples). P-values can "
                            "still be slightly optimistic with very few subjects."))

    if not a['equal_var']:
        if test in ('student_t', 'anova1'):
            alt = 'welch_t' if test == 'student_t' else 'welch_anova'
            out.append(('warning', f"Group variances differ (Levene p = {fmt_p(a['levene_p'])}). {name} assumes equal "
                                   f"variances; consider **{label(alt)}**."))
        if posthoc in ('tukey', 'pairwise_t'):
            out.append(('warning', f"Group variances differ (Levene p = {fmt_p(a['levene_p'])}); "
                                   f"{POSTHOCS[posthoc]} assumes equal variances. Games-Howell / Welch tests do not."))

    if test == 'mixed_anova':
        if not a['balanced']:
            n_inc = len(a['incomplete'])
            out.append(('warning', f"{n_inc} subject(s) miss at least one timepoint. RM ANOVA removes these subjects "
                                   "completely (listwise deletion), which loses power and can cause survivor bias. "
                                   "A **Mixed-effects model** uses all available data."))
        if not a['sphericity']:
            out.append(('info', f"Sphericity violated (Mauchly p = {fmt_p(a['sphericity_p'])}); the "
                                "Greenhouse-Geisser corrected p-value is reported."))

    if design != 'long' and a['n_timepoints'] > 1:
        out.append(('warning', f"{name} is run separately at each timepoint and ignores that the same subjects are "
                               "measured repeatedly. A repeated-measures model accounts for this correlation."))

    if a['small_sample'] and a['normality_test']:
        out.append(('info', f"Small sample (n = {a['n_residuals']} residuals): the normality test has low power, "
                            "so a 'normal' result is weak evidence."))
    if uses_correction(posthoc) and CORRECTIONS.get(correction) is None and _n_comparisons(test, a) > 1:
        out.append(('warning', "No multiple-comparison correction: with several comparisons the chance of at least "
                               "one false positive is well above alpha."))
    return out


def _n_comparisons(test, a):
    pairs = a['n_groups'] * (a['n_groups'] - 1) // 2
    return pairs * a['n_timepoints']


# ---------------------------------------------------------------------------
# 4. Analysis
# ---------------------------------------------------------------------------
_TERM_NAMES = {'C(_time_, Sum)': 'Time', 'C(_group_, Sum)': 'Group',
               'C(_time_, Sum):C(_group_, Sum)': 'Time × Group'}
_LONG_FORMULA = "_metric_ ~ C(_time_, Sum) * C(_group_, Sum)"


def _wald_table(res):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        w = res.wald_test_terms(scalar=True).summary_frame()
    w = w.drop(index='Intercept', errors='ignore')
    return pd.DataFrame({
        'Source': [_TERM_NAMES.get(i, i) for i in w.index],
        'Wald χ²': w['chi2'].astype(float).values,
        'df': w['df constraint'].astype(int).values,
        'p': w['P>chi2'].astype(float).values,
    })


def _model_contrasts(res, d, groups, tps):
    """B - A difference between every pair of groups at every timepoint, using the
    fitted model's covariance (pooled repeated-measures error, as Prism does)."""
    # The fixed-effect design row depends only on (time, group), so take it from any
    # fitted row in that cell. Avoids patsy's design_info (gone in statsmodels >= 0.15).
    exog = np.asarray(res.model.exog)
    k = getattr(res.model, 'k_fe', exog.shape[1])
    cell_row = {cell: exog[i, :k] for i, cell in enumerate(zip(d['_time_'], d['_group_']))}
    rows = []
    for tp in tps:
        for ga, gb in itertools.combinations(groups, 2):
            row = {TP: tp, 'Group A': ga, 'Group B': gb, 'Difference (B − A)': np.nan, 'SE': np.nan, 'p_unc': np.nan}
            a_key, b_key = (str(tp), ga), (str(tp), gb)
            if a_key in cell_row and b_key in cell_row:
                try:
                    L = (cell_row[b_key] - cell_row[a_key]).reshape(1, -1)
                    tt = res.t_test(L)
                    row.update({'Difference (B − A)': float(np.ravel(tt.effect)[0]),
                                'SE': float(np.ravel(tt.sd)[0]),
                                'p_unc': float(np.ravel(tt.pvalue)[0])})
                except Exception:
                    pass
            rows.append(row)
    return pd.DataFrame(rows)


def _gee_family(choice, a, notes):
    if choice == 'auto':
        if a['is_count']:
            choice = 'poisson'
        elif a['strictly_positive'] and a['raw_skew'] > 1.0:
            choice = 'gamma'
        else:
            choice = 'gaussian'
        notes.append(('info', f"GEE family chosen automatically: **{choice.title()}**."))
    if choice in ('gamma', 'poisson'):
        notes.append(('info', "With a log link, differences are on the log scale (exp(diff) = ratio B/A)."))
    fam = {'gaussian': sm.families.Gaussian(),
           'gamma': sm.families.Gamma(link=sm.families.links.Log()),
           'poisson': sm.families.Poisson()}[choice]
    return fam, choice


class _Autoregressive(sm.cov_struct.Autoregressive):
    """statsmodels sets dep_params to int 0 when the lag-1 correlation is ~0, which then
    crashes for subjects with exactly 2 observations (int matrix divided in place)."""
    def update(self, params):
        super().update(params)
        self.dep_params = float(self.dep_params)


def _fit_gee(d, a, family, cov, notes):
    fam, fam_name = _gee_family(family, a, notes)
    tp_index = d[TP].map({t: i for i, t in enumerate(a['timepoints'])}).values
    covs = {'autoregressive': _Autoregressive, 'exchangeable': sm.cov_struct.Exchangeable,
            'independence': sm.cov_struct.Independence}
    # AR(1) cannot be estimated when the correlation is ~1, so it falls back to exchangeable.
    order = ['autoregressive', 'exchangeable'] if cov in ('auto', 'autoregressive') else [cov]
    cov_type = 'bias_reduced' if d[SUBJ].nunique() < GEE_SMALL_N else 'robust'
    err = None
    for c in order:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                res = smf.gee(_LONG_FORMULA, groups=d[SUBJ], data=d, time=tp_index,
                              cov_struct=covs[c](), family=fam).fit(cov_type=cov_type)
            if c != order[0]:
                notes.append(('warning', "Autoregressive working correlation failed to fit; fell back to "
                                         "**Exchangeable**."))
            return res, fam_name, c, cov_type
        except Exception as e:
            err = e
    raise RuntimeError(f"GEE failed to fit: {err}")


def _dunn(sub, groups):
    """Dunn's test (tie-corrected) on ranks pooled over the selected groups."""
    ranks = stats.rankdata(sub[Y])
    n = len(ranks)
    _, tie_counts = np.unique(ranks, return_counts=True)
    var = n * (n + 1) / 12 - (tie_counts ** 3 - tie_counts).sum() / (12 * (n - 1))
    r = pd.Series(ranks, index=sub.index).groupby(sub[GRP])
    mean_r, cnt = r.mean(), r.count()
    rows = []
    for ga, gb in itertools.combinations(groups, 2):
        if ga in cnt and gb in cnt:
            z = (mean_r[gb] - mean_r[ga]) / np.sqrt(var * (1 / cnt[ga] + 1 / cnt[gb]))
            rows.append((ga, gb, z, 2 * stats.norm.sf(abs(z))))
    return rows


def _cross_sectional(d, test, posthoc, groups, tps):
    """Per-timepoint tests. Returns (omnibus_df or None, comparisons_df)."""
    omni, comps = [], []
    for tp in tps:
        sub = d[d[TP] == tp]
        by = {g: sub.loc[sub[GRP] == g, Y].values for g in groups}
        valid = [g for g in groups if len(by[g]) >= 2]
        mean = {g: by[g].mean() if len(by[g]) else np.nan for g in groups}

        if TESTS[test][1] == 'two':
            ga, gb = groups
            row = {TP: tp, 'Group A': ga, 'Group B': gb, 'Difference (B − A)': mean[gb] - mean[ga],
                   'Statistic': np.nan, 'p_unc': np.nan}
            if len(valid) == 2:
                if test == 'mwu':
                    r = stats.mannwhitneyu(by[gb], by[ga], alternative='two-sided')
                else:
                    r = stats.ttest_ind(by[gb], by[ga], equal_var=(test == 'student_t'))
                row.update({'Statistic': float(r.statistic), 'p_unc': float(r.pvalue)})
            comps.append(row)
            continue

        # 3+ groups: omnibus at this timepoint
        sub_v = sub[sub[GRP].isin(valid)]
        if len(valid) >= 2:
            try:
                if test == 'anova1':
                    o = pg.anova(sub_v, dv=Y, between=GRP)
                    omni.append({TP: tp, 'Statistic': 'F', 'Value': o['F'].iloc[0],
                                 'df': f"{o['ddof1'].iloc[0]:g}, {o['ddof2'].iloc[0]:g}", 'p': o['p_unc'].iloc[0]})
                elif test == 'welch_anova':
                    o = pg.welch_anova(sub_v, dv=Y, between=GRP)
                    omni.append({TP: tp, 'Statistic': 'F (Welch)', 'Value': o['F'].iloc[0],
                                 'df': f"{o['ddof1'].iloc[0]:g}, {o['ddof2'].iloc[0]:.2f}", 'p': o['p_unc'].iloc[0]})
                else:
                    o = pg.kruskal(sub_v, dv=Y, between=GRP)
                    omni.append({TP: tp, 'Statistic': 'H', 'Value': o['H'].iloc[0],
                                 'df': f"{o['ddof1'].iloc[0]:g}", 'p': o['p_unc'].iloc[0]})
            except Exception:
                pass

        # post-hoc at this timepoint
        if posthoc in SELF_ADJUSTED and len(valid) >= 2:
            fn = pg.pairwise_tukey if posthoc == 'tukey' else pg.pairwise_gameshowell
            pcol = 'p_tukey' if posthoc == 'tukey' else 'pval'
            try:
                for _, r in fn(sub_v, dv=Y, between=GRP).iterrows():
                    comps.append({TP: tp, 'Group A': r['A'], 'Group B': r['B'],
                                  'Difference (B − A)': -float(r['diff']), 'Statistic': float(r['T']),
                                  'p_unc': np.nan, 'p_corr': float(r[pcol])})
            except Exception:
                pass
        elif posthoc == 'dunn' and len(valid) >= 2:
            for ga, gb, z, p in _dunn(sub_v, valid):
                comps.append({TP: tp, 'Group A': ga, 'Group B': gb, 'Difference (B − A)': mean[gb] - mean[ga],
                              'Statistic': z, 'p_unc': p})
        else:
            for ga, gb in itertools.combinations(valid, 2):
                if posthoc == 'pairwise_mwu':
                    r = stats.mannwhitneyu(by[gb], by[ga], alternative='two-sided')
                else:
                    r = stats.ttest_ind(by[gb], by[ga], equal_var=(posthoc == 'pairwise_t'))
                comps.append({TP: tp, 'Group A': ga, 'Group B': gb, 'Difference (B − A)': mean[gb] - mean[ga],
                              'Statistic': float(r.statistic), 'p_unc': float(r.pvalue)})
    return (pd.DataFrame(omni) if omni else None), pd.DataFrame(comps)


def run_analysis(df: pd.DataFrame, test: str = 'auto', posthoc: str = 'auto',
                 correction: str = DEFAULT_CORRECTION, alpha: float = 0.05,
                 gee_family: str = 'auto', gee_cov: str = 'auto', metric_name: str = "the outcome",
                 assumptions: dict = None) -> dict:
    """Run the chosen analysis. 'auto' resolves to the recommended test / default post-hoc."""
    d = _prep(df)
    a = assumptions or check_assumptions(df, alpha)
    rec_test, rec_post, _ = recommend(a)
    if test == 'auto':
        test = rec_test
    if test not in available_tests(a['n_groups'], a['n_timepoints']):
        raise ValueError(f"{test} is not valid for {a['n_groups']} groups x {a['n_timepoints']} timepoints")
    if posthoc == 'auto' or posthoc not in available_posthocs(test):
        posthoc = rec_post if rec_test == test else available_posthocs(test)[0]

    notes = assess_fit(test, posthoc, correction, a)
    result = {'test': test, 'posthoc': posthoc, 'correction': correction, 'alpha': alpha,
              'assumptions': a, 'notes': notes, 'omnibus': None, 'comparisons': pd.DataFrame(),
              'error': None, 'details': {}}
    if any(level == 'error' for level, _ in notes):
        result['error'] = next(m for level, m in notes if level == 'error')
        return result

    groups, tps = a['groups'], a['timepoints']
    try:
        if test == 'mixed_anova':
            complete = d[~d[SUBJ].isin(a['incomplete'][SUBJ])]
            if complete[GRP].nunique() < a['n_groups']:
                raise RuntimeError("no group has complete data for every timepoint")
            aov = pg.mixed_anova(dv=Y, within=TP, between=GRP, subject=SUBJ, data=complete, correction=True)
            p = aov['p_unc'].astype(float).copy()
            if 'p_GG_corr' in aov.columns and not a['sphericity']:
                p = aov['p_GG_corr'].astype(float).fillna(p)
            result['omnibus'] = pd.DataFrame({
                'Source': aov['Source'].replace({TP: 'Time', 'Interaction': 'Time × Group'}).values,
                'F': aov['F'].astype(float).values,
                'df': [f"{a1:g}, {a2:g}" for a1, a2 in zip(aov['DF1'], aov['DF2'])],
                'p': p.values,
                'η²p': aov['np2'].astype(float).values,
            })
            res = _fit_mixedlm(complete, _LONG_FORMULA)
            comps = _model_contrasts(res, complete, groups, tps)
            result['details']['n_dropped'] = d[SUBJ].nunique() - complete[SUBJ].nunique()
        elif test == 'lmm':
            res = _fit_mixedlm(d, _LONG_FORMULA)
            result['omnibus'] = _wald_table(res)
            comps = _model_contrasts(res, d, groups, tps)
            result['details']['random_intercept_var'] = float(res.cov_re.iloc[0, 0])
        elif test == 'gee':
            res, fam, cov, cov_type = _fit_gee(d, a, gee_family, gee_cov, notes)
            result['omnibus'] = _wald_table(res)
            comps = _model_contrasts(res, d, groups, tps)
            result['details'].update({'family': fam, 'cov_struct': cov, 'cov_type': cov_type})
        else:
            result['omnibus'], comps = _cross_sectional(d, test, posthoc, groups, tps)
    except Exception as e:
        result['error'] = f"{label(test)} failed: {e}"
        return result

    if comps.empty:
        result['comparisons'] = comps
    else:
        if 'p_corr' not in comps.columns:
            comps['p_corr'] = np.nan
        need = comps['p_corr'].isna()
        method = CORRECTIONS.get(correction) if uses_correction(posthoc) else None
        comps.loc[need, 'p_corr'] = _adjust(comps.loc[need, 'p_unc'], method)
        comps['Summary'] = comps['p_corr'].apply(p_to_stars)
        comps['Significant'] = comps['p_corr'] < alpha
        result['comparisons'] = comps
    result['methods'] = methods_text(result, metric_name)
    return result


# ---------------------------------------------------------------------------
# 5. Methods paragraph
# ---------------------------------------------------------------------------
def methods_text(result: dict, metric_name: str = "the outcome") -> str:
    a, test, posthoc = result['assumptions'], result['test'], result['posthoc']
    corr = CORRECTIONS.get(result['correction']) if uses_correction(posthoc) else None
    parts = [f"Trials were averaged per subject and timepoint. Data are presented as mean ± SEM."]
    if a['normality_test']:
        parts.append(f"Normality of residuals was assessed with the {a['normality_test']} test.")
    if test == 'mixed_anova':
        parts.append(f"{metric_name} was analysed with a two-way repeated-measures (mixed-design) ANOVA with time as "
                     "within-subject and group as between-subject factor; the Greenhouse-Geisser correction was "
                     "applied when Mauchly's test indicated a violation of sphericity.")
    elif test == 'lmm':
        parts.append(f"{metric_name} was analysed with a linear mixed-effects model (REML) with time, group and their "
                     "interaction as fixed effects and a random intercept per subject, which retains subjects with "
                     "missing timepoints. Fixed effects were tested with Wald χ² tests.")
    elif test == 'gee':
        det = result['details']
        se_text = ("Mancl-DeRouen bias-reduced robust standard errors" if det.get('cov_type') == 'bias_reduced'
                   else "robust standard errors")
        parts.append(f"{metric_name} was analysed with generalized estimating equations ({det.get('family', '')} "
                     f"family, {det.get('cov_struct', '')} working correlation, {se_text}) with time, "
                     "group and their interaction as factors. Terms were tested with Wald χ² tests.")
    else:
        each = " at each timepoint separately" if a['n_timepoints'] > 1 else ""
        parts.append(f"Group differences in {metric_name} were tested{each} with the {label(test)}.")

    if posthoc == 'model':
        parts.append("Groups were compared at each timepoint with contrasts derived from the fitted model.")
    elif posthoc != 'direct':
        parts.append(f"Post-hoc comparisons used {POSTHOCS[posthoc]}.")
    if uses_correction(posthoc) and _n_comparisons(test, a) > 1:
        parts.append(f"P-values were adjusted for multiple comparisons with the {result['correction']} method."
                     if corr else "P-values were not adjusted for multiple comparisons.")
    parts.append(f"Statistical significance was set at α = {result['alpha']}.")
    return " ".join(parts)


if __name__ == "__main__":
    # Self-check: synthetic 3-group longitudinal design with a known group B effect.
    rng = np.random.default_rng(1)
    rows = []
    for g in ['A', 'B', 'C']:
        for s in range(8):
            u = rng.normal()
            for t in [4, 8, 12]:
                rows.append({SUBJ: f"{g}{s}", GRP: g, TP: t, Y: t + 3 * (g == 'B') + u + rng.normal()})
    df = pd.DataFrame(rows)
    a = check_assumptions(df)
    assert a['balanced'] and a['n_groups'] == 3
    for t in available_tests(3, 3):
        for ph in available_posthocs(t):
            r = run_analysis(df, t, ph)
            assert r['error'] is None, (t, ph, r['error'])
            c = r['comparisons']
            ab = c[(c['Group A'] == 'A') & (c['Group B'] == 'B')]
            assert (ab['p_corr'] < 0.05).all() and (ab['Difference (B − A)'] > 0).all(), (t, ph, ab)
    two = df[df[GRP] != 'C']
    for t in available_tests(2, 1):
        r = run_analysis(two[two[TP] == 4], t)
        assert r['error'] is None and len(r['comparisons']) == 1, (t, r['error'])
    # Unbalanced data: RM ANOVA must warn and drop, LMM keeps everyone.
    unb = df.drop(index=df[(df[SUBJ] == 'A0') & (df[TP] == 12)].index)
    a2 = check_assumptions(unb)
    assert not a2['balanced']
    assert any('listwise' in m for _, m in assess_fit('mixed_anova', 'model', DEFAULT_CORRECTION, a2))
    assert run_analysis(unb, 'mixed_anova')['details']['n_dropped'] == 1
    # GEE AR(1) with ~0 within-subject correlation and a 2-observation subject (statsmodels int bug).
    iid = unb.assign(**{Y: rng.normal(size=len(unb))})
    for cov in ('autoregressive', 'auto'):
        r = run_analysis(iid, 'gee', gee_cov=cov)
        assert r['error'] is None and r['details']['cov_struct'] == 'autoregressive', (cov, r['error'], r['details'])
    # Small-sample GEE (24 subjects): bias-reduced SEs, larger than plain sandwich SEs, and no warning.
    g = run_analysis(df, 'gee', gee_cov='exchangeable')
    assert g['details']['cov_type'] == 'bias_reduced' and 'Mancl' in g['methods']
    assert not any(lvl == 'warning' for lvl, _ in g['notes']), g['notes']
    plain = smf.gee(_LONG_FORMULA, groups=_prep(df)[SUBJ], data=_prep(df),
                    cov_struct=sm.cov_struct.Exchangeable()).fit()
    assert (_model_contrasts(plain, _prep(df), a['groups'], a['timepoints'])['SE'] < g['comparisons']['SE']).all()
    # 2 subjects per group over time: Auto falls back to per-timepoint tests instead of an error.
    tiny = df[df[SUBJ].str[1].isin(['0', '1'])]
    t_rec = recommend(check_assumptions(tiny))[0]
    assert TESTS[t_rec][1] != 'long' and run_analysis(tiny)['error'] is None, t_rec
    overl = pd.concat([df, df[df[GRP] == 'A'].assign(**{GRP: 'C'})])
    assert run_analysis(overl, 'lmm')['error'].startswith("8 subject(s)")
    assert p_to_stars(0.00001) == "****" and p_to_stars(0.2) == "ns"
    print("stats_engine self-check passed")
