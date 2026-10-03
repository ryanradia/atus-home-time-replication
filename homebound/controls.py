"""
Demographic and calendar controls, recoded from IPUMS value labels (never from assumed numeric codes).
Categories follow Sharkey (2024).
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

MISSING_LABEL = re.compile(r"NIU|not in universe|refused|don't know|dont know|blank|missing|unknown", re.I)

# Control -> reference category (the reference choice does not affect the year contrasts).
CONTROLS = {
    "age_cat": "15-24",
    "race_eth": "NH White",
    "employed": "Employed",
    "married_sp": "Other",
    "educ_cat": "HS grad / some college",
    "kid_u18": "No own child <18",
    "sex": "Male",
    "owner": "Non-owner",
    "inc_cat": "Middle ($20k-74.9k)",
    "month": 1,
    "dow": "Sunday",
}


def missing_codes(meta: dict, var: str) -> set[int]:
    return {k for k, v in meta[var]["values"].items() if MISSING_LABEL.search(v)}


def recode_by_label(series: pd.Series, meta: dict, var: str, rules: list[tuple[str, object]]):
    """Map each valid code to a category using ordered (regex, category) rules applied to value labels.
    Missing/NIU codes become NaN. Raises if a substantive code present in the data is left unmapped."""
    labels = meta[var]["values"]
    miss = missing_codes(meta, var)
    mapping = {}
    for code, lab in labels.items():
        if code in miss:
            continue
        for pat, cat in rules:
            if re.search(pat, lab, re.I):
                mapping[code] = cat
                break
    present = set(series.dropna().astype(int).unique())
    unmapped = present - set(mapping) - miss
    if unmapped:
        raise SystemExit(f"{var}: codes present but not mapped by label rules: {sorted(unmapped)}")
    return series.map(mapping)


def income_lower_bound(label: str) -> float | None:
    if re.search(r"less than", label, re.I):
        return 0.0
    m = re.search(r"\$([\d,]+)", label)
    return float(m.group(1).replace(",", "")) if m else None


def build_controls(d: pd.DataFrame, meta: dict) -> pd.DataFrame:
    d = d.copy()
    # Age: 996/997/999 are refused/don't know/NIU. Top codes (80; 80/85 from 2005) fall inside 65+.
    a = d["AGE"].where(d["AGE"] < 996)
    d["age_cat"] = pd.cut(a, [14, 24, 34, 44, 54, 64, 200],
                          labels=["15-24", "25-34", "35-44", "45-54", "55-64", "65+"]).astype(object)
    # Race/ethnicity: anyone Hispanic -> Hispanic; otherwise single-race White/Black/Asian; else Other.
    hisp = recode_by_label(d["HISPAN"], meta, "HISPAN", [(r"^not hispanic$", 0), (r".", 1)])
    race = recode_by_label(d["RACE"], meta, "RACE",
                           [(r"^white only$", "NH White"), (r"^black only$", "NH Black"),
                            (r"^asian only$", "NH Asian"), (r"^asian or pacific islander$", "NH Asian"),
                            (r".", "Other")])
    d["race_eth"] = np.where(hisp == 1, "Hispanic", race)
    d.loc[hisp.isna() | race.isna(), "race_eth"] = np.nan
    d["employed"] = recode_by_label(d["EMPSTAT"], meta, "EMPSTAT",
                                    [(r"^employed", "Employed"),
                                     (r"unemployed|not in labor force", "Not employed")])
    d["educ_cat"] = recode_by_label(
        d["EDUC"], meta, "EDUC",
        [(r"grade", "Less than HS"), (r"high school graduate|some college|associate", "HS grad / some college"),
         (r"bachelor|master|professional|doctoral", "College grad+")])
    d["married_sp"] = recode_by_label(d["MARST"], meta, "MARST",
                                      [(r"married - spouse present", "Married, spouse present"), (r".", "Other")])
    d["kid_u18"] = recode_by_label(d["KIDUND18"], meta, "KIDUND18",
                                   [(r"^yes$", "Own child <18"), (r"^no$", "No own child <18")])
    d["sex"] = recode_by_label(d["SEX"], meta, "SEX", [(r"^male$", "Male"), (r"^female$", "Female")])
    d["owner"] = recode_by_label(d["HHTENURE"], meta, "HHTENURE", [(r"^owned", "Owner"), (r"rent", "Non-owner")])
    inc = {}
    for code, lab in meta["FAMINCOME"]["values"].items():
        if code in missing_codes(meta, "FAMINCOME"):
            continue
        lb = income_lower_bound(lab)
        inc[code] = "Low (<$20k)" if lb < 20000 else "High ($75k+)" if lb >= 75000 else "Middle ($20k-74.9k)"
    d["inc_cat"] = d["FAMINCOME"].map(inc)
    # Month from the diary DATE. IPUMS MONTH disagrees with DATE for a handful of respondents whose
    # DATE agrees with the day of week; MONTH is kept for the Sharkey reproduction check.
    date = pd.to_datetime(d["DATE"].astype(int).astype(str), format="%Y%m%d")
    d["diary_date"] = date
    d["month"] = date.dt.month
    d["month_ipums"] = d["MONTH"]
    d["dow"] = d["DAY"].map({k: v for k, v in meta["DAY"]["values"].items()
                             if k not in missing_codes(meta, "DAY")})
    # Weights: WT06 for every year except 2020, when WT06 does not exist and WT20 is required.
    d["WEIGHT"] = np.where(d["YEAR"] == 2020, d["WT20"], d["WT06"])
    return d
