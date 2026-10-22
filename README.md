# NSW Housing Supply Pipeline Dashboard

Independent analysis using DPHI's openly licensed data sheet. Not produced by, affiliated with or endorsed by the NSW Department of Planning, Housing and Infrastructure or the NSW Government.

Interactive dashboard tracking the NSW housing supply pipeline from lodgement through to completion, built from DPHI open data.

**[View Dashboard](https://bhanurekhab.github.io/nsw-housing-supply-dashboard/output/housing_supply_dashboard.html)**

## What This Project Does

- Processes the NSW Department of Planning, Housing and Infrastructure (DPHI) Housing Supply Dashboard data sheet
- Tracks four pipeline stages: lodged, approved for development, approved for construction, and completions
- Measures LGA-level progress against the five-year housing targets set under the National Housing Accord
- Summarises greenfield precinct capacity and lot creation across Sydney's growth areas
- Produces a self-contained HTML dashboard with Chart.js visualisations

## Data Source

- **Housing supply pipeline:** [DPHI Housing Supply Dashboard Data Sheet](https://data.nsw.gov.au/data/dataset/housing-supply) (CC BY 3.0 AU)
- **Housing targets:** [DPHI Housing Targets](https://www.planning.nsw.gov.au/policy-and-legislation/housing/housing-targets)
- **Construction approvals methodology:** [ABS Building Approvals, Australia](https://www.abs.gov.au/methodologies/building-approvals-australia-methodology/aug-2026)

Data covers July 2024 to September 2026 (construction approvals to August 2026; completions to the June 2026 quarter). Data sheet release of 13 October 2026, downloaded October 2026. The SHA-256 hash of the data sheet is recorded in the dashboard footer and `summary.json` so the release can be identified.

## Dashboard Sections

1. **Key findings** — KPI tiles (including greenfield capacity and new lots) and five generated findings, headline first
2. **Pipeline overview** — monthly lodgements, development approvals and construction approvals
3. **Dwelling completions** — quarterly houses vs other dwellings
4. **Target LGA progress** — DA and construction approvals as a percentage of pro-rated five-year completion targets for the 15 largest target LGAs
5. **Construction-to-DA ratio** — all 43 target LGAs ranked by how far construction approvals lag DA approvals (the apartment feasibility gap)
6. **Greenfield capacity and lot creation** — precinct capacity in one panel; new lots and subdivision approvals in another
7. **Methodology and sources** — stage definitions, target framework, regional remainder method, feasibility-gap caveats, computed data-quality notes

Each chart has a "Show data table" toggle and the page has a light/dark theme switch. The HTML is fully self-contained (Chart.js is embedded), so it works offline.

## Pipeline Outputs

| File | Description |
|------|-------------|
| `housing_supply_dashboard.html` | Self-contained interactive dashboard |
| `pipeline_monthly.csv` | Monthly lodged, dev-approved and construction-approved totals |
| `completions_quarterly.csv` | Quarterly completions by dwelling type |
| `target_progress.csv` | LGA-level target progress (DA and construction approval %) |
| `feasibility_gap.csv` | Construction-to-DA ratio for each target LGA |
| `greenfield_summary.csv` | Growth-area precinct capacity and lot creation |
| `chart_data.json` | Pre-calculated chart data consumed by the dashboard |
| `summary.json` | Machine-readable key findings |

## How to Run

```bash
pip install -r requirements.txt
python scripts/analyse_housing.py
```

The script reads `data/housingsupplydashboard_datasheet.xlsx` and writes all output files to `output/`. To refresh, download the latest data sheet from data.nsw.gov.au into `data/` and re-run. The run prints a warning for any null cells it converts to zero. Narrative notes in the methodology section (as-at dates, named precincts) were written for the 13 October 2026 release and should be re-checked after a refresh.

## Key Findings (October 2026 data release)

- **Completions are at 61% of the rate needed** for the 377,000 Accord target: 92,270 dwellings over 8 quarters against a pro-rated 150,800
- DA approvals reach 103% of pro-rated targets across the 43 target LGAs (19 LGAs at or above 100%), but construction approvals reach only 66% (6 LGAs) — a 37-point gap
- **Construction approvals are below half of DA approvals in 10 target LGAs, all in Greater Sydney** (Willoughby 0.15, North Sydney 0.19, Randwick 0.29 …), consistent with the apartment feasibility gap reported by industry
- Completions rose 16% year-on-year (42,725 in 2024-25 to 49,545 in 2025-26); 53% of completions are non-house dwellings
- Regional NSW (85 non-target LGAs) tracking via remainder method against its 55,000 target

Pipeline totals and greenfield capacity are shown as KPI tiles rather than findings.

## Reconciliation checks

The script asserts on every run that the LGA and SA2 sheets give identical statewide totals for every month of all three pipeline stages, that the targets sum to 377,000, that all 43 target LGAs are matched, and that completions are non-negative. Data-quality observations (duplicate rows, negative lot counts, extra rows in the construction sheet) and as-at dates are computed from the data sheet rather than hard-coded.

## Limitations

- Pro-rating assumes a flat delivery trajectory across the five-year target period
- The construction-to-DA ratio is indicative only: approvals are not split by dwelling type, and the construction series includes CDCs that never enter the DA series, so ratios above 1.0 occur and the ratio is not a true conversion rate. Joining ABS building approvals by dwelling type at LGA level (houses vs other residential, published monthly) would confirm the apartment-feasibility inference directly
- The data sheet does not state whether the lodged / approved-for-development series include complying development certificates (CDCs); ABS building approvals in NSW typically include both construction certificates and CDCs, so the construction series is not strictly a subset of the DA series
- ABS building approvals are subject to revision, generally within 12–18 months
- The three greenfield measures have different as-at dates (capacity June 2026, subdivision audit December 2025, new lots to September 2026) and are not a numerator/denominator pair

## Tools

- **Python 3** (openpyxl, standard library) — data extraction, analysis and report generation; no other dependencies
- **HTML/CSS/JavaScript** (Chart.js 4.4.4, embedded) — interactive dashboard
- **DPHI open data** — source dataset (CC BY)
