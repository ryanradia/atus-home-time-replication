"""
Replication pipeline: time at home and job work, ATUS 2003-2025.

    python run_all.py [--data-dir data] [--home-def personalcare|sleep]

Reads an IPUMS ATUS hierarchical extract (see docs/ipums_extract.md), builds one record per respondent,
validates it, estimates the three charts and all sensitivity checks, and writes results/.
"""
from __future__ import annotations

import argparse
import platform
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from homebound import charts, data, models
from homebound.controls import CONTROLS, build_controls
from homebound.models import FIRST_YEAR, design, wls, year_rows, work_pattern, work_terms

ROOT = Path(__file__).resolve().parent
# Published benchmarks used only for the reproduction check (Sharkey 2024 and his replication log).
SHARKEY_LOG_MEANS = {2003: 991.9541, 2022: 1091.323}
SHARKEY_ANALYTIC_N_2003_2022 = 222_757
SHARKEY_PUBLISHED_2022 = 99.0
GAP_WINDOWS_MD = [(318, 509), (930, 1111)]  # Mar 18-May 9 (2020) and Sep 30-Nov 11 (2025), as month*100+day


class Tee:
    def __init__(self, path: Path):
        self.f = open(path, "w", encoding="utf-8")
        self.o = sys.stdout

    def write(self, s):
        self.o.write(s)
        self.f.write(s)

    def flush(self):
        self.o.flush()
        self.f.flush()


def section(title):
    print("\n" + "=" * 90 + f"\n{title}\n" + "=" * 90)


TESTED_PYTHON = "3.12.10"


def installed_versions() -> dict:
    """Python and installed versions of every package pinned in requirements.txt; warns on differences."""
    from importlib import metadata
    env = {"python": platform.python_version()}
    if env["python"] != TESTED_PYTHON:
        print(f"Note: results/ were produced with Python {TESTED_PYTHON}; running {env['python']}.")
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        line = line.split("#")[0].strip()
        if "==" not in line:
            continue
        name, pinned = line.split("==")
        try:
            got = metadata.version(name)
        except metadata.PackageNotFoundError:
            got = "not installed"
        env[name] = got
        if got != pinned:
            print(f"Note: {name} {got} installed; results/ were produced with {pinned}.")
    return env


def wavg(x, w):
    return float(np.average(x, weights=w))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(ROOT / "data"))
    ap.add_argument("--home-def", choices=["personalcare", "sleep"], default="personalcare",
                    help="personalcare = Sharkey's definition (main); sleep = home/yard + sleep only")
    args = ap.parse_args()
    home_def = args.home_def
    res_dir = ROOT / ("results" if home_def == "personalcare" else "results_home_sleep_only")
    build = ROOT / "build"
    res_dir.mkdir(exist_ok=True)
    build.mkdir(exist_ok=True)
    sys.stdout = Tee(build / f"run_log_{home_def}.txt")
    pd.set_option("display.width", 220, "display.max_columns", 40, "display.max_rows", 300)
    t0 = time.time()

    section("0. INPUTS")
    env = installed_versions()
    print(env)
    dat, xml = data.find_extract(Path(args.data_dir))
    meta = data.parse_ddi(xml)
    data.check_variables(meta)
    df, rep = data.load(dat, meta, build / "cache")
    print(f"Respondents parsed: {len(df):,} ({time.time() - t0:.0f}s)")

    # ------------------------------------------------------------------ 1. construction checks
    section("1. RESPONDENT-LEVEL CONSTRUCTION CHECKS")
    checks = {
        "one record per respondent (unique CASEID)": df["CASEID"].is_unique,
        "all records are ATUS respondents (LINENO = 1)": bool((df["LINENO"] == 1).all()),
        "every respondent has activity records": bool((df["n_act"] > 0).all()),
        "DURATION sums to 1,440 minutes for every diary": bool((df["dur_sum"] == 1440).all()),
        "sleep never has a recorded location (no double counting)":
            bool((df["H_sleep"] == df["home_where"] + df["sleep"]).all()),
        "Sharkey home = WHERE home + no-location personal care":
            bool((df["H_pc"] == df["home_where"] + df["pcare_noloc"]).all()),
        "W = WH + WA + WU": bool((df["W"] == df["WH"] + df["WA"] + df["WU"]).all()),
        "WH <= W": bool((df["WH"] <= df["W"]).all()),
        "all minute totals within 0-1,440":
            bool(df[["H_pc", "H_sleep", "W", "WH", "WA", "WU"]].stack().between(0, 1440).all()),
        "primary job work is a subset of broad 05xxxx work":
            bool(((df["W"] <= df["BW"]) & (df["WH"] <= df["BWH"])).all()),
        "replicate weights present and positive": bool(np.isfinite(rep).all() and (rep > 0).all()),
    }
    df["H"] = df["H_pc"] if home_def == "personalcare" else df["H_sleep"]
    df["N"] = df["H"] - df["WH"]
    df["N_broad"] = df["H"] - df["BWH"]
    alt = "H_sleep" if home_def == "personalcare" else "H_pc"
    df["N_alt"] = df[alt] - df["WH"]
    checks["WH <= H"] = bool((df["WH"] <= df["H"]).all())
    checks["H = WH + N exactly"] = bool((df["H"] == df["WH"] + df["N"]).all())
    for k, v in checks.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    if not all(checks.values()):
        raise SystemExit("Construction checks failed.")
    val_rows = [dict(check=k, result="PASS" if v else "FAIL") for k, v in checks.items()]

    d = build_controls(df, meta)
    d["REP_ROW"] = np.arange(len(d))
    ctrl = list(CONTROLS)
    ok = d[ctrl + ["WEIGHT"]].notna().all(axis=1) & (d["WEIGHT"] > 0)
    flow = pd.DataFrame({"step": ["respondents in extract", "positive weight",
                                  "complete controls = analytic sample (all charts)"],
                         "n": [len(d), int((d["WEIGHT"] > 0).sum()), int(ok.sum())]})
    print(flow.to_string(index=False))
    miss = d.loc[d["WEIGHT"] > 0, ctrl].isna().sum()
    print("Excluded for missing controls:", miss[miss > 0].to_dict())
    flow.to_csv(res_dir / "sample_flow.csv", index=False)
    a = d.loc[ok].copy()
    R = rep[a["REP_ROW"].to_numpy()]
    w = a["WEIGHT"].to_numpy(float)
    a["pattern"] = work_pattern(a)

    # ------------------------------------------------------------------ 2. reproduction of Sharkey
    section("2. REPRODUCTION OF SHARKEY (2024)")
    for yr, logged in SHARKEY_LOG_MEANS.items():
        g = d[d["YEAR"] == yr]  # his logged means: all respondents, weighted
        m = wavg(g["H_pc"], g["WEIGHT"])
        print(f"  {yr} weighted mean (Sharkey definition), all {len(g):,} respondents: {m:.4f}  [his log: {logged}]")
        val_rows.append(dict(check=f"{yr} weighted mean time at home, Sharkey definition", result=f"{m:.4f}",
                             benchmark=logged))
    a_sh = a[a["YEAR"] <= 2022].assign(month=lambda x: x["month_ipums"])
    r_sh, _ = wls(design(a_sh), a_sh[["H_pc"]], a_sh["WEIGHT"].to_numpy(float))
    c22 = r_sh["H_pc"].loc["year_2022", "coef"]
    print(f"  2003-2022 model: N = {len(a_sh):,} [his: {SHARKEY_ANALYTIC_N_2003_2022:,}], "
          f"2022 coefficient = {c22:.2f} [published: ~{SHARKEY_PUBLISHED_2022:.0f}]")
    val_rows += [dict(check="2003-2022 analytic N", result=len(a_sh), benchmark=SHARKEY_ANALYTIC_N_2003_2022),
                 dict(check="2003-2022 model, 2022 coefficient (Sharkey definition)", result=f"{c22:.2f}",
                      benchmark=SHARKEY_PUBLISHED_2022)]

    # ------------------------------------------------------------------ 3. annual diagnostics
    def g_stats(g):
        ww = g["WEIGHT"]
        out = {"n_unweighted": len(g)}
        for c in ["H", "N", "H_pc", "H_sleep", "W", "WH", "WA", "WU", "BW", "BWH", "uncoded", "gap",
                  "TRAVEL_WORK", "TRAVEL_WORK_BROAD"]:
            out[f"mean_{c}"] = wavg(g[c], ww)
        out.update({"share_any_job_work": wavg(g["W"] > 0, ww), "share_any_job_work_at_home": wavg(g["WH"] > 0, ww),
                    "share_employed": wavg(g["employed"] == "Employed", ww),
                    "min_diary_date": g["diary_date"].min().date(), "max_diary_date": g["diary_date"].max().date()})
        for p in models.PATTERNS:
            out[f"pattern_share_{p}"] = wavg(g["pattern"] == p, ww)
            out[f"pattern_n_{p}"] = int((g["pattern"] == p).sum())
        return pd.Series(out)
    diag = a.groupby("YEAR").apply(g_stats, include_groups=False)
    diag.to_csv(res_dir / "annual_diagnostics.csv")

    # ------------------------------------------------------------------ 4. Charts 1 & 2
    section("3. CHARTS 1 AND 2 (SDR replicate standard errors)")
    X0 = design(a)
    outcomes = ["H", "N", "WH", "W", "N_broad", "N_alt", alt]
    res0, _ = wls(X0, a[outcomes], w, R)
    yc = [c for c in X0.columns if c.startswith("year_")]
    ident = float((res0["H"].loc[yc, "coef"] - res0["N"].loc[yc, "coef"] - res0["WH"].loc[yc, "coef"]).abs().max())
    print(f"  Identity Chart 1 = Chart 2 + WH contrast: max |residual| = {ident:.1e}")
    val_rows.append(dict(check="identity: Chart 1 = Chart 2 + job work at home (max abs residual)",
                         result=f"{ident:.1e}"))
    rows = [year_rows(res0["H"], a, a["H"], "Chart 1", "Total time at home", "SDR"),
            year_rows(res0["N"], a, a["N"], "Chart 2", "Time at home excluding job work at home", "SDR"),
            year_rows(res0["WH"], a, a["WH"], "Accounting", "Job-work minutes at home (WH)", "SDR"),
            year_rows(res0["W"], a, a["W"], "Accounting", "Job-work minutes, all locations (W)", "SDR")]

    # ------------------------------------------------------------------ 5. Chart 3
    section("4. CHART 3 (work-pattern adjustment)")
    X_lin = design(a, extra=work_terms(a, flexible=False))
    X_flex = design(a, extra=work_terms(a, flexible=True))
    res_lin, _ = wls(X_lin, a[["H"]], w, R)
    res_flex, _ = wls(X_flex, a[["H"]], w, R)
    fitted = X_flex.to_numpy(float) @ res_flex["H"]["coef"].to_numpy()
    print(f"  flexible model: p = {X_flex.shape[1]}, fitted < 0: {(fitted < 0).sum()}, > 1440: {(fitted > 1440).sum()}")
    rows += [year_rows(res_flex["H"], a, a["H"], "Chart 3",
                       "Time at home adjusted for demographics and diary-day work patterns", "SDR"),
             year_rows(res_lin["H"], a, a["H"], "Chart 3 diagnostic",
                       "Time at home adjusted for demographics + linear W and WH hours", "SDR")]
    main_tab = pd.concat(rows, ignore_index=True)
    main_tab.to_csv(res_dir / "annual_results_main.csv", index=False, float_format="%.10g")

    # ------------------------------------------------------------------ 6. sensitivity checks
    section("5. SENSITIVITY CHECKS")
    sens = []

    def add(res, dd, outcome, chart, model, method="HC1"):
        sens.append(year_rows(res, dd, dd[outcome], chart, model, method))

    alt_label = ("Home + sleep only (narrower home definition)" if home_def == "personalcare"
                 else "Home + all no-location personal care (Sharkey definition)")
    add(res0["N_broad"], a, "N_broad", "Chart 2 sens.", "Excluding all 05xxxx work-related activities at home")
    add(res0[alt], a, alt, "Chart 1 sens.", alt_label)
    add(res0["N_alt"], a, "N_alt", "Chart 2 sens.", alt_label)
    bw = a.assign(BWA=a["BW"] - a["BWH"] - a["BWU"])
    r, _ = wls(design(a, extra=work_terms(bw, True, "BW", "BWH", "BWA", "BWU")), a[["H"]], w)
    add(r["H"], a, "H", "Chart 3 sens.", "Work adjustment using broad 05xxxx work")
    r, _ = wls(X_flex, a[[alt]], w)
    add(r[alt], a, alt, "Chart 3 sens.", alt_label)
    # excluding 2020
    b = a[a["YEAR"] != 2020]
    wb = b["WEIGHT"].to_numpy(float)
    r, _ = wls(design(b), b[["H", "N"]], wb)
    add(r["H"], b, "H", "Chart 1 sens.", "Excluding 2020")
    add(r["N"], b, "N", "Chart 2 sens.", "Excluding 2020")
    r, _ = wls(design(b, extra=work_terms(b, True)), b[["H"]], wb)
    add(r["H"], b, "H", "Chart 3 sens.", "Excluding 2020")
    # restricted period: drop the 2020 and 2025 gap calendar windows from every year
    md = a["diary_date"].dt.month * 100 + a["diary_date"].dt.day
    c = a[~np.logical_or.reduce([(md >= lo) & (md <= hi) for lo, hi in GAP_WINDOWS_MD])]
    wc = c["WEIGHT"].to_numpy(float)
    lab = "Restricted period: diary dates outside the 2020/2025 gaps, all years"
    r, _ = wls(design(c), c[["H", "N"]], wc)
    add(r["H"], c, "H", "Chart 1 sens.", lab)
    add(r["N"], c, "N", "Chart 2 sens.", lab)
    r, _ = wls(design(c, extra=work_terms(c, True)), c[["H"]], wc)
    add(r["H"], c, "H", "Chart 3 sens.", lab)
    # complete work-location sample
    e = a[a["WU"] == 0]
    r, _ = wls(design(e), e[["H", "N"]], e["WEIGHT"].to_numpy(float))
    add(r["H"], e, "H", "Chart 1 sens.", "Complete work-location sample")
    add(r["N"], e, "N", "Chart 2 sens.", "Complete work-location sample")
    # subgroups (employment control dropped: constant within group)
    ctrl_noemp = {k: v for k, v in CONTROLS.items() if k != "employed"}
    for label, mask in [("Not employed respondents", a["employed"] == "Not employed"),
                        ("Employed respondents with no job work at home on the diary day",
                         (a["employed"] == "Employed") & (a["WH"] == 0))]:
        g = a[mask]
        r, _ = wls(design(g, ctrl_noemp), g[["H"]], g["WEIGHT"].to_numpy(float))
        add(r["H"], g, "H", "Subgroup", label)
    # HC1 (Sharkey-style) intervals for the main charts
    add(res0["H"], a, "H", "Chart 1 HC1", "Total time at home, HC1 intervals")
    add(res0["N"], a, "N", "Chart 2 HC1", "Excluding job work at home, HC1 intervals")
    add(res_flex["H"], a, "H", "Chart 3 HC1", "Work-pattern adjusted, HC1 intervals")
    pd.concat(sens, ignore_index=True).to_csv(res_dir / "sensitivity_main.csv", index=False, float_format="%.10g")

    # year x work-pattern interactions, standardized to a fixed (2003 or 2019) pattern mix
    pats = models.PATTERNS[1:]
    years = sorted(a["YEAR"].unique())
    inter = {f"y{yr}_x_{p}": ((a["YEAR"] == yr) & (a["pattern"] == p)).astype(float)
             for yr in years[1:] for p in pats}
    Xi = design(a, extra=pd.concat([work_terms(a, True), pd.DataFrame(inter, index=a.index)], axis=1))
    ri, ci = wls(Xi, a[["H"]], w)
    std_rows = []
    for ref in (2003, 2019):
        g = a[a["YEAR"] == ref]
        share = {p: wavg(g["pattern"] == p, g["WEIGHT"]) for p in pats}
        for yr in years[1:]:
            gv = pd.Series(0.0, index=Xi.columns)
            gv[f"year_{yr}"] = 1.0
            for p in pats:
                if f"y{yr}_x_{p}" in gv.index:
                    gv[f"y{yr}_x_{p}"] = share[p]
            std_rows.append(dict(reference_pattern_mix=ref, year=yr, contrast_vs_2003=float(gv @ ri["H"]["coef"]),
                                 se_hc1=float(np.sqrt(gv @ ci["H"] @ gv)),
                                 **{f"n_{p}": int(((a["YEAR"] == yr) & (a["pattern"] == p)).sum()) for p in pats}))
    pd.DataFrame(std_rows).to_csv(res_dir / "sensitivity_chart3_interactions.csv", index=False, float_format="%.10g")

    # work travel and natural cubic splines (SDR intervals)
    section("6. CHART 3: WORK TRAVEL AND NATURAL CUBIC SPLINES")
    a["W_h"], a["WH_h"], a["TR_h"] = a["W"] / 60, a["WH"] / 60, a["TRAVEL_WORK"] / 60
    kW = models.knots_for(a["W_h"], (0.05, 0.275, 0.5, 0.725, 0.95))
    kWH = models.knots_for(a["WH_h"], (0.05, 0.35, 0.65, 0.95))
    kTR = models.knots_for(a["TR_h"], (0.05, 0.35, 0.65, 0.95))
    print("  cubic-spline knots (hours): W", kW.round(2), "| WH", kWH.round(2), "| travel", kTR.round(2))
    lin = work_terms(a, flexible=True)
    ncs = pd.concat([models.rcs_basis(a["W_h"], kW, "W_hours"), models.rcs_basis(a["WH_h"], kWH, "WH_hours"),
                     models.pattern_dummies(a)], axis=1)
    alt_models = {
        "Natural cubic splines in W and WH": ncs,
        "Linear splines + work travel 180501 (linear spline)":
            pd.concat([lin, models.travel_terms(a, "TRAVEL_WORK")], axis=1),
        "Linear splines + work travel, broad 1805xx (linear spline)":
            pd.concat([lin, models.travel_terms(a, "TRAVEL_WORK_BROAD")], axis=1),
        "Natural cubic splines + work travel 180501 (cubic spline)":
            pd.concat([ncs, models.rcs_basis(a["TR_h"], kTR, "TRAVEL_hours")], axis=1),
    }
    alt_rows = [year_rows(res_flex["H"], a, a["H"], "Chart 3 sens.", "Linear splines (main Chart 3)", "SDR")]
    fit_rows = []
    yv, ybar = a["H"].to_numpy(float), wavg(a["H"], w)
    for label, extra in alt_models.items():
        X = design(a, extra=extra)
        r, _ = wls(X, a[["H"]], w, R)
        alt_rows.append(year_rows(r["H"], a, a["H"], "Chart 3 sens.", label, "SDR"))
        f = X.to_numpy(float) @ r["H"]["coef"].to_numpy()
        fit_rows.append(dict(model=label, n_params=X.shape[1],
                             weighted_R2=1 - np.sum(w * (yv - f) ** 2) / np.sum(w * (yv - ybar) ** 2)))
    alt_tab = pd.concat(alt_rows, ignore_index=True)
    alt_tab.to_csv(res_dir / "sensitivity_chart3_travel_splines.csv", index=False, float_format="%.10g")
    pd.DataFrame(fit_rows).to_csv(res_dir / "sensitivity_chart3_travel_splines_fit.csv", index=False)

    pd.DataFrame(val_rows).to_csv(res_dir / "validation_checks.csv", index=False)

    # ------------------------------------------------------------------ 7. charts
    section("7. CHARTS")
    tabs = [main_tab[main_tab["chart"] == f"Chart {k}"] for k in (1, 2, 3)]
    ylim = charts.shared_ylim(tabs)
    for t, (stem, title, sub, note) in zip(tabs, charts.chart_text(len(a), int(a["AGE"].min()), home_def)):
        charts.save_square(t, title, sub, note, ylim, res_dir / stem)
        print(f"  saved {res_dir.name}/{stem}.png and .pdf")

    # ------------------------------------------------------------------ 8. summary
    section("8. SUMMARY (minutes per day vs 2003)")
    piv = main_tab.pivot_table(index="model", columns="year", values="estimate")[[2019, 2020, 2022, 2025]]
    print(piv.round(1).to_string())
    sp = alt_tab.pivot_table(index="model", columns="year", values="estimate")[[2019, 2022, 2025]]
    print(sp.round(1).to_string())
    with open(res_dir / "environment.txt", "w", encoding="utf-8") as f:
        f.write(f"Command: python run_all.py --home-def {home_def}\n")
        for k, v in env.items():
            f.write(f"{k}: {v}\n")
        f.write(f"respondents in extract: {len(df)}\n")
    print(f"\nDone in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
