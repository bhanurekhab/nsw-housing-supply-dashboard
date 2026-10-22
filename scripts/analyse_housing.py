#!/usr/bin/env python3
"""
NSW Housing Supply Pipeline Dashboard
Analyses DPHI housing supply data and generates an interactive HTML report.

Data source: NSW Department of Planning, Housing and Infrastructure
             Housing Supply Dashboard Data Sheet (Creative Commons Attribution)
             https://data.nsw.gov.au/data/dataset/housing-supply

Author: Bhanu Rekha Basireddy
Date:   October 2026
"""

import csv
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from openpyxl import load_workbook

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BASE_DIR / "data" / "housingsupplydashboard_datasheet.xlsx"
TEMPLATE_DIR = BASE_DIR / "templates"
OUTPUT_DIR = BASE_DIR / "output"


# ---------------------------------------------------------------------------
# 1. Extract data from Excel
# ---------------------------------------------------------------------------

def load_lga_sheet(wb, sheet_name):
    """Load a monthly LGA sheet into {lga: {month: count}}.

    Returns (months, data, null_count) where null_count is the number of
    null cells converted to 0.
    """
    ws = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    headers = list(rows[0])
    months = headers[1:]
    data = {}
    null_count = 0
    for row in rows[1:]:
        lga = row[0]
        if lga is None:
            continue
        data[lga] = {}
        for i, m in enumerate(months):
            val = row[i + 1]
            if val is None:
                null_count += 1
                print(f"  Warning: null cell in {sheet_name} for {lga}, {m} — treated as 0",
                      file=sys.stderr)
                data[lga][m] = 0
            else:
                data[lga][m] = int(val)
    return months, data, null_count


def load_sa2_monthly_totals(wb, sheet_name):
    """Load an SA2 sheet and return {month: total_across_all_SA2s}.

    Used for cross-checking against LGA-level totals."""
    ws = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    headers = list(rows[0])
    months = headers[1:]
    totals = {m: 0 for m in months}
    for row in rows[1:]:
        if row[0] is None:
            continue
        for i, m in enumerate(months):
            val = row[i + 1]
            if val is not None:
                totals[m] += int(val)
    return totals


def load_completions(wb):
    """Load quarterly completions."""
    _dt = datetime
    ws = wb["Completions (NSW)"]
    rows = list(ws.iter_rows(values_only=True))
    completions = []
    for row in rows[1:]:
        date_val, dwelling_type, dwellings = row[0], row[1], row[2]
        # Normalise date to "d/mm/yyyy" string regardless of cell type
        if isinstance(date_val, _dt):
            date_str = f"{date_val.day}/{date_val.month:02d}/{date_val.year}"
        elif isinstance(date_val, str):
            date_str = date_val
        else:
            print(f"  Warning: unexpected date type {type(date_val).__name__} in Completions: {date_val!r}",
                  file=sys.stderr)
            continue
        completions.append({
            "date": date_str,
            "type": dwelling_type,
            "count": int(dwellings) if dwellings else 0,
        })
    return completions


def load_index_dates(wb):
    """Load as-at dates from the Index tab."""
    ws = wb["Index"]
    dates = {}
    for row in ws.iter_rows(values_only=True):
        tab_name = str(row[0]).strip() if row[0] else ""
        timeframe = str(row[2]).strip() if len(row) > 2 and row[2] else ""
        if tab_name and timeframe and tab_name != "Contents (tabs)":
            dates[tab_name] = timeframe
    return dates


def load_targets(wb):
    """Load LGA housing targets."""
    ws = wb["Targets"]
    rows = list(ws.iter_rows(values_only=True))
    targets = {}
    for row in rows[1:]:
        lga, target = row[0], row[1]
        if lga and target:
            targets[str(lga).strip()] = int(target)
    return targets


def load_greenfield(wb):
    """Load greenfield capacity and subdivision data."""
    # Capacity
    ws = wb["Greenfield Precincts Capacity"]
    capacity = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue
        capacity.append({
            "precinct": row[0],
            "growth_area": row[1],
            "capacity": int(row[2]) if row[2] else 0,
        })

    # Subdivision audit
    ws = wb["Greenfield Subdivision Audit"]
    subdivision = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue
        subdivision.append({
            "precinct": row[0],
            "growth_area": row[1],
            "status": row[2],
            "lots": int(row[3]) if row[3] else 0,
        })

    # New lots
    ws = wb["Greenfield New Lots"]
    new_lots = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue
        new_lots.append({
            "precinct": row[0],
            "growth_area": row[1],
            "type": row[2],
            "lots": int(row[3]) if row[3] else 0,
        })

    return capacity, subdivision, new_lots


# ---------------------------------------------------------------------------
# 2. Compute analytics
# ---------------------------------------------------------------------------

def compute_pipeline_totals(months, lodged, approved_dev, approved_con):
    """Monthly statewide totals for each pipeline stage."""
    pipeline = {"months": list(months), "lodged": [], "approved_dev": [], "approved_con": []}
    for m in months:
        pipeline["lodged"].append(sum(lodged[lga].get(m, 0) for lga in lodged))
        pipeline["approved_dev"].append(sum(approved_dev[lga].get(m, 0) for lga in approved_dev))
        # approved_con may have fewer months — use None (not 0) for absent months
        has_con = any(m in approved_con[lga] for lga in approved_con)
        if has_con:
            pipeline["approved_con"].append(sum(approved_con[lga].get(m, 0) for lga in approved_con))
        else:
            pipeline["approved_con"].append(None)
    return pipeline



def compute_completions_quarterly(completions):
    """Structure completions by quarter."""
    # Parse dates into quarter labels
    quarters = []
    houses = []
    other = []
    # Completions come in pairs: House then Other for each date
    seen = {}
    for c in completions:
        # date like "1/09/2024"
        parts = c["date"].split("/")
        if len(parts) == 3:
            month_num = int(parts[1])
            year = int(parts[2])
        else:
            continue

        # Map to FY quarter
        if month_num in (7, 8, 9):
            q_label = f"Q1 {year}-{str(year+1)[2:]}"
        elif month_num in (10, 11, 12):
            q_label = f"Q2 {year}-{str(year+1)[2:]}"
        elif month_num in (1, 2, 3):
            q_label = f"Q3 {year-1}-{str(year)[2:]}"
        elif month_num in (4, 5, 6):
            q_label = f"Q4 {year-1}-{str(year)[2:]}"
        else:
            continue

        if q_label not in seen:
            seen[q_label] = {"house": 0, "other": 0}
        if c["type"] == "House":
            seen[q_label]["house"] += c["count"]
        else:
            seen[q_label]["other"] += c["count"]

    # Sort chronologically by FY then quarter number
    def q_sort_key(label):
        # "Q1 2024-25" -> (2024, 1)
        parts = label.split()
        q_num = int(parts[0][1])
        fy_start = int(parts[1].split("-")[0])
        return (fy_start, q_num)

    for q in sorted(seen.keys(), key=q_sort_key):
        quarters.append(q)
        houses.append(seen[q]["house"])
        other.append(seen[q]["other"])

    return {"quarters": quarters, "houses": houses, "other": other}



def compute_lga_target_progress(months, series_by_lga, targets,
                                filter_months=False):
    """For target LGAs, compute cumulative approvals as % of 5-year target.

    When filter_months is True the month list is narrowed to those that have
    data in at least one LGA (construction data may cover fewer months than
    the DA data).  Returns (progress_list, n_months_used).
    """
    if filter_months:
        months = [m for m in months
                  if any(m in series_by_lga[lga] for lga in series_by_lga)]
    n_months = len(months)
    progress = []
    for lga, target in sorted(targets.items(), key=lambda x: x[1], reverse=True):
        if lga in series_by_lga:
            cumulative = sum(series_by_lga[lga].get(m, 0) for m in months)
            # Pro-rate: target is 5 years (60 months), data covers n_months
            expected_rate = target / 60 * n_months
            pct_of_target = (cumulative / target * 100) if target > 0 else 0
            pct_of_prorated = (cumulative / expected_rate * 100) if expected_rate > 0 else 0
            progress.append({
                "lga": lga,
                "cumulative": cumulative,
                "target_5yr": target,
                "prorated_target": round(expected_rate),
                "pct_of_target": round(pct_of_target, 1),
                "pct_of_prorated": round(pct_of_prorated, 1),
            })
    return progress, n_months


def compute_greenfield_summary(capacity, subdivision, new_lots):
    """Summarise greenfield data by growth area."""
    areas = {}
    _default = lambda: {"capacity": 0, "approved": 0, "assessment": 0, "new_lots": 0}
    for c in capacity:
        ga = c["growth_area"]
        areas.setdefault(ga, _default())["capacity"] += c["capacity"]
    for s in subdivision:
        ga = s["growth_area"]
        entry = areas.setdefault(ga, _default())
        if s["status"] == "Subdivision Approved":
            entry["approved"] += s["lots"]
        else:
            entry["assessment"] += s["lots"]
    for nl in new_lots:
        ga = nl["growth_area"]
        areas.setdefault(ga, _default())["new_lots"] += nl["lots"]

    # Track which growth areas have subdivision audit rows
    areas_with_audit = set()
    for s in subdivision:
        areas_with_audit.add(s["growth_area"])

    result = []
    for ga in sorted(areas.keys()):
        d = areas[ga]
        result.append({
            "growth_area": ga,
            "capacity": d["capacity"],
            "lots_approved": d["approved"],
            "lots_in_assessment": d["assessment"],
            "new_lots_created": d["new_lots"],
            "has_audit_data": ga in areas_with_audit,
        })
    return result


def compute_data_quality_notes(new_lots, greenfield_summary):
    """Derive data-quality observations from the greenfield sheets.

    Returns a list of plain-text notes.  Computed rather than hard-coded so
    they stay correct when the data sheet is refreshed.
    """
    notes = []

    # Duplicate (precinct, type) rows in the New Lots sheet
    seen = {}
    for nl in new_lots:
        key = (nl["precinct"], nl["type"])
        seen.setdefault(key, []).append(nl["lots"])
    dups = [(k, v) for k, v in seen.items() if len(v) > 1]
    for (precinct, lot_type), vals in dups:
        notes.append(
            f"The Greenfield New Lots sheet contains {len(vals)} rows for {precinct} "
            f"({lot_type}) with values {', '.join(str(v) for v in vals)}; "
            f"all rows are summed.")

    # Precincts with net negative new lots
    neg = [(nl["precinct"], nl["lots"]) for nl in new_lots if nl["lots"] < 0]
    if neg:
        neg_strs = [f"{p} {v:+,}".replace("+", "") for p, v in neg]
        neg_areas = [(g["growth_area"], g["new_lots_created"]) for g in greenfield_summary
                     if g["new_lots_created"] < 0]
        area_note = ""
        if neg_areas:
            area_strs = [f"{ga} at {v:,}" for ga, v in neg_areas]
            area_note = (f" At growth-area level this leaves {', '.join(area_strs)}, "
                         f"shown as 0 in the chart and as the negative value in the table.")
        notes.append(
            f"{len(neg)} precinct{'s' if len(neg) != 1 else ''} carr{'y' if len(neg) != 1 else 'ies'} "
            f"net negative new-lot figures ({', '.join(neg_strs)}), where demolitions or lot "
            f"consolidations exceed new lots created.{area_note}")

    return notes


def compute_feasibility_gap(target_progress, target_progress_con):
    """Compute construction÷DA ratio for each target LGA.

    A low ratio (DA-heavy, construction-light) signals feasibility risk —
    approvals exist but projects aren't starting.  A ratio near or above 1
    means construction is keeping pace with DAs.
    """
    con_lookup = {t["lga"]: t for t in target_progress_con}
    ratios = []
    for t in target_progress:
        c = con_lookup.get(t["lga"])
        if c and t["cumulative"] > 0:
            ratio = c["cumulative"] / t["cumulative"]
            ratios.append({
                "lga": t["lga"],
                "da_pct": t["pct_of_prorated"],
                "con_pct": c["pct_of_prorated"],
                "con_da_ratio": round(ratio, 2),
                "da_approvals": t["cumulative"],
                "con_approvals": c["cumulative"],
                "target_5yr": t["target_5yr"],
            })
    ratios.sort(key=lambda r: r["con_da_ratio"])
    return ratios


def compute_finding_stats(pipeline, completions_q,
                          target_progress, target_progress_con, n_con_months,
                          greenfield_summary, capacity_raw, new_lots_raw, targets,
                          n_total_lgas=128):
    """Compute all statistics needed for key findings (pure numbers, no prose).

    Returns a dict of numeric values consumed by narrate_findings().
    """
    s = {}

    # Pipeline totals
    s["total_lodged"] = sum(pipeline["lodged"])
    s["total_approved_dev"] = sum(pipeline["approved_dev"])
    s["total_approved_con"] = sum(v for v in pipeline["approved_con"] if v is not None)
    s["n_months"] = len(pipeline["months"])
    s["n_da_months"] = s["n_months"]
    s["n_con_months"] = n_con_months

    # Completions
    s["total_houses"] = sum(completions_q["houses"])
    s["total_other"] = sum(completions_q["other"])
    s["total_completions"] = s["total_houses"] + s["total_other"]
    s["n_comp_quarters"] = len(completions_q["quarters"])
    s["total_target"] = sum(targets.values())

    # Target progress — weighted averages
    s["n_target_lgas"] = len(target_progress)
    s["n_on_track_da"] = sum(1 for t in target_progress if t["pct_of_prorated"] >= 100)
    s["n_on_track_con"] = sum(1 for t in target_progress_con if t["pct_of_prorated"] >= 100)

    total_cum_da = sum(t["cumulative"] for t in target_progress)
    total_prorated_da = sum(t["prorated_target"] for t in target_progress)
    s["weighted_da"] = (total_cum_da / total_prorated_da * 100) if total_prorated_da > 0 else 0

    total_cum_con = sum(t["cumulative"] for t in target_progress_con)
    total_prorated_con = sum(t["prorated_target"] for t in target_progress_con)
    s["weighted_con"] = (total_cum_con / total_prorated_con * 100) if total_prorated_con > 0 else 0

    # Completions vs target
    if s["total_target"] > 0 and s["n_comp_quarters"] > 0:
        s["prorated_target_completions"] = s["total_target"] / 20 * s["n_comp_quarters"]
        s["completions_pct"] = s["total_completions"] / s["prorated_target_completions"] * 100

    # DA vs construction gap (from rounded display figures so reader's arithmetic matches)
    s["da_display"] = round(s["weighted_da"])
    s["con_display"] = round(s["weighted_con"])
    s["gap_display"] = s["da_display"] - s["con_display"]

    # Feasibility gap
    s["feasibility"] = compute_feasibility_gap(target_progress, target_progress_con)
    if s["feasibility"]:
        s["bottom_5"] = s["feasibility"][:5]
        s["top_5"] = list(reversed(s["feasibility"][-5:]))
        s["below_half"] = [r["lga"] for r in s["feasibility"] if r["con_da_ratio"] < 0.5]
        outside_sydney = {"Central Coast", "Newcastle", "Lake Macquarie", "Maitland", "Cessnock",
                          "Port Stephens", "Wollongong", "Shellharbour", "Kiama", "Shoalhaven"}
        s["feasibility_all_sydney"] = not (set(s["below_half"]) & outside_sydney)

    # Completion trend
    s["other_pct"] = s["total_other"] / s["total_completions"] * 100 if s["total_completions"] > 0 else 0
    quarterly_totals = [h + o for h, o in zip(completions_q["houses"], completions_q["other"])]
    s["fy_detail"] = ""
    if s["n_comp_quarters"] >= 8 and completions_q["quarters"][0].startswith("Q1"):
        fy1_total = sum(quarterly_totals[0:4])
        fy2_total = sum(quarterly_totals[4:8])
        fy1_label = completions_q["quarters"][0].split()[1]
        fy2_label = completions_q["quarters"][4].split()[1]
        fy_change = (fy2_total - fy1_total) / fy1_total * 100 if fy1_total > 0 else 0
        s["fy_detail"] = (f" Full-year completions rose from {fy1_total:,} in {fy1_label} "
                          f"to {fy2_total:,} in {fy2_label} (up {abs(fy_change):.0f}%).")

    # Human-readable quarter end: "Q4 2025-26" → "June 2026"
    q_end_map = {"Q1": "September", "Q2": "December", "Q3": "March", "Q4": "June"}
    last_q_label = completions_q["quarters"][-1]
    last_q_parts = last_q_label.split()
    s["last_q_readable"] = last_q_label  # fallback
    if len(last_q_parts) == 2 and last_q_parts[0] in q_end_map:
        fy_end_year = last_q_parts[1].split("-")
        if last_q_parts[0] in ("Q3", "Q4") and len(fy_end_year) == 2:
            end_year = fy_end_year[0][:2] + fy_end_year[1]
        else:
            end_year = fy_end_year[0]
        s["last_q_readable"] = f"{q_end_map[last_q_parts[0]]} {end_year}"

    # Regional NSW
    s["regional_target"] = targets.get("Other regional", 0)
    if s["regional_target"] > 0:
        non_target_da = s["total_approved_dev"] - total_cum_da
        prorated_regional_da = s["regional_target"] / 60 * s["n_da_months"]
        s["regional_da_pct"] = (non_target_da / prorated_regional_da * 100) if prorated_regional_da > 0 else 0
        non_target_con = s["total_approved_con"] - total_cum_con
        prorated_regional_con = s["regional_target"] / 60 * n_con_months
        s["regional_con_pct"] = (non_target_con / prorated_regional_con * 100) if prorated_regional_con > 0 else 0
        s["n_non_target"] = n_total_lgas - len(target_progress)

    # Greenfield KPI stats
    s["total_capacity"] = sum(g["capacity"] for g in greenfield_summary)
    s["total_new_lots"] = sum(g["new_lots_created"] for g in greenfield_summary)

    # Over-capacity precinct count (used in greenfield chart description)
    cap_by_precinct = {c["precinct"]: c["capacity"] for c in capacity_raw}
    lots_by_precinct = {}
    for nl in new_lots_raw:
        lots_by_precinct[nl["precinct"]] = lots_by_precinct.get(nl["precinct"], 0) + nl["lots"]
    over_capacity = [p for p in cap_by_precinct
                     if lots_by_precinct.get(p, 0) > cap_by_precinct[p] and cap_by_precinct[p] > 0]
    s["n_over_capacity"] = len(over_capacity)

    return s


def narrate_findings(s):
    """Convert computed stats into prose findings.

    Takes the dict returned by compute_finding_stats().
    Returns (findings_list, feasibility_list).
    """
    findings = []

    # --- 1. Completions vs targets (the headline) ---
    if s["total_target"] > 0 and s["n_comp_quarters"] > 0:
        findings.append({
            "finding": f"Completions at {s['completions_pct']:.0f}% of the rate needed for the {s['total_target']:,} Accord target",
            "detail": (f"{s['total_completions']:,} dwellings completed over {s['n_comp_quarters']} quarters "
                       f"against a pro-rated target of {s['prorated_target_completions']:,.0f}. "
                       f"Construction approvals, the closer proxy for near-term delivery, "
                       f"reach only {s['weighted_con']:.0f}% of pro-rated targets across the "
                       f"{s['n_target_lgas']} target LGAs.")
        })

    # --- 2. DA vs construction gap ---
    if s["n_target_lgas"] > 0:
        findings.append({
            "finding": (f"DA approvals at {s['da_display']}% of target but construction at only "
                        f"{s['con_display']}% — a {s['gap_display']}-point gap"),
            "detail": (f"Across {s['n_target_lgas']} target LGAs, {s['n_on_track_da']} are at or above "
                       f"100% on DA approvals ({s['n_da_months']} months) but only {s['n_on_track_con']} "
                       f"on construction approvals ({s['n_con_months']} months of ABS building approvals). "
                       f"Because approvals precede completions by one to three years, "
                       f"the DA figure overstates readiness to deliver.")
        })

    # --- 3. Apartment feasibility gap ---
    feasibility = s.get("feasibility", [])
    if feasibility:
        bottom_strs = [f"{r['lga']} ({r['con_da_ratio']:.2f})" for r in s["bottom_5"]]
        top_strs = [f"{r['lga']} ({r['con_da_ratio']:.2f})" for r in s["top_5"]]
        where = ", all in Greater Sydney" if s.get("feasibility_all_sydney") else ""
        findings.append({
            "finding": (f"Construction approvals are below half of DA approvals in "
                        f"{len(s['below_half'])} target LGAs{where}"),
            "detail": (f"Lowest construction-to-DA ratios: {', '.join(bottom_strs)}. "
                       f"Highest: {', '.join(top_strs)}. The low-ratio councils are established "
                       f"Sydney areas where new supply is mostly apartments; this is consistent "
                       f"with the apartment feasibility gap reported by industry (Property Council "
                       f"NSW, Feb 2026, citing Urbis: 75% of apartments approved in metropolitan "
                       f"Sydney since 2020 had not progressed to construction). The data sheet does "
                       f"not split approvals by dwelling type, so the ratio is indicative only; "
                       f"ratios above 1.0 occur because ABS construction approvals include CDCs, "
                       f"which bypass the DA series.")
        })

    # --- 4. Completion trend ---
    findings.append({
        "finding": (f"{s['total_completions']:,} dwellings completed — {s['other_pct']:.0f}% are "
                    f"non-house dwellings (apartments, townhouses and similar)"),
        "detail": (f"{s['total_houses']:,} houses and {s['total_other']:,} other dwellings "
                   f"to the {s['last_q_readable']} quarter.{s['fy_detail']}")
    })

    # --- 5. Regional NSW ---
    if s["regional_target"] > 0:
        findings.append({
            "finding": (f"Regional NSW at {s['regional_da_pct']:.0f}% DA / "
                        f"{s['regional_con_pct']:.0f}% construction against its "
                        f"{s['regional_target']:,} target"),
            "detail": (f"The {s['n_non_target']} non-target LGAs are the regional remainder "
                       f"(all {s['n_target_lgas']} target councils have individual targets). "
                       f"The regional figure is derived by subtracting the 43 target-LGA totals "
                       f"from the statewide pipeline; it therefore includes all non-target councils "
                       f"and any dwellings not attributable to a target LGA.")
        })

    return findings, feasibility

def compute_pipeline_caveats(pipeline):
    """Detect outlier months in the pipeline series and return caveat HTML.

    Uses median-based detection with series-appropriate thresholds.
    The text states only what the data shows — timing and magnitude
    — without attributing cause.
    """
    from statistics import median as _median

    months = pipeline["months"]
    lodged = pipeline["lodged"]
    dev = pipeline["approved_dev"]
    caveats = []

    def _outliers(values, labels, threshold=1.5):
        """Return [(month, value), ...] for months exceeding threshold× the median."""
        med = _median(values)
        return [(labels[i], values[i]) for i in range(len(values))
                if values[i] > med * threshold]

    # Lodgement outliers (2× median — higher bar; lodgement counts are noisier)
    lodg_out = _outliers(lodged, months, threshold=2)
    if lodg_out:
        parts = ", ".join(f"{m}: {v:,}" for m, v in lodg_out)
        if len(lodg_out) == 1 and lodg_out[0][0] == months[-1]:
            # Single spike in the latest month — flag as provisional
            caveats.append(
                f"The {lodg_out[0][0]} lodgement figure ({lodg_out[0][1]:,}) "
                f"is a single month in the latest data release and is "
                f"subject to revision.")
        else:
            caveats.append(
                f"Lodgement outliers: {parts} "
                f"(each exceeds 2× the monthly median).")

    # Development-approval outliers
    dev_out = _outliers(dev, months)
    if dev_out:
        parts = ", ".join(f"{m}: {v:,}" for m, v in dev_out)
        fy_end = [m for m, _ in dev_out if m.endswith("-06")]
        if fy_end:
            caveats.append(
                f"Development-approval outliers: {parts}. "
                f"The timing of {', '.join(fy_end)} is consistent with "
                f"financial-year-end determination clearance.")
        else:
            caveats.append(
                f"Development-approval outliers: {parts} "
                f"(each exceeds 1.5× the monthly median).")

    if not caveats:
        return ""
    return "\n    " + "\n    ".join(caveats)




# ---------------------------------------------------------------------------
# 3. Build HTML report
# ---------------------------------------------------------------------------

def compute_file_hash(path):
    """Return SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def build_html(data_obj, findings, data_hash, n_over_capacity=0, total_nulls=0,
               unincorp_info=None, index_dates=None, dq_notes=None):
    """Generate a self-contained HTML dashboard."""
    chartjs_path = TEMPLATE_DIR / "chartjs.min.js"
    styles_path = TEMPLATE_DIR / "styles.css"
    render_js_path = TEMPLATE_DIR / "render.js"

    for tpl in (chartjs_path, styles_path, render_js_path):
        if not tpl.exists():
            raise FileNotFoundError(f"Required template missing: {tpl}")

    chartjs = chartjs_path.read_text()
    styles = styles_path.read_text()
    render_js = render_js_path.read_text()

    data_json = json.dumps(data_obj, indent=2)

    # Computed narrative values
    n_growth_areas = len(data_obj["greenfield"])
    n_target_lgas = len(data_obj["target_progress"])
    total_target = sum(t["target_5yr"] for t in data_obj["target_progress"])
    n_pipeline_months = len(data_obj["pipeline"]["months"])
    first_month = data_obj["pipeline"]["months"][0]
    last_month = data_obj["pipeline"]["months"][-1]
    n_con = data_obj["n_con_months"]

    pipeline_caveat_html = compute_pipeline_caveats(data_obj["pipeline"])

    # Index-tab timeframes, with only the leading word lower-cased ("As at June 2026" -> "as at June 2026")
    def _tf(tab):
        t = (index_dates or {}).get(tab, "see Index tab")
        return t[0].lower() + t[1:] if t else "see Index tab"

    dq_items = "".join(f"\n        <li>{n}</li>" for n in (dq_notes or []))

    # Unincorporated NSW row info (computed from raw construction LGA data)
    if unincorp_info:
        unincorp_note = (f'The construction approvals sheet includes an '
                         f'&ldquo;{unincorp_info["lga"]}&rdquo; row '
                         f'({unincorp_info["total"]:,} dwelling{"s" if unincorp_info["total"] != 1 else ""}) '
                         f'absent from other pipeline sheets; included in statewide totals.')
    else:
        unincorp_note = ""

    # Build findings HTML
    findings_html = ""
    for i, f in enumerate(findings, 1):
        findings_html += f'''
        <div class="finding">
            <h3>{i}. {f["finding"]}</h3>
            <p>{f["detail"]}</p>
        </div>'''

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NSW Housing Supply Pipeline Dashboard</title>
<style>
{styles}
</style>
<script>{chartjs}</script>
</head>
<body>
<div class="report-container">

<header class="report-header">
    <h1>NSW Housing Supply Pipeline Dashboard</h1>
    <p class="subtitle">An independent analysis of DPHI open data on dwelling approvals, completions and targets</p>
    <p class="meta">
        Independent analysis: Bhanu Rekha Basireddy (not affiliated with or endorsed by DPHI) &middot;
        Data: NSW Department of Planning, Housing and Infrastructure &middot;
        <a href="https://data.nsw.gov.au/data/dataset/housing-supply">Housing Supply Dashboard Data Sheet</a>
        (Creative Commons Attribution; version 3.0 Australia per data.gov.au mirror)
    </p>
</header>

<section class="findings-section">
    <h2>Key findings</h2>
    {findings_html}
</section>

<section class="chart-section">
    <h2>Pipeline overview</h2>
    <p class="chart-description">Monthly dwelling counts at three pipeline stages:
    lodged for development (DA applications via the Planning Portal),
    approved for development (DAs determined), and approved for construction
    (ABS building approvals; per ABS methodology these include both
    construction certificates and complying development certificates).
    Data covers {first_month} to {last_month}
    ({n_pipeline_months} months).{pipeline_caveat_html}</p>
    <div class="chart-container" style="height:360px">
        <canvas id="pipelineChart"></canvas>
    </div>
</section>

<section class="chart-section">
    <h2>Dwelling completions</h2>
    <p class="chart-description">Quarterly dwelling completions across NSW, split by
    houses and other dwelling types (apartments, townhouses, etc.).
    DPHI&rsquo;s own split is &ldquo;detached / multi-unit&rdquo;, which maps to House / Other
    in the data sheet.
    Source: ABS data via DPHI.</p>
    <div class="chart-container" style="height:320px">
        <canvas id="completionsChart"></canvas>
    </div>
</section>

<section class="chart-section">
    <h2>Target LGA progress: DA vs construction approvals</h2>
    <p class="chart-description">Top 15 target LGAs (by five-year completion target) showing
    both DA approvals ({n_pipeline_months} months) and construction approvals
    ({n_con} months of ABS building approvals) as a percentage of their
    pro-rated target.  Construction approvals are a closer proxy for delivery.</p>
    <div class="chart-container" style="height:440px">
        <canvas id="targetChart"></canvas>
    </div>
</section>

<section class="chart-section">
    <h2>Construction-to-DA ratio by LGA</h2>
    <p class="chart-description">Construction approvals as a share of DA approvals for each
    target LGA.  A low ratio signals feasibility risk: DAs exist but projects are not
    converting to construction starts.  Ratios above 1.0 occur because ABS construction
    approvals include complying development certificates (CDCs), which bypass the DA
    pathway; the ratio therefore ranks LGAs but is not a true conversion rate.</p>
    <div class="chart-container" style="height:920px">
        <canvas id="feasibilityChart"></canvas>
    </div>
</section>

<section class="chart-section">
    <h2>Greenfield capacity and lot creation</h2>
    <p class="chart-description">Two panels: (left) planned dwelling capacity by growth area;
    (right) new lots created and lots with subdivision approval.
    {f'New lots exceed capacity in {n_over_capacity} precincts, suggesting the figure is residual rather than total yield.' if n_over_capacity > 0 else ''}
    These measures have different as-at dates and are not a numerator/denominator pair.</p>
    <div class="greenfield-panels">
        <div class="chart-container" style="height:360px; flex:1">
            <canvas id="greenfieldCapChart"></canvas>
        </div>
        <div class="chart-container" style="height:360px; flex:1">
            <canvas id="greenfieldLotsChart"></canvas>
        </div>
    </div>
</section>

<section class="notes-section">
    <h2>Methodology and sources</h2>
    <h3>Data source</h3>
    <p>NSW Department of Planning, Housing and Infrastructure,
    <a href="https://data.nsw.gov.au/data/dataset/housing-supply">Housing Supply Dashboard Data Sheet</a>,
    licensed under Creative Commons Attribution (version 3.0 Australia per data.gov.au mirror).
    The dataset is published monthly and covers dwelling activity from July 2024 onwards.
    This dashboard is an independent reuse of the published data sheet. Figures, groupings
    and interpretations are the analyst&rsquo;s own and may differ from DPHI&rsquo;s official
    Housing Supply Dashboard.</p>
    <p><strong>Key references:</strong></p>
    <ul>
        <li><a href="https://www.planning.nsw.gov.au/policy-and-legislation/housing/housing-targets">DPHI Housing Targets</a>
        &mdash; framework overview, {n_target_lgas} LGA targets, {total_target:,} statewide total; confirms these are completion targets.</li>
        <li><a href="https://www.planning.nsw.gov.au/policy-and-legislation/housing/housing-targets/frequently-asked-questions-housing-targets">DPHI Housing Targets FAQ</a>
        &mdash; 55,000 regional target and other detail.</li>
        <li><a href="https://www.abs.gov.au/methodologies/building-approvals-australia-methodology/aug-2026">ABS Building Approvals methodology</a>
        &mdash; scope of construction approvals (CCs and CDCs for NSW), revision policy (typically within 12&ndash;18 months).</li>
    </ul>

    <h3>Pipeline stages</h3>
    <p><em>Stage definitions below are as understood by the analyst; the data sheet does not define these terms.
    The published <a href="https://datasets.seed.nsw.gov.au/dataset/housing-supply/resource/data_quality_report/pdf">Data Quality Statement</a>
    on data.nsw.gov.au should be checked for authoritative definitions and for whether CDCs
    are included in the DA series.</em></p>
    <ul>
        <li><strong>Lodged for development</strong> &mdash; dwelling applications submitted via the NSW Planning Portal (source: DPHI). May include state-significant development in addition to council-determined DAs.</li>
        <li><strong>Approved for development</strong> &mdash; development applications determined (approved). May include state-significant development determined by the Minister or Independent Planning Commission.</li>
        <li><strong>Approved for construction</strong> &mdash; ABS building approvals data via DPHI; per ABS methodology this includes both construction certificates (CCs) and complying development certificates (CDCs). ABS states that building approvals are revised, typically within 12&ndash;18 months of the original release.</li>
        <li><strong>Completions</strong> &mdash; dwellings completed (ABS data via DPHI), reported quarterly</li>
    </ul>
    <p>{unincorp_note}</p>

    <h3>Housing targets</h3>
    <p>Five-year dwelling completion targets are set for {n_target_lgas} LGAs and regional NSW under the NSW Government&rsquo;s
    housing targets framework. Pro-rated progress is calculated by comparing cumulative approvals
    against the linear share of the five-year completion target that corresponds to the elapsed reporting period.
    Two measures are shown: DA approvals ({n_pipeline_months} of 60 months)
    and construction approvals ({n_con} of 60 months, ABS building approvals
    which per ABS methodology include both CCs and CDCs). The data sheet does not state
    whether the DA series includes CDCs. Weighted averages weight each LGA
    by its target size; the chart shows the top 15 LGAs by target.</p>
    <p><strong>Regional NSW:</strong> the &ldquo;Other regional&rdquo; target ({total_target - sum(t['target_5yr'] for t in data_obj['target_progress']):,} dwellings)
    covers all councils without an individual target. Progress is estimated by subtracting the
    {n_target_lgas} target-LGA approval totals from the statewide pipeline. This remainder method
    attributes every non-target-LGA approval to the regional pool; it is an approximation, not a
    direct count of approvals within specific regional councils.</p>

    <p><strong>Important caveat:</strong> because approvals precede completions by one to three years,
    approval rates need to run well ahead of a linear completions path in the early years for the
    target to be met. Reaching 100% of the pro-rated share is not evidence of being on track;
    it is the minimum that would be expected if the pipeline had no lead time at all.
    Linear pro-rating also assumes a flat delivery trajectory across the five-year period,
    which is a simplifying assumption.</p>

    <h3>Construction-to-DA ratio</h3>
    <p>The ratio chart divides each LGA&rsquo;s cumulative construction approvals
    by its cumulative DA approvals. A ratio below 1.0 means DA approvals are outrunning construction
    starts. Ratios above 1.0 occur because ABS construction approvals include complying development
    certificates (CDCs), which bypass the DA pathway entirely; the ratio therefore ranks LGAs by
    relative conversion but is not a true conversion rate.
    The concentration of low ratios in inner-city and metropolitan councils is consistent
    with the &ldquo;apartment feasibility gap&rdquo; widely reported in industry analysis: the
    <a href="https://www.propertycouncil.com.au/media-releases/property-council-calls-for-nsw-budget-support-to-unlock-stalled-apartment-construction">Property Council NSW</a>
    (19 Feb 2026, citing Urbis) reported that 75% of apartments approved in metropolitan
    Sydney since 2020 had not progressed to construction. The data sheet does not split
    approvals by dwelling type, so this interpretation is inferred from LGA geography,
    not measured from the dataset. Joining ABS building approvals by dwelling type
    at LGA level (houses vs other residential, published monthly) would confirm the
    correlation directly.</p>

    <h3>Greenfield data</h3>
    <p>Greenfield precinct capacity, new lot creation and subdivision audit data cover
    {n_growth_areas} growth-area groupings in and around Greater Sydney. As-at dates vary
    (per the dataset Index tab):
    capacity {_tf("Greenfield Precincts Capacity")},
    subdivision audit {_tf("Greenfield Subdivision Audit")},
    new lots {_tf("Greenfield New Lots")},
    and targets {_tf("Targets")}.
    New lots created (cadastral lots and strata units) is a net figure and includes
    negative entries for some precincts.</p>

    <h3>Data quality notes</h3>
    <ul>{dq_items}
        {"<li>The pipeline sheets (lodged, dev approved, construction approved) contain " + str(total_nulls) + " null cell(s) converted to zero. Totals may be understated if these represent missing data rather than true zeros.</li>" if total_nulls > 0 else "<li>No null cells in the pipeline sheets (lodged, dev approved, construction approved).</li>"}
        <li>LGA-level and SA2-level sheets reconcile exactly, month by month, for all three
        pipeline stages (checked by the script on each run).</li>
    </ul>

    <h3>Analysis pipeline</h3>
    <p>All findings, charts and tables are generated programmatically from the source
    data using Python. Chart.js v4.4.4 is embedded inline; no internet connection
    is needed to view the report.</p>
    <p>Narrative values (growth-area count, LGA count, target totals, as-at dates,
    Unincorporated NSW total, data-quality observations) are computed from the data
    sheet on each run. The release used is identified by the SHA-256 hash below.</p>
    <p class="data-hash">Data sheet SHA-256: <code>{data_hash}</code></p>
</section>

</div>

<script>
const DATA = {data_json};
{render_js}
</script>
</body>
</html>'''
    return html


# ---------------------------------------------------------------------------
# 4. Write outputs
# ---------------------------------------------------------------------------

def write_csv(path, headers, rows):
    """Write a simple CSV file."""
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)


def main():
    if not DATA_FILE.exists():
        print(f"Error: data file not found at {DATA_FILE}", file=sys.stderr)
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    wb = load_workbook(str(DATA_FILE), read_only=True)

    # Extract
    months_lodged, lodged, nulls_lodged = load_lga_sheet(wb, "Lodged for Development (LGA)")
    months_dev, approved_dev, nulls_dev = load_lga_sheet(wb, "Approved for Development (LGA)")
    months_con, approved_con, nulls_con = load_lga_sheet(wb, "Approved for Construction (LGA)")
    total_nulls = nulls_lodged + nulls_dev + nulls_con
    completions = load_completions(wb)
    targets = load_targets(wb)
    capacity, subdivision, new_lots = load_greenfield(wb)

    # Use common months across pipeline stages (lodged ∩ dev approved)
    months_dev_set = set(months_dev)
    common_months = [m for m in months_lodged if m in months_dev_set]

    # Compute
    pipeline = compute_pipeline_totals(common_months, lodged, approved_dev, approved_con)
    completions_q = compute_completions_quarterly(completions)
    target_progress, _ = compute_lga_target_progress(common_months, approved_dev, targets)
    target_progress_con, n_con_months = compute_lga_target_progress(
        common_months, approved_con, targets, filter_months=True)
    greenfield_summary = compute_greenfield_summary(capacity, subdivision, new_lots)
    index_dates = load_index_dates(wb)
    n_total_lgas = len(approved_dev)

    # Compute Unincorporated NSW info from raw construction LGA data
    unincorp_info = None
    for lga_name, monthly_vals in approved_con.items():
        if "unincorporated" in lga_name.lower():
            unincorp_info = {"lga": lga_name, "total": sum(monthly_vals.values())}
            break
    finding_stats = compute_finding_stats(
        pipeline, completions_q,
        target_progress, target_progress_con, n_con_months,
        greenfield_summary, capacity, new_lots, targets, n_total_lgas)
    findings, feasibility = narrate_findings(finding_stats)
    n_over_capacity = finding_stats["n_over_capacity"]

    # --- Reconciliation checks ---
    # 1. LGA-vs-SA2 monthly cross-check (all three pipeline stages)
    sa2_lodged = load_sa2_monthly_totals(wb, "Lodged for Development (SA2)")
    sa2_dev = load_sa2_monthly_totals(wb, "Approved for Development (SA2)")
    sa2_con = load_sa2_monthly_totals(wb, "Approved for Construction (SA2)")

    for stage_name, lga_data, sa2_totals in [
        ("Lodged", lodged, sa2_lodged),
        ("Dev-approved", approved_dev, sa2_dev),
        ("Construction", approved_con, sa2_con),
    ]:
        for m in sa2_totals:
            lga_total = sum(lga_data[lga].get(m, 0) for lga in lga_data)
            sa2_total = sa2_totals[m]
            assert abs(lga_total - sa2_total) < 1, (
                f"{stage_name} mismatch in {m}: LGA total {lga_total} vs SA2 total {sa2_total}")

    # 2. Targets total 377,000
    # Deliberate hard stop: if DPHI revises the housing targets (e.g. adds LGAs
    # or changes allocations), this assertion forces the analyst to review the
    # downstream pro-rating, regional-remainder calculation, and KPI narratives
    # before the pipeline produces a silently wrong dashboard.
    total_target = sum(targets.values())
    assert total_target == 377_000, f"Targets total {total_target}, expected 377,000"

    # 3. Target progress LGA count matches targets (excluding "Other regional")
    n_target_lgas = len([k for k in targets if k != "Other regional"])
    assert len(target_progress) == n_target_lgas, (
        f"Target progress has {len(target_progress)} LGAs, expected {n_target_lgas}")

    # 4. Completions are non-negative
    for i, q in enumerate(completions_q["quarters"]):
        h = completions_q["houses"][i]
        o = completions_q["other"][i]
        assert h >= 0 and o >= 0, f"Negative completions in {q}: houses={h}, other={o}"

    print("✓ All reconciliation checks passed")

    # Build data object for HTML
    data_obj = {
        "pipeline": pipeline,
        "completions": completions_q,
        "target_progress": sorted(target_progress,
                                   key=lambda t: t["target_5yr"], reverse=True),
        "target_progress_top15": sorted(target_progress,
                                   key=lambda t: t["target_5yr"], reverse=True)[:15],
        "target_progress_con": sorted(target_progress_con,
                                       key=lambda t: t["target_5yr"], reverse=True),
        "n_con_months": n_con_months,
        "greenfield": greenfield_summary,
        "feasibility": feasibility,
        "findings": [{"finding": f["finding"], "detail": f["detail"]} for f in findings],
    }

    # Write outputs
    # 1. Summary JSON
    data_hash = compute_file_hash(DATA_FILE)
    summary = {
        "title": "NSW Housing Supply Pipeline Dashboard",
        "analyst": "Bhanu Rekha Basireddy",
        "date": "October 2026",
        "data_source": "NSW DPHI Housing Supply Dashboard Data Sheet (CC BY)",
        "data_sheet_sha256": data_hash,
        "reporting_period": f"{pipeline['months'][0]} to {pipeline['months'][-1]}",
        "key_findings": findings,
    }
    with open(OUTPUT_DIR / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    # 2. Pipeline CSV
    pipeline_rows = []
    for i, m in enumerate(pipeline["months"]):
        pipeline_rows.append([
            m,
            pipeline["lodged"][i],
            pipeline["approved_dev"][i],
            pipeline["approved_con"][i] if pipeline["approved_con"][i] is not None else "",
        ])
    write_csv(OUTPUT_DIR / "pipeline_monthly.csv",
              ["month", "lodged", "approved_development", "approved_construction"],
              pipeline_rows)

    # 3. Target progress CSV
    con_lookup = {t["lga"]: t for t in target_progress_con}
    target_rows = []
    for t in target_progress:
        c = con_lookup.get(t["lga"], {})
        target_rows.append([
            t["lga"], t["cumulative"], t["target_5yr"], t["prorated_target"],
            t["pct_of_target"], t["pct_of_prorated"],
            c.get("cumulative", ""), c.get("prorated_target", ""),
            c.get("pct_of_prorated", ""),
        ])
    write_csv(OUTPUT_DIR / "target_progress.csv",
              ["lga", "da_approvals", "target_5yr", "da_prorated_target",
               "da_pct_of_target", "da_pct_of_prorated",
               "con_approvals", "con_prorated_target", "con_pct_of_prorated"],
              target_rows)

    # 4. Greenfield CSV
    gf_rows = [[g["growth_area"], g["capacity"], g["lots_approved"],
                 g["lots_in_assessment"], g["new_lots_created"]]
                for g in greenfield_summary]
    write_csv(OUTPUT_DIR / "greenfield_summary.csv",
              ["growth_area", "capacity", "lots_approved", "lots_in_assessment", "new_lots_created"],
              gf_rows)

    # 5. Feasibility CSV
    feas_rows = [[r["lga"], r["da_approvals"], r["con_approvals"],
                   r["da_pct"], r["con_pct"], r["con_da_ratio"], r["target_5yr"]]
                  for r in feasibility]
    write_csv(OUTPUT_DIR / "feasibility_gap.csv",
              ["lga", "da_approvals", "con_approvals",
               "da_pct_prorated", "con_pct_prorated", "con_da_ratio", "target_5yr"],
              feas_rows)

    # 7. Completions CSV
    comp_rows = []
    for i, q in enumerate(completions_q["quarters"]):
        comp_rows.append([q, completions_q["houses"][i], completions_q["other"][i],
                          completions_q["houses"][i] + completions_q["other"][i]])
    write_csv(OUTPUT_DIR / "completions_quarterly.csv",
              ["quarter", "houses", "other", "total"],
              comp_rows)

    # 8. Chart data JSON
    with open(OUTPUT_DIR / "chart_data.json", "w") as f:
        json.dump(data_obj, f, indent=2)

    # 9. HTML report
    html = build_html(data_obj, findings, data_hash, n_over_capacity, total_nulls,
                       unincorp_info=unincorp_info, index_dates=index_dates,
                       dq_notes=compute_data_quality_notes(new_lots, greenfield_summary))
    with open(OUTPUT_DIR / "housing_supply_dashboard.html", "w") as f:
        f.write(html)

    print("✓ Analysis complete")
    print(f"  Files written to {OUTPUT_DIR}:")
    for p in sorted(OUTPUT_DIR.iterdir()):
        print(f"    {p.name} ({p.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
