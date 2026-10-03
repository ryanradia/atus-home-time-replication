# Getting the data from IPUMS ATUS

This repository does **not** include any IPUMS microdata. IPUMS terms of use do not allow redistributing
extracts, so every user must create their own (free) extract. The steps below reproduce the extract
used to generate `results/`.

## 1. Register and agree to the terms

1. Go to <https://www.atusdata.org> and create a free account (or log in).
2. Accept the IPUMS ATUS conditions of use, which govern any use of the data, including the prohibition on
   redistributing extracts.

## 2. Build the extract

Open the data extract builder ("Get Data" / "Select Data").

**Samples.** Select every ATUS annual sample from **2003 through 2025** (23 samples).

**Variables.** Add the variables below. IPUMS adds the technical identifiers (`YEAR`, `CASEID`, `SERIAL`,
`STRATA`, `PERNUM`, `ACTLINE`, `RECTYPE`) automatically. Variable order does not matter, because the code
reads every position from the DDI codebook.

| Level | Variables |
|---|---|
| Household | `HHTENURE`, `FAMINCOME` |
| Person: technical | `LINENO`, `DATE`, `MONTH`, `DAY` |
| Person: weights | `WT06`, `WT20`, `RWT06`, `RWT20` (choosing the replicate weights adds all 160 of each: `RWT06_1`–`RWT06_160`, `RWT20_1`–`RWT20_160`) |
| Person: demographics | `AGE`, `SEX`, `RACE`, `HISPAN`, `MARST`, `EDUC`, `EMPSTAT`, `KIDUND18` |
| Activity | `ACTIVITY`, `WHERE`, `DURATION` (use `DURATION`, not `DURATION_EXT`) |

No time-use summary variables are needed. Time at home, job work, location and work travel are all built
from the activity records.

**Extract options.** In the extract cart, before submitting:

- **Data structure: Hierarchical.** The code needs household, person and activity records. Rectangular
  person or activity extracts will not work.
- **Data format: fixed-width text (.dat).**
- **Sample members: ATUS respondents only** (the default). The code checks that every person record is
  the respondent (`LINENO = 1`).
- Do not add case selections or attach "who" (with-whom) records.

Submit the extract. The uncompressed file is about 1.5 GB, and IPUMS delivers it gzip-compressed.

## 3. Download and place the files

When the extract is ready, download **both**:

- the data file, `atus_000NN.dat.gz` (it can stay compressed; the code reads `.dat.gz` directly), and
- the **DDI codebook**, `atus_000NN.xml` (the "DDI" link next to the extract). The code needs it for column
  positions, implied decimals and value labels.

Put both in this repository's `data/` folder, keeping the base names identical apart from the
extension, then run:

```
python run_all.py
```

Alternatively, leave the files anywhere and run `python run_all.py --data-dir /path/to/folder`.

If a required variable is missing, the script stops and lists it.

## Version note

`results/` was produced from IPUMS ATUS **Version 3.4** (DOI 10.18128/D060.V3.4), the current release when
the extract was created in October 2026. It is the first release that includes the 2025 ATUS. The DDI
codebook delivered with the extract still printed the Version 3.3 citation text; the IPUMS version page
(<https://www.ipums.org/projects/ipums-time-use/d060.V3.4>) identifies 3.4 as the current release.

IPUMS and BLS occasionally revise past data, so extracts made from later releases may differ slightly.
`results/validation_checks.csv` reports the values every rerun should reproduce for the published
Sharkey (2024) benchmarks.

## Data reference

Sarah M. Flood, Liana C. Sayer, Daniel Backman and Etienne Breton. American Time Use Survey Data Extract
Builder: Version 3.4 [dataset]. College Park, MD: University of Maryland and Minneapolis, MN: IPUMS, 2026.
DOI 10.18128/D060.V3.4.
