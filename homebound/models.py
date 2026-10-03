"""
Design matrices, weighted least squares, HC1 and successive-difference-replication (SDR) variances.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .controls import CONTROLS

FIRST_YEAR = 2003
SDR_FACTOR = 4 / 160  # BLS ATUS User's Guide: sum of squared replicate deviations x 4/160


def design(d: pd.DataFrame, controls: dict = CONTROLS, extra: pd.DataFrame | None = None) -> pd.DataFrame:
    """Year dummies (2003 omitted) + categorical controls with explicit reference levels + optional
    numeric columns. No linear trend; no interactions unless supplied in `extra`."""
    years = sorted(d["YEAR"].unique())
    assert years[0] == FIRST_YEAR
    parts = [pd.Series(1.0, index=d.index, name="const"),
             pd.get_dummies(pd.Categorical(d["YEAR"], categories=years), prefix="year",
                            drop_first=True, dtype=float).set_index(d.index)]
    for col, ref in controls.items():
        levels = [ref] + sorted([x for x in d[col].unique() if x != ref], key=str)
        parts.append(pd.get_dummies(pd.Categorical(d[col], categories=levels), prefix=col,
                                    drop_first=True, dtype=float).set_index(d.index))
    if extra is not None:
        parts.append(extra)
    X = pd.concat(parts, axis=1)
    return X.loc[:, X.abs().sum() > 0]  # drop all-zero dummies (e.g., an unused category in a subgroup)


def wls(X: pd.DataFrame, Y: pd.DataFrame, w: np.ndarray, R: np.ndarray | None = None):
    """Fit every column of Y on X with weights w. Returns (results, HC1 covariances), where results maps
    outcome -> DataFrame(coef, se_hc1[, se_sdr]). If R (n x 160 replicate weights) is given, the full
    regression is refit with each replicate weight and SDR standard errors are added."""
    Xa, Ya = X.to_numpy(float), Y.to_numpy(float)
    n, p = Xa.shape
    XtW = (Xa * w[:, None]).T
    A = XtW @ Xa
    if np.linalg.matrix_rank(A) < p:
        raise np.linalg.LinAlgError("design is rank deficient")
    Ainv = np.linalg.inv(A)
    B = Ainv @ (XtW @ Ya)
    E = Ya - Xa @ B
    out, covs = {}, {}
    for k, name in enumerate(Y.columns):
        S = Xa * (w * E[:, k])[:, None]
        V = Ainv @ (S.T @ S) @ Ainv * n / (n - p)  # HC1 (= Stata regress [aw], robust)
        covs[name] = pd.DataFrame(V, index=X.columns, columns=X.columns)
        out[name] = pd.DataFrame({"coef": B[:, k], "se_hc1": np.sqrt(np.diag(V))}, index=X.columns)
    if R is not None:
        dev2 = np.zeros_like(B)
        for r in range(R.shape[1]):
            XtWr = (Xa * R[:, r][:, None]).T
            dev2 += (np.linalg.solve(XtWr @ Xa, XtWr @ Ya) - B) ** 2
        se = np.sqrt(SDR_FACTOR * dev2)
        for k, name in enumerate(Y.columns):
            out[name]["se_sdr"] = se[:, k]
    return out, covs


def year_rows(res: pd.DataFrame, d: pd.DataFrame, outcome: pd.Series, chart: str, model: str,
              method: str) -> pd.DataFrame:
    """Year contrasts vs 2003 (2003 = 0 by definition, no interval) with 95% CIs."""
    rows = []
    for yr in sorted(d["YEAR"].unique()):
        sub = d["YEAR"] == yr
        wm = np.average(outcome[sub], weights=d.loc[sub, "WEIGHT"])
        if yr == FIRST_YEAR:
            est, s_h, s_s = 0.0, np.nan, np.nan
        else:
            r = res.loc[f"year_{yr}"]
            est, s_h, s_s = r["coef"], r["se_hc1"], r.get("se_sdr", np.nan)
        se = s_s if method == "SDR" else s_h
        ref = yr == FIRST_YEAR
        rows.append(dict(chart=chart, model=model, year=int(yr), estimate=est, standard_error=se,
                         ci95_low=np.nan if ref else est - 1.96 * se,
                         ci95_high=np.nan if ref else est + 1.96 * se,
                         interval_method="reference (0 by definition)" if ref else method,
                         se_hc1=s_h, se_sdr=s_s, n_unweighted=int(sub.sum()), weighted_mean_outcome=wm))
    return pd.DataFrame(rows)


# ---- Chart 3 work-pattern terms ----------------------------------------------------------------
PATTERNS = ["No job work", "Away only", "Home only", "Both home and away"]
W_KNOTS, WH_KNOTS, TRAVEL_KNOTS = (4, 8, 10), (2, 6), (1, 2)  # hours, linear-spline knots


def work_pattern(d: pd.DataFrame, W="W", WH="WH", WA="WA", WU="WU") -> pd.Series:
    away = d[WA] + d[WU]  # the very rare unknown-location work is grouped with away
    return pd.Series(np.select([d[W] == 0, (d[WH] > 0) & (away > 0), d[WH] > 0],
                               ["No job work", "Both home and away", "Home only"], "Away only"), index=d.index)


def pattern_dummies(d: pd.DataFrame, **kw) -> pd.DataFrame:
    pat = pd.Categorical(work_pattern(d, **kw), categories=PATTERNS)
    return pd.get_dummies(pat, prefix="pattern", drop_first=True, dtype=float).set_index(d.index)


def work_terms(d: pd.DataFrame, flexible: bool, W="W", WH="WH", WA="WA", WU="WU") -> pd.DataFrame:
    """Linear W and WH hours (diagnostic) or the main flexible terms: work-pattern dummies plus
    linear splines in job-work hours (knots 4, 8, 10) and at-home job-work hours (knots 2, 6)."""
    w, wh = d[W] / 60, d[WH] / 60
    cols = {"W_hours": w, "WH_hours": wh}
    if not flexible:
        return pd.DataFrame(cols, index=d.index)
    for k in W_KNOTS:
        cols[f"W_hours_gt{k}"] = (w - k).clip(lower=0)
    for k in WH_KNOTS:
        cols[f"WH_hours_gt{k}"] = (wh - k).clip(lower=0)
    return pd.concat([pd.DataFrame(cols, index=d.index), pattern_dummies(d, W=W, WH=WH, WA=WA, WU=WU)], axis=1)


def travel_terms(d: pd.DataFrame, col: str) -> pd.DataFrame:
    h = d[col] / 60
    cols = {f"{col}_hours": h}
    for k in TRAVEL_KNOTS:
        cols[f"{col}_hours_gt{k}"] = (h - k).clip(lower=0)
    return pd.DataFrame(cols, index=d.index)


def rcs_basis(x: pd.Series, knots, name: str) -> pd.DataFrame:
    """Restricted (natural) cubic spline basis (Harrell): x plus k-2 nonlinear terms, linear in both tails."""
    t = np.asarray(knots, float)
    k = len(t)
    xv = x.to_numpy(float)
    cols = {name: xv}
    norm = (t[-1] - t[0]) ** 2

    def p3(z):
        return np.clip(z, 0, None) ** 3

    for j in range(k - 2):
        cols[f"{name}_rcs{j + 1}"] = (p3(xv - t[j])
                                      - p3(xv - t[k - 2]) * (t[k - 1] - t[j]) / (t[k - 1] - t[k - 2])
                                      + p3(xv - t[k - 1]) * (t[k - 2] - t[j]) / (t[k - 1] - t[k - 2])) / norm
    return pd.DataFrame(cols, index=x.index)


def knots_for(s: pd.Series, q) -> np.ndarray:
    """Spline knots at percentiles of the positive values."""
    kn = np.unique(np.round(s[s > 0].quantile(list(q)).to_numpy(), 4))
    assert len(kn) == len(q), f"duplicate knots: {kn}"
    return kn
