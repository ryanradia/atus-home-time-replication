"""
Square (2500 x 2500 px) bar charts of year contrasts vs 2003, with 95% CI whiskers.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from .models import FIRST_YEAR  # noqa: E402

RED, INK, MUTED, GRID = "#C8102E", "#1a1a1a", "#595959", "#e3e3e3"
LABEL_YEARS = (2019, 2020, 2022, 2025)
SIZE_IN, DPI = 10, 250
TITLE_PT, SUB_PT, NOTE_PT, XTICK_PT, YTICK_PT, VALUE_PT = 21, 12.5, 10.5, 9.5 * 1.15, 9.5, 9.5
NOTE_WRAP, NOTE_SPACING = 122, 1.3
LEFT, RIGHT = 0.05, 0.985

HOME_NOTE = {
    "personalcare": "Time at home = activities in 'respondent's home or yard' + personal care with no recorded "
                    "location (sleep, grooming, personal activities), as in Sharkey (2024)",
    "sleep": "Time at home = activities in 'respondent's home or yard' + sleep (location not collected for sleep)",
}
JOB = "Job work = ACTIVITY 0501xx (main/other job, incl. self-employment; excludes commuting, job search)"


def chart_text(n_tot: int, min_age: int, home_def: str) -> list[tuple[str, str, str, str]]:
    """(file stem, title, subtitle, footnote) for Charts 1-3."""
    base = (
        f"Sample: American Time Use Survey respondents, civilian noninstitutionalized U.S. population ages "
        f"{min_age} and older; one diary day per respondent, 2003-2025 (N = {n_tot:,} with complete data). "
        "Bars: year coefficients from weighted OLS (2003 = reference) controlling for age, race/ethnicity, employment, "
        "marital status, education, own child <18, sex, home ownership, family income, month and day of week{extra}. "
        "Error bars: 95% CIs from 160 successive-difference replicate weights. Weights: WT06 (WT20 for 2020). "
        + HOME_NOTE[home_def] + "{outcome}. "
        "No diaries were collected Mar 18-May 9, 2020 or Sep 30-Nov 11, 2025. Source: ATUS via IPUMS ATUS. "
        "Extends Sharkey (2024), Figure 1.")
    return [
        ("chart1_time_at_home", "Time Spent at Home",
         "Change in average minutes per day spent at home compared with 2003",
         base.format(extra="", outcome="")),
        ("chart2_time_at_home_excluding_job_work", "Time at Home, Excluding Job Work",
         "Change in average minutes per day spent at home, not counting job work done at home, compared with 2003",
         base.format(extra="", outcome=f", minus job work done at home. {JOB}")),
        ("chart3_time_at_home_adjusted_for_work_patterns", "Time at Home, Adjusted for Work Patterns",
         "Change in average minutes per day at home vs. 2003, holding diary-day job-work time and location constant",
         base.format(extra="; plus diary-day job-work hours and at-home job-work hours (linear splines) and "
                           "work location pattern (none/away/home/both)", outcome=f". {JOB}")),
    ]


def shared_ylim(tables: list[pd.DataFrame]) -> tuple[float, float]:
    """One y-range for all three charts: just below the lowest CI and just above the highest CI + label."""
    allc = pd.concat(tables)
    return min(0.0, allc["ci95_low"].min()) - 6, allc["ci95_high"].max() + 10


def draw_panel(ax, t: pd.DataFrame, ylim):
    t = t[t["year"] != FIRST_YEAR]  # 2003 is the reference (0 by definition); stated in the subtitle
    x, y = t["year"].to_numpy(), t["estimate"].to_numpy()
    ax.set_facecolor("white")
    ax.bar(x, y, width=0.72, color=RED, zorder=2, edgecolor="white", linewidth=0.8)
    ax.errorbar(x, y, yerr=[y - t["ci95_low"].to_numpy(), t["ci95_high"].to_numpy() - y], fmt="none",
                ecolor=INK, elinewidth=1.0, capsize=2.5, capthick=1.0, zorder=3)
    for yr in LABEL_YEARS:
        r = t.loc[t["year"] == yr]
        if len(r):
            r = r.iloc[0]
            ax.text(yr, max(r["ci95_high"], 0) + 3, f"{r['estimate']:+.0f}", ha="center", va="bottom",
                    fontsize=VALUE_PT, color=INK, fontweight="bold")
    ax.axhline(0, color="#8c8c8c", linewidth=0.9, zorder=1)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8, zorder=0)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color("#8c8c8c")
    ax.tick_params(axis="x", colors=MUTED, labelsize=XTICK_PT, length=0)
    ax.tick_params(axis="y", colors=MUTED, labelsize=YTICK_PT, length=0)
    ax.set_xticks(x)
    ax.set_xticklabels([str(v) for v in x], rotation=45, ha="right")
    ax.set_xlim(x.min() - 0.6, x.max() + 0.6)
    ax.set_ylim(*ylim)


def _h(n_lines, pt, spacing):
    return n_lines * pt * spacing / 72 / SIZE_IN


def save_square(t: pd.DataFrame, title: str, subtitle: str, note: str, ylim, stem: Path):
    plt.rcParams.update({"font.family": "sans-serif", "pdf.fonttype": 42})
    fig = plt.figure(figsize=(SIZE_IN, SIZE_IN), dpi=DPI)
    fig.patch.set_facecolor("white")
    sub = textwrap.fill(subtitle, 82)
    note = textwrap.fill(" ".join(note.split()), NOTE_WRAP)
    top_title = 0.98
    sub_top = top_title - 0.042
    ax_top = sub_top - _h(sub.count("\n") + 1, SUB_PT, 1.3) - 0.008
    note_bottom = 0.014
    ax_bottom = note_bottom + _h(note.count("\n") + 1, NOTE_PT, NOTE_SPACING) + 0.088
    ax = fig.add_axes([LEFT, ax_bottom, RIGHT - LEFT, ax_top - ax_bottom])
    draw_panel(ax, t, ylim)
    ax.set_xlabel("Year", color=INK, fontsize=11, labelpad=8)
    fig.text(LEFT, top_title, title, fontsize=TITLE_PT, fontweight="bold", family="serif", color=INK, va="top")
    fig.text(LEFT, sub_top, sub, fontsize=SUB_PT, color=MUTED, va="top", linespacing=1.3)
    fig.text(LEFT, note_bottom, note, fontsize=NOTE_PT, color=MUTED, va="bottom", linespacing=NOTE_SPACING)
    fig.savefig(stem.with_suffix(".png"), dpi=DPI, facecolor="white")
    fig.savefig(stem.with_suffix(".pdf"), facecolor="white")
    plt.close(fig)
