"""
Reading an IPUMS ATUS hierarchical extract and building one analysis record per respondent.

All column positions, implied decimals and value labels are read from the DDI codebook (.xml)
that IPUMS delivers with the extract, so the code does not depend on variable order.
"""
from __future__ import annotations

import gzip
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pandas as pd

NS = "{ddi:codebook:2_5}"
N_REP = 160

# ---- activity and location codes (IPUMS ATUS ACTIVITY / WHERE) ---------------------------
# Job work (primary): ACTIVITY 0501xx "Working": main job, other job(s), security procedures
# related to work, waiting associated with working, working n.e.c. Self-employment is coded here.
WORK_PRIMARY = ("050101", "050102", "050103", "050104", "050199")
WORK_BROAD_PREFIX = "05"           # sensitivity: all work and work-related activities
WHERE_HOME = "0101"                # "R's home or yard"
WHERE_MISSING = ("9997", "9998", "9999")             # don't know, refused, NIU (not collected)
WHERE_UNKNOWN = WHERE_MISSING + ("0115",)            # ... plus "unspecified place" (for work location)
SLEEP_PREFIX = "0101"              # 010101 sleeping, 010102 sleeplessness, 010199 n.e.c.
# Sharkey (2024) replication code: an activity is at home if its location is the respondent's home
# or yard, or if its location is missing and it is personal care (ACTIVITY 010101-010499).
PCARE_PREFIXES = ("0101", "0102", "0103", "0104")
TRAVEL_WORK = "180501"             # travel related to working
TRAVEL_WORK_PREFIX = "1805"        # all work-related travel (sensitivity)

HH_VARS = ["FAMINCOME", "HHTENURE"]
PERSON_VARS = ["YEAR", "CASEID", "LINENO", "MONTH", "DAY", "DATE", "WT06", "WT20", "AGE", "SEX", "RACE",
               "HISPAN", "MARST", "EDUC", "EMPSTAT", "KIDUND18"]
ACT_VARS = ["ACTLINE", "ACTIVITY", "WHERE", "DURATION"]
REP_FAMILIES = ("RWT06", "RWT20")

ACC = ["n_act", "dur_sum", "H_pc", "H_sleep", "home_where", "sleep", "pcare_noloc",
       "W", "WH", "WA", "WU", "BW", "BWH", "BWU", "uncoded", "gap", "TRAVEL_WORK", "TRAVEL_WORK_BROAD"]
CACHE_VERSION = "1"


def find_extract(data_dir: Path) -> tuple[Path, Path]:
    """Locate the extract's data file (.dat or .dat.gz) and its DDI codebook (.xml)."""
    data_dir = Path(data_dir)
    pairs = []
    for xml in sorted(data_dir.glob("*.xml")):
        for dat in (xml.with_suffix(".dat"), xml.with_suffix(".dat.gz")):
            if dat.exists():
                pairs.append((dat, xml))
    if not pairs:
        raise SystemExit(f"No IPUMS ATUS extract found in {data_dir}. Put the .dat (or .dat.gz) file and its "
                         "DDI .xml codebook there; see docs/ipums_extract.md.")
    if len(pairs) > 1:
        print(f"Several extracts found; using the most recently modified: {pairs[-1][0].name}")
        pairs.sort(key=lambda p: p[0].stat().st_mtime)
    return pairs[-1]


def parse_ddi(xml: Path) -> dict:
    meta = {}
    for v in ET.parse(xml).getroot().iter(NS + "var"):
        loc = v.find(NS + "location")
        meta[v.get("name").upper()] = dict(
            rt=set((v.get("rectype") or "1 2 3").split()), s=int(loc.get("StartPos")) - 1,
            e=int(loc.get("EndPos")), dcml=int(v.get("dcml", "0")),
            label=(v.findtext(NS + "labl") or "").strip(),
            values={int(c.findtext(NS + "catValu")): c.findtext(NS + "labl").strip()
                    for c in v.findall(NS + "catgry")})
    return meta


def check_variables(meta: dict) -> None:
    need = (["RECTYPE"] + HH_VARS + PERSON_VARS + ACT_VARS
            + [f"{f}_{k}" for f in REP_FAMILIES for k in range(1, N_REP + 1)])
    missing = [v for v in need if v not in meta]
    if missing:
        short = sorted({m.split("_")[0] if m.startswith("RWT") else m for m in missing})
        raise SystemExit(f"The extract is missing required variables: {short}. "
                         "See docs/ipums_extract.md for the exact variable list.")
    for v in HH_VARS:
        assert "1" in meta[v]["rt"], f"{v} expected on the household record"
    for v in ACT_VARS:
        assert meta[v]["rt"] == {"3"}, f"{v} expected on the activity record (hierarchical extract required)"


def _open(path: Path):
    return gzip.open(path, "rt", encoding="latin-1") if path.suffix == ".gz" else open(path, encoding="latin-1")


def _replicate_block(meta, fam):
    s, e = meta[f"{fam}_1"]["s"], meta[f"{fam}_{N_REP}"]["e"]
    for k in range(1, N_REP + 1):  # verify contiguous 15-character fields with 6 implied decimals
        m = meta[f"{fam}_{k}"]
        assert m["s"] == s + 15 * (k - 1) and m["e"] - m["s"] == 15 and m["dcml"] == 6
    return s, e


_POW10 = 10 ** np.arange(14, -1, -1, dtype=np.int64)


def _parse_block(raw: str) -> np.ndarray:
    b = np.frombuffer(raw.encode("ascii"), dtype=np.uint8).reshape(N_REP, 15) - 48
    if (b > 9).any():
        raise ValueError("non-digit in replicate weight block")
    return (b.astype(np.int64) @ _POW10) / 1e6


def read_extract(dat: Path, meta: dict):
    """One pass over the hierarchical file. Household variables are carried to the respondent;
    activity records are aggregated to one row per respondent. Returns (DataFrame, replicate matrix)
    where the replicate matrix holds RWT06_1-160 (RWT20_1-160 for 2020)."""
    pos = {n: (meta[n]["s"], meta[n]["e"]) for n in PERSON_VARS + HH_VARS}
    a_line, a_act, a_where, a_dur = (meta[n] for n in ACT_VARS)
    r06, r20 = _replicate_block(meta, "RWT06"), _replicate_block(meta, "RWT20")
    ix = {k: j for j, k in enumerate(ACC)}
    raw = {n: [] for n in PERSON_VARS + HH_VARS}
    reps, accs = [], []
    hh = hh_cid = cid = row = None
    last_line = 0
    with _open(dat) as fh:
        for line in fh:
            t = line[0]
            if t == "1":
                hh_cid = line[6:20]
                hh = [line[slice(*pos[n])] for n in HH_VARS]
            elif t == "2":
                cid = line[6:20]
                assert cid == hh_cid, f"person {cid} without its household record"
                for n in PERSON_VARS:
                    raw[n].append(line[slice(*pos[n])])
                for n, v in zip(HH_VARS, hh):
                    raw[n].append(v)
                s, e = r20 if int(line[1:6]) == 2020 else r06
                blk = line[s:e]
                reps.append(_parse_block(blk) if blk.strip() else np.full(N_REP, np.nan))
                row = np.zeros(len(ACC), dtype=np.int64)
                accs.append(row)
                last_line = 0
            elif t == "3":
                assert line[6:20] == cid, "activity record out of order"
                al = int(line[a_line["s"]:a_line["e"]])
                assert al == last_line + 1, f"ACTLINE gap or duplicate for case {cid}"
                last_line = al
                act = line[a_act["s"]:a_act["e"]]
                where = line[a_where["s"]:a_where["e"]]
                dur = int(line[a_dur["s"]:a_dur["e"]])
                row[ix["n_act"]] += 1
                row[ix["dur_sum"]] += dur
                home = where == WHERE_HOME
                sleep = act.startswith(SLEEP_PREFIX)
                pc_noloc = where in WHERE_MISSING and act[:4] in PCARE_PREFIXES
                if home:
                    row[ix["home_where"]] += dur
                if sleep:
                    row[ix["sleep"]] += dur
                if pc_noloc:
                    row[ix["pcare_noloc"]] += dur
                if home or pc_noloc:
                    row[ix["H_pc"]] += dur
                if home or sleep:
                    row[ix["H_sleep"]] += dur
                unknown = where in WHERE_UNKNOWN
                if act in WORK_PRIMARY:
                    row[ix["W"]] += dur
                    row[ix["WH" if home else "WU" if unknown else "WA"]] += dur
                if act.startswith(WORK_BROAD_PREFIX):
                    row[ix["BW"]] += dur
                    if home:
                        row[ix["BWH"]] += dur
                    elif unknown:
                        row[ix["BWU"]] += dur
                if act.startswith("50"):
                    row[ix["uncoded"]] += dur
                    if act == "500106":
                        row[ix["gap"]] += dur
                if act.startswith(TRAVEL_WORK_PREFIX):
                    row[ix["TRAVEL_WORK_BROAD"]] += dur
                    if act == TRAVEL_WORK:
                        row[ix["TRAVEL_WORK"]] += dur
            else:
                raise ValueError(f"unknown record type {t!r}")
    df = pd.DataFrame(np.vstack(accs), columns=ACC)
    for v in PERSON_VARS + HH_VARS:
        s = pd.Series(raw[v]).str.strip()
        if v == "CASEID":
            df[v] = s.values  # exact 14-character identifier
            continue
        s = s.where(s != "", None)
        vals = pd.to_numeric(s)
        if meta[v]["dcml"] > 0:  # implied decimals apply only when no explicit decimal point
            vals = vals.where(s.fillna("").str.contains(".", regex=False), vals / 10 ** meta[v]["dcml"])
        df[v] = vals.values
    return df, np.vstack(reps)


def load(dat: Path, meta: dict, cache_dir: Path):
    """Parse once and cache the respondent-level file (the raw extract is ~1.5 GB)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    st = dat.stat()
    key = f"{CACHE_VERSION}_{st.st_size}_{int(st.st_mtime)}"
    pf, rf = cache_dir / f"respondents_{key}.pkl", cache_dir / f"replicates_{key}.npy"
    if pf.exists() and rf.exists():
        return pd.read_pickle(pf), np.load(rf)
    df, rep = read_extract(dat, meta)
    df.to_pickle(pf)
    np.save(rf, rep)
    return df, rep
