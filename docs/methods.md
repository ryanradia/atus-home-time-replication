# Methods and results

## Questions

| Chart | Outcome | Question |
|---|---|---|
| 1 | **H**: minutes at home | How much has demographic-adjusted time at home changed since 2003? (reproduces and extends Sharkey 2024, Figure 1) |
| 2 | **N = H − WH**, where WH = job-work minutes done at home | How much of that change remains after removing the minutes spent actually working at a job at home? |
| 3 | **H**, additionally adjusted for diary-day work time and location | How much change remains among people with the same diary-day job-work time and work location? |

All three charts use the same sample, weights, controls, 2003 reference year and interval method.
Chart 3 is an adjusted descriptive trend, not a causal estimate of a world without remote work: WH is part
of H, so its coefficient partly reflects arithmetic. Chart 2 still contains indirect effects of working from
home, such as commuting time saved and then spent at home.

## Data

- **Source:** IPUMS ATUS, 2003–2025, hierarchical extract (household, person and activity records); see
  [`ipums_extract.md`](ipums_extract.md).
- **Universe:** ATUS respondents, the civilian noninstitutionalized U.S. population ages 15 and older,
  one diary day each (4 a.m. to 4 a.m.).
- **Sample:** 258,954 respondents. The analytic sample has **245,120** with complete controls: 13,698
  lack family income (all in 2003–2010, when FAMINCOME could be refused, don't know or blank) and 171 lack
  housing tenure (all in 2004).
- **Construction checks** (all pass; `results/validation_checks.csv`):
  - one record per respondent;
  - activity durations sum to 1,440 minutes in every diary;
  - activity lines run 1..n with no gaps or duplicates;
  - every minute total lies within 0–1,440;
  - W = WH + WA + WU;
  - H = WH + N exactly.

## Definitions

- **Time at home (H), following Sharkey's replication code.** An activity counts as at home if its
  location (WHERE) is "respondent's home or yard", or if its location is missing (not collected, don't know,
  refused) and it is personal care (ACTIVITY 010101–010499). The code (`timeuse_analysis_20240621.do`) is:
  `gen home=0 if tewhere>=1 & tewhere<=99`; `replace home=1 if tewhere==1`;
  `replace home=1 if home==. & trcodep>=10101 & trcodep<=10499`.
  - In the data, sleep, grooming and personal activities never have a recorded location, so all of them count.
  - Health-related self-care always has a recorded location and counts only when recorded at home.
  - "Unspecified place" is a recorded location, so it is not home.
  - Unknown activities (refused, can't remember) are not home.
- **Narrower alternative (sensitivity):** home or yard plus sleep (0101xx) only.
- **Job work (W):** ACTIVITY 0501xx, "Working": main job, other jobs, work security procedures, waiting
  associated with work, working n.e.c. Self-employment is coded here.
  - Excluded: work-related socializing/eating/sports (0502), other income-generating activities (0503),
    job search (0504) and work travel (1805).
  - WH is job work at WHERE = home.
  - WU is job work with location don't know, refused, not collected or unspecified place. That is one
    respondent in the analytic sample.
  - WA is all other locations, including vehicles.
- **Broad job work (sensitivity):** all 05xxxx.
- **Work travel (sensitivity):** ACTIVITY 180501 "travel related to working". The broad version is all 1805xx.
- **Month:** from the diary DATE. IPUMS MONTH disagrees with DATE for 4 respondents whose DATE agrees with
  the day of week.

## Model

Weighted least squares of each outcome on the following (no linear trend, no interactions):
- year indicators, with 2003 omitted;
- age (15–24, 25–34, 35–44, 45–54, 55–64, 65+);
- race/ethnicity (non-Hispanic White, Black, Asian; Hispanic; other);
- employed vs. not employed;
- married with spouse present vs. other;
- education (less than high school; high school or some college; college degree or more);
- own child under 18 in the household;
- sex;
- home ownership;
- family income (<$20k, $20k–$74.9k, ≥$75k);
- month and day-of-week indicators.

Chart 3 adds work-pattern terms:
- **Work-pattern indicators:** no job work / away only / home only / both home and away.
- **Linear spline in job-work hours:** knots at 4, 8 and 10.
- **Linear spline in at-home job-work hours:** knots at 2 and 6.

**Weights.** WT06 (2006 methodology) for every year except 2020, which uses WT20 (WT06 does not exist for 2020).

**Intervals.** Successive-difference replication: the full regression is refit with each of the 160
replicate weights (RWT06; RWT20 for 2020), and Var = 4/160 · Σ(b_r − b)² (BLS ATUS User's Guide).
- Each year's interval is for its contrast with 2003, so baseline uncertainty is included.
- The 2003 bar is 0 by definition and has no interval.
- Replicate indices are matched across years. The years are independently sampled, so the cross-year terms
  average to zero.
- HC1 (Sharkey-style) intervals are also reported in `sensitivity_main.csv` and are slightly wider.

## Data-collection gaps

- **2020:** no diaries from March 18 to May 9; WT20 represents only the observed period.
- **2025:** no diaries from September 30 to November 11, during the federal government shutdown. BLS
  weighted the remaining diaries to represent the full quarter and notes the effect cannot be quantified.
- Month indicators do not reconstruct unobserved dates. A restricted-period sensitivity check drops both
  calendar windows from every year.

## Reproduction of Sharkey (2024)

| Check | Sharkey | This code |
|---|---|---|
| 2003 weighted mean time at home, all 20,720 respondents | 991.9541 (replication log) | 991.9541 |
| 2022 weighted mean, all 8,136 respondents | 1,091.323 (replication log) | 1,091.3233 |
| 2003–2022 analytic N | 222,757 | 222,757 |
| 2022 year coefficient | ≈ 99 (published) | 98.90 |

## Main results (minutes per day vs. 2003; SDR standard errors in parentheses)

| | 2019 | 2020 | 2022 | 2025 |
|---|---|---|---|---|
| Chart 1: total time at home | 32.0 (4.0) | 131.6 (4.0) | 98.3 (4.6) | 94.7 (4.9) |
| Job work at home (WH) | 4.3 (1.3) | 32.6 (1.7) | 28.9 (2.0) | 25.2 (2.2) |
| Chart 2: time at home excluding job work | 27.7 (4.1) | 99.0 (4.0) | 69.3 (4.2) | 69.5 (4.4) |
| Chart 3: adjusted for diary-day work patterns | 25.1 (3.4) | 89.5 (3.3) | 60.7 (3.5) | 59.3 (3.9) |
| Job work, all locations (W) | −2.0 (3.2) | −6.3 (3.2) | −5.4 (3.2) | −8.6 (3.3) |

- **Accounting identity:** Chart 1 = Chart 2 + WH for every year (largest residual about 1e-11). The
  identity holds for point estimates only; the intervals do not add.
- **Job work at home** accounts for about 25 of the 95-minute rise from 2003 to 2025, and about 21 of the
  63-minute rise from 2019 to 2025.
- **What remains:** about 70 minutes remain outside job work at home, and about 59 among people with the
  same diary-day work time and location.
- **Timing:** much of the rise predates the pandemic (+25 to +32 by 2019, of which 4 minutes is job work at
  home), and levels have been stable since 2022.
- **Scope:** these are minutes at home. They are not measures of loneliness or social connection, and no
  causal claims are made.

## Sensitivity checks (2019 / 2020 / 2022 / 2025)

| Check | Chart 1 | Chart 2 | Chart 3 |
|---|---|---|---|
| Main | 32.0 / 131.6 / 98.3 / 94.7 | 27.7 / 99.0 / 69.3 / 69.5 | 25.1 / 89.5 / 60.7 / 59.3 |
| Narrower home definition (home + sleep only) | 32.7 / 135.4 / 100.0 / 96.3 | 28.4 / 102.8 / 71.0 / 71.1 | 25.6 / 92.0 / 61.2 / 59.8 |
| Broad 05xxxx work definition | — | 26.9 / 98.9 / 69.6 / 68.9 | 24.1 / 88.1 / 60.1 / 57.9 |
| Excluding 2020 | 32.3 / — / 98.7 / 95.3 | 27.8 / — / 69.5 / 69.9 | 25.2 / — / 60.9 / 59.7 |
| Restricted period (drop Mar 18–May 9 and Sep 30–Nov 11 in every year) | 34.0 / 128.6 / 101.9 / 96.4 | 29.3 / 98.0 / 72.6 / 71.7 | 27.7 / 88.7 / 65.1 / 62.3 |
| Linear W and WH only (diagnostic) | — | — | 25.8 / 90.9 / 62.3 / 60.5 |
| Natural cubic splines in W and WH | — | — | 25.1 / 89.5 / 60.7 / 59.3 |
| + work travel 180501 (linear spline) | — | — | 25.6 / 89.8 / 60.8 / 59.4 |
| + work travel, broad 1805xx | — | — | 25.0 / 88.9 / 60.0 / 58.7 |
| Cubic splines + work travel (cubic spline) | — | — | 25.6 / 89.8 / 60.7 / 59.3 |
| Year × work-pattern interactions, 2003 pattern mix | — | — | 25.0 / 84.7 / 59.1 / 59.0 |
| Year × work-pattern interactions, 2019 pattern mix | — | — | 25.3 / 86.2 / 59.8 / 59.2 |

Subgroup trends in total time at home are shown below. These are changing subpopulations, and the second
group is not "people who never work remotely":

| Subgroup | 2019 | 2020 | 2022 | 2025 |
|---|---|---|---|---|
| Not employed | +32.3 | +109.4 | +67.8 | +65.4 |
| Employed with no job work at home on the diary day | +29.1 | +95.2 | +74.7 | +78.8 |

**Work travel.** Adding work travel is an upper bound on the commute's role. Work travel is almost always
away from home (about 1% of 1805xx minutes are recorded at home), and shorter commutes are one way remote
work raises time at home. It moves Chart 3 by under 1 minute in every year. Average work travel fell only
about 2 minutes a day between 2003 and 2025 (`annual_diagnostics.csv`), and most of that is already captured
by the work-location pattern.

**Natural cubic splines.** Cubic splines use the same number of parameters as the linear splines, with knots
at standard percentiles of positive values. They give identical fit (weighted R² 0.535) and year contrasts
within 0.03 minutes.

## Caveats

- **Unknown activities can hide job work.** Activity codes 50xxxx (insufficient detail, can't remember) cover
  7–18 minutes a day with no trend; any job work inside them is unobserved, so WH is a lower bound.
- **Telework questions are not used.** Usual telework arrangements are not measured on the diary day, and the
  questions are not available in all years.
- **Survey design.** Pooling replicate weights across years by matching replicate index is standard practice
  but not officially documented by BLS for multi-year regressions.

## References

- Sharkey, Patrick. 2024. "Homebound: The Long-Term Rise in Time Spent at Home Among U.S. Adults."
  *Sociological Science* 11: 553–578. <https://doi.org/10.15195/v11.a20>. Replication files: Harvard Dataverse,
  <https://doi.org/10.7910/DVN/R4P98D>.
- Flood, Sarah M., Liana C. Sayer, Daniel Backman, and Etienne Breton. 2026. American Time Use Survey Data
  Extract Builder: Version 3.4 [dataset]. College Park, MD: University of Maryland and Minneapolis, MN: IPUMS.
  DOI 10.18128/D060.V3.4. <https://www.ipums.org/projects/ipums-time-use/d060.V3.4>
- U.S. Bureau of Labor Statistics. *American Time Use Survey User's Guide*. <https://www.bls.gov/tus/atususersguide.pdf>
- U.S. Bureau of Labor Statistics. Notice on missing 2025 ATUS data (Sep 30–Nov 11, 2025).
  <https://www.bls.gov/tus/notices/2026/october2025shutdown.htm>
