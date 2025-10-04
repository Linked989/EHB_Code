"""Analytics helpers to derive secondary metrics for visualization."""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Dict, Iterable, List, Optional, Tuple


VALIDATION_SLO_P95_MS_DEFAULT = 50.0


@dataclass
class EventLogRow:
    ts: float
    event_id: str
    event_type: str
    status: str
    expected_valid: bool
    latency_ms: Optional[float]
    subject_id: Optional[str]
    run_id: Optional[str]
    run_started: Optional[float]
    sim_delay_ms: Optional[float]


def _group_runs(rows: List[EventLogRow]) -> List[Tuple[str, float, List[EventLogRow]]]:
    if not rows:
        return []
    grouped: Dict[str, List[EventLogRow]] = defaultdict(list)
    for row in rows:
        run_key = row.run_id or "UNKNOWN"
        grouped[run_key].append(row)
    runs: List[Tuple[str, float, List[EventLogRow]]] = []
    for run_id, run_rows in grouped.items():
        start_candidates = [r.run_started for r in run_rows if r.run_started is not None]
        if start_candidates:
            start = min(float(s) for s in start_candidates)
        else:
            start = min(float(r.ts) for r in run_rows)
        runs.append((run_id, start, sorted(run_rows, key=lambda r: r.ts)))
    runs.sort(key=lambda item: item[1])
    return runs


def _limit_runs(runs: List[Tuple[str, float, List[EventLogRow]]], limit: Optional[int]) -> List[Tuple[str, float, List[EventLogRow]]]:
    if limit is None or limit <= 0:
        return runs
    if len(runs) <= limit:
        return runs
    return runs[-limit:]


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    ordered = sorted(values)
    k = (len(ordered) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(ordered[int(k)])
    return float(ordered[f] + (ordered[c] - ordered[f]) * (k - f))


def _load_event_rows(path: Path) -> List[EventLogRow]:
    if not path.exists():
        return []
    rows: List[EventLogRow] = []
    with path.open() as f:
        reader = csv.DictReader(f)
        for raw in reader:
            if raw.get("action") != "submit":
                continue
            try:
                ts = float(raw.get("ts", "0"))
            except ValueError:
                ts = 0.0
            extra_raw = raw.get("extra", "")
            extra: Dict[str, object] = {}
            if extra_raw:
                try:
                    extra = json.loads(extra_raw)
                except json.JSONDecodeError:
                    extra = {}
            sim_delay_val = extra.get("simulated_delay_ms")
            if isinstance(sim_delay_val, str) and sim_delay_val not in ("", "None"):
                try:
                    sim_delay_val = float(sim_delay_val)
                except ValueError:
                    sim_delay_val = None
            elif isinstance(sim_delay_val, (int, float)):
                sim_delay_val = float(sim_delay_val)
            else:
                sim_delay_val = None
            rows.append(EventLogRow(
                ts=ts,
                event_id=raw.get("event_id", ""),
                event_type=raw.get("event_type", "unknown"),
                status=raw.get("value", ""),
                expected_valid=bool(extra.get("expected_valid", True)),
                latency_ms=(float(extra["latency_ms"]) if isinstance(extra.get("latency_ms"), (float, int, str)) and str(extra.get("latency_ms")) not in ("", "None") else None),
                subject_id=extra.get("subject_id"),
                run_id=extra.get("run_id"),
                run_started=(float(extra["run_started"]) if isinstance(extra.get("run_started"), (float, int, str)) and str(extra.get("run_started")) not in ("", "None") else None),
                sim_delay_ms=sim_delay_val,
            ))
    return rows


def _safe_latency_list(values: Iterable[Optional[float]]) -> List[float]:
    return [float(v) for v in values if isinstance(v, (int, float))]


def _compute_policy_metrics(rows: List[EventLogRow]) -> Dict[str, float]:
    invalid_attempted = sum(1 for r in rows if not r.expected_valid)
    invalid_accepted = sum(1 for r in rows if (not r.expected_valid and r.status == "OK"))
    valid_attempted = sum(1 for r in rows if r.expected_valid)
    valid_rejected = sum(1 for r in rows if (r.expected_valid and r.status != "OK"))
    pv_ar = (invalid_accepted / invalid_attempted) if invalid_attempted else 0.0
    frr = (valid_rejected / valid_attempted) if valid_attempted else 0.0
    return {
        "invalid_attempted": invalid_attempted,
        "invalid_accepted": invalid_accepted,
        "pv_ar": pv_ar,
        "valid_attempted": valid_attempted,
        "valid_rejected": valid_rejected,
        "frr": frr,
    }


def _compute_latency_metrics(rows: List[EventLogRow]) -> List[Dict[str, float]]:
    by_type: Dict[str, List[float]] = defaultdict(list)
    for row in rows:
        if row.latency_ms is not None:
            by_type[row.event_type].append(float(row.latency_ms))
    metrics = []
    for event_type, values in sorted(by_type.items()):
        metrics.append({
            "event_type": event_type,
            "p50_ms": _percentile(values, 50.0),
            "p90_ms": _percentile(values, 90.0),
            "p95_ms": _percentile(values, 95.0),
            "mean_ms": float(mean(values)) if values else 0.0,
            "count": len(values),
        })
    return metrics


def _compute_throughput(rows: List[EventLogRow], slo_p95_ms: float) -> Tuple[List[Dict[str, float]], Dict[str, float]]:
    if not rows:
        return [], {"sustainable_eps": 0.0, "slo_p95_ms": slo_p95_ms, "overall_eps": 0.0, "overall_p95_ms": 0.0}
    ordered = sorted(rows, key=lambda r: r.ts)
    start = ordered[0].ts
    end = ordered[-1].ts
    window = 1.0  # seconds
    duration = max(end - start, window)
    overall_eps = len(ordered) / duration
    overall_latencies = _safe_latency_list(r.latency_ms for r in ordered)
    overall_p95 = _percentile(overall_latencies, 95.0) if overall_latencies else 0.0

    buckets: Dict[int, List[EventLogRow]] = defaultdict(list)
    for row in ordered:
        idx = int((row.ts - start) // window)
        buckets[idx].append(row)

    window_rows: List[Dict[str, float]] = []
    sustainable_eps = 0.0
    for idx in sorted(buckets.keys()):
        bucket = buckets[idx]
        latencies = _safe_latency_list(r.latency_ms for r in bucket)
        if not bucket:
            continue
        eps = len(bucket) / window
        p95 = _percentile(latencies, 95.0) if latencies else 0.0
        sla_met = p95 <= slo_p95_ms
        if sla_met:
            sustainable_eps = max(sustainable_eps, eps)
        window_rows.append({
            "window_start_s": idx * window,
            "eps": eps,
            "p95_ms": p95,
            "count": len(bucket),
            "sla_met": sla_met,
        })

    summary = {
        "sustainable_eps": sustainable_eps,
        "slo_p95_ms": slo_p95_ms,
        "overall_eps": overall_eps,
        "overall_p95_ms": overall_p95,
        "event_count": len(ordered),
        "duration_s": duration,
        "sla_met": overall_p95 <= slo_p95_ms,
    }
    return window_rows, summary


def _compute_audit_metrics(contract) -> List[Dict[str, float]]:
    ledger = contract.ledger
    results: List[Dict[str, float]] = []
    for event_id, record in ledger.events.items():
        started = perf_counter()
        path = contract.get_ancestry(event_id)
        elapsed = (perf_counter() - started) * 1000.0
        depth = max(len(path) - 1, 0)
        results.append({
            "event_id": event_id,
            "event_type": record.event_type,
            "depth": depth,
            "latency_ms": elapsed,
        })
    results.sort(key=lambda r: (r["depth"], r["event_id"]))
    return results


def _compute_audit_summary(records: List[Dict[str, float]]) -> Dict[str, float]:
    if not records:
        return {"avg_latency_ms": 0.0, "slope_ms_per_link": 0.0}
    depths = [r["depth"] for r in records]
    latencies = [r["latency_ms"] for r in records]
    avg_latency = float(mean(latencies)) if latencies else 0.0

    sum_x = sum(depths)
    sum_y = sum(latencies)
    sum_x2 = sum(d * d for d in depths)
    sum_xy = sum(d * l for d, l in zip(depths, latencies))
    n = len(records)
    denom = n * sum_x2 - sum_x * sum_x
    slope = 0.0 if denom == 0 else (n * sum_xy - sum_x * sum_y) / denom
    return {
        "avg_latency_ms": avg_latency,
        "slope_ms_per_link": slope,
    }


def _average_fields(records: List[Dict[str, float]], keys: Iterable[str]) -> Dict[str, float]:
    if not records:
        return {k: 0.0 for k in keys}
    return {
        key: (sum(float(rec.get(key, 0.0)) for rec in records) / len(records)) for key in keys
    }


def _write_csv(path: Path, headers: List[str], rows: Iterable[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in headers})


def build_reports(
    metrics_csv_path: str,
    contract,
    out_dir: str = "data",
    slo_p95_ms: float = VALIDATION_SLO_P95_MS_DEFAULT,
    rounds: Optional[int] = None,
) -> str:
    out_base = Path(out_dir)
    rows = _load_event_rows(Path(metrics_csv_path))
    runs = _limit_runs(_group_runs(rows), rounds)

    policy_runs: List[Dict[str, float]] = []
    latency_runs: List[Dict[str, float]] = []
    throughput_windows: List[Dict[str, float]] = []
    throughput_summary_runs: List[Dict[str, float]] = []
    network_tps_runs: List[Dict[str, float]] = []

    if runs:
        for ordinal, (run_id, _, run_rows) in enumerate(runs, start=1):
            policy_metrics = _compute_policy_metrics(run_rows)
            policy_metrics.update({"run_id": run_id, "round": ordinal})
            policy_runs.append(policy_metrics)

            latency_metrics = _compute_latency_metrics(run_rows)
            for entry in latency_metrics:
                entry_copy = dict(entry)
                entry_copy.update({"run_id": run_id, "round": ordinal})
                latency_runs.append(entry_copy)

            window_rows, summary = _compute_throughput(run_rows, slo_p95_ms)
            for window_row in window_rows:
                enriched = dict(window_row)
                enriched.update({"run_id": run_id, "round": ordinal})
                throughput_windows.append(enriched)

            summary_enriched = dict(summary)
            summary_enriched.update({"run_id": run_id, "round": ordinal})
            throughput_summary_runs.append(summary_enriched)

            network_tps_runs.append({
                "run_id": run_id,
                "round": ordinal,
                "overall_eps": summary["overall_eps"],
                "sustainable_eps": summary["sustainable_eps"],
                "overall_p95_ms": summary["overall_p95_ms"],
                "event_count": summary["event_count"],
                "duration_s": summary["duration_s"],
                "sla_met": summary["sla_met"],
            })
    else:
        policy_runs.append({
            "run_id": "NONE",
            "round": 0,
            "invalid_attempted": 0,
            "invalid_accepted": 0,
            "pv_ar": 0.0,
            "valid_attempted": 0,
            "valid_rejected": 0,
            "frr": 0.0,
        })

    # Averages
    policy_average = _average_fields(policy_runs, [
        "invalid_attempted",
        "invalid_accepted",
        "pv_ar",
        "valid_attempted",
        "valid_rejected",
        "frr",
    ])
    policy_average.update({"run_id": "AVERAGE", "round": ""})

    latency_average: List[Dict[str, float]] = []
    latency_by_type: Dict[str, List[Dict[str, float]]] = defaultdict(list)
    for entry in latency_runs:
        latency_by_type[entry["event_type"]].append(entry)
    for event_type, items in sorted(latency_by_type.items()):
        avg_entry = {
            "run_id": "AVERAGE",
            "round": "",
            "event_type": event_type,
            "count": sum(item.get("count", 0) for item in items) / len(items),
            "p50_ms": sum(item.get("p50_ms", 0.0) for item in items) / len(items),
            "p90_ms": sum(item.get("p90_ms", 0.0) for item in items) / len(items),
            "p95_ms": sum(item.get("p95_ms", 0.0) for item in items) / len(items),
            "mean_ms": sum(item.get("mean_ms", 0.0) for item in items) / len(items),
        }
        latency_average.append(avg_entry)

    throughput_average = _average_fields(throughput_summary_runs, [
        "sustainable_eps",
        "overall_eps",
        "overall_p95_ms",
        "event_count",
        "duration_s",
    ])
    throughput_average.update({
        "run_id": "AVERAGE",
        "round": "",
        "slo_p95_ms": slo_p95_ms,
        "sla_met_ratio": (
            sum(1 for summary in throughput_summary_runs if summary.get("sla_met")) / len(throughput_summary_runs)
            if throughput_summary_runs else 0.0
        ),
    })
    throughput_average.setdefault("sla_met", "")

    network_tps_average = _average_fields(network_tps_runs, [
        "overall_eps",
        "sustainable_eps",
        "overall_p95_ms",
        "event_count",
        "duration_s",
    ])
    network_tps_average.update({
        "run_id": "AVERAGE",
        "round": "",
        "sla_met": (
            sum(1 for record in network_tps_runs if record.get("sla_met")) / len(network_tps_runs)
            if network_tps_runs else 0.0
        ),
    })

    audit = _compute_audit_metrics(contract)
    audit_summary = _compute_audit_summary(audit)

    # Consolidated summary CSV
    summary_map: Dict[str, Dict[str, object]] = {}
    run_row_lookup = {run_id: run_rows for run_id, _, run_rows in runs}

    for metrics in policy_runs:
        run_id = metrics.get("run_id", "")
        summary_map[run_id] = {
            "run_identifier": run_id,
            "round_number": metrics.get("round", ""),
            "invalid_events_attempted": metrics.get("invalid_attempted", 0.0),
            "invalid_events_accepted": metrics.get("invalid_accepted", 0.0),
            "policy_violation_rate": metrics.get("pv_ar", 0.0),
            "valid_events_attempted": metrics.get("valid_attempted", 0.0),
            "valid_events_rejected": metrics.get("valid_rejected", 0.0),
            "false_rejection_rate": metrics.get("frr", 0.0),
            "command_latency_p50_ms": 0.0,
            "command_latency_p90_ms": 0.0,
            "command_latency_p95_ms": 0.0,
            "events_per_second_overall": 0.0,
            "events_per_second_sustainable": 0.0,
            "overall_latency_p95_ms": 0.0,
            "events_processed": 0.0,
            "round_duration_seconds": 0.0,
            "slo_compliance_ratio": 0.0,
            "avg_validation_latency_ms": 0.0,
            "avg_simulated_delay_ms": 0.0,
        }

    for entry in latency_runs:
        if entry.get("event_type") != "command":
            continue
        run_id = entry.get("run_id", "")
        if run_id not in summary_map:
            continue
        summary_map[run_id]["command_latency_p50_ms"] = entry.get("p50_ms", 0.0)
        summary_map[run_id]["command_latency_p90_ms"] = entry.get("p90_ms", 0.0)
        summary_map[run_id]["command_latency_p95_ms"] = entry.get("p95_ms", 0.0)

    for entry in throughput_summary_runs:
        run_id = entry.get("run_id", "")
        if run_id not in summary_map:
            continue
        summary_map[run_id]["events_per_second_overall"] = entry.get("overall_eps", 0.0)
        summary_map[run_id]["events_per_second_sustainable"] = entry.get("sustainable_eps", 0.0)
        summary_map[run_id]["overall_latency_p95_ms"] = entry.get("overall_p95_ms", 0.0)
        summary_map[run_id]["events_processed"] = entry.get("event_count", 0.0)
        summary_map[run_id]["round_duration_seconds"] = entry.get("duration_s", 0.0)
        summary_map[run_id]["slo_compliance_ratio"] = 1.0 if entry.get("sla_met") else 0.0

    for run_id, rows_for_run in run_row_lookup.items():
        summary = summary_map.get(run_id)
        if not summary:
            continue
        latency_values = [float(r.latency_ms) for r in rows_for_run if r.latency_ms is not None]
        sim_delays = [float(r.sim_delay_ms) for r in rows_for_run if r.sim_delay_ms is not None]
        summary["avg_validation_latency_ms"] = float(sum(latency_values) / len(latency_values)) if latency_values else 0.0
        summary["avg_simulated_delay_ms"] = float(sum(sim_delays) / len(sim_delays)) if sim_delays else 0.0

    summary_rows: List[Dict[str, object]] = []
    for metrics in policy_runs:
        rid = metrics.get("run_id", "")
        if rid in summary_map:
            summary_rows.append(summary_map[rid])

    command_avg_entry = next((entry for entry in latency_average if entry.get("event_type") == "command"), None)
    avg_summary_row = {
        "run_identifier": "AVERAGE",
        "round_number": "",
        "invalid_events_attempted": policy_average.get("invalid_attempted", 0.0),
        "invalid_events_accepted": policy_average.get("invalid_accepted", 0.0),
        "policy_violation_rate": policy_average.get("pv_ar", 0.0),
        "valid_events_attempted": policy_average.get("valid_attempted", 0.0),
        "valid_events_rejected": policy_average.get("valid_rejected", 0.0),
        "false_rejection_rate": policy_average.get("frr", 0.0),
        "command_latency_p50_ms": command_avg_entry.get("p50_ms", 0.0) if command_avg_entry else 0.0,
        "command_latency_p90_ms": command_avg_entry.get("p90_ms", 0.0) if command_avg_entry else 0.0,
        "command_latency_p95_ms": command_avg_entry.get("p95_ms", 0.0) if command_avg_entry else 0.0,
        "events_per_second_overall": throughput_average.get("overall_eps", 0.0),
        "events_per_second_sustainable": throughput_average.get("sustainable_eps", 0.0),
        "overall_latency_p95_ms": throughput_average.get("overall_p95_ms", 0.0),
        "events_processed": throughput_average.get("event_count", 0.0),
        "round_duration_seconds": throughput_average.get("duration_s", 0.0),
        "slo_compliance_ratio": throughput_average.get("sla_met_ratio", 0.0),
        "avg_validation_latency_ms": (
            sum(float(row.get("avg_validation_latency_ms", 0.0)) for row in summary_rows) / len(summary_rows)
            if summary_rows else 0.0
        ),
        "avg_simulated_delay_ms": (
            sum(float(row.get("avg_simulated_delay_ms", 0.0)) for row in summary_rows) / len(summary_rows)
            if summary_rows else 0.0
        ),
    }

    # Dedicated CSV exports with descriptive names
    policy_headers = [
        "run_identifier",
        "round_number",
        "invalid_events_attempted",
        "invalid_events_accepted",
        "policy_violation_rate",
        "valid_events_attempted",
        "valid_events_rejected",
        "false_rejection_rate",
    ]
    policy_rows = [{
        "run_identifier": row["run_identifier"],
        "round_number": row["round_number"],
        "invalid_events_attempted": row["invalid_events_attempted"],
        "invalid_events_accepted": row["invalid_events_accepted"],
        "policy_violation_rate": row["policy_violation_rate"],
        "valid_events_attempted": row["valid_events_attempted"],
        "valid_events_rejected": row["valid_events_rejected"],
        "false_rejection_rate": row["false_rejection_rate"],
    } for row in summary_rows]
    policy_rows.append({k: avg_summary_row[k] for k in policy_headers})
    _write_csv(out_base / "policy_violation_rates.csv", policy_headers, policy_rows)

    latency_headers = [
        "run_identifier",
        "round_number",
        "event_type",
        "samples",
        "latency_p50_ms",
        "latency_p90_ms",
        "latency_p95_ms",
        "latency_mean_ms",
    ]
    latency_rows_csv: List[Dict[str, object]] = []
    for entry in latency_runs:
        latency_rows_csv.append({
            "run_identifier": entry.get("run_id", ""),
            "round_number": entry.get("round", ""),
            "event_type": entry.get("event_type"),
            "samples": entry.get("count", 0),
            "latency_p50_ms": entry.get("p50_ms", 0.0),
            "latency_p90_ms": entry.get("p90_ms", 0.0),
            "latency_p95_ms": entry.get("p95_ms", 0.0),
            "latency_mean_ms": entry.get("mean_ms", 0.0),
        })
    for entry in latency_average:
        latency_rows_csv.append({
            "run_identifier": entry.get("run_id", "AVERAGE"),
            "round_number": "",
            "event_type": entry.get("event_type"),
            "samples": entry.get("count", 0.0),
            "latency_p50_ms": entry.get("p50_ms", 0.0),
            "latency_p90_ms": entry.get("p90_ms", 0.0),
            "latency_p95_ms": entry.get("p95_ms", 0.0),
            "latency_mean_ms": entry.get("mean_ms", 0.0),
        })
    _write_csv(out_base / "validation_latency_by_event.csv", latency_headers, latency_rows_csv)

    throughput_headers = [
        "run_identifier",
        "round_number",
        "events_per_second_overall",
        "events_per_second_sustainable",
        "overall_latency_p95_ms",
        "events_processed",
        "round_duration_seconds",
        "slo_threshold_p95_ms",
        "slo_met",
        "slo_compliance_ratio",
    ]
    throughput_rows_csv: List[Dict[str, object]] = []
    for entry in throughput_summary_runs:
        throughput_rows_csv.append({
            "run_identifier": entry.get("run_id", ""),
            "round_number": entry.get("round", ""),
            "events_per_second_overall": entry.get("overall_eps", 0.0),
            "events_per_second_sustainable": entry.get("sustainable_eps", 0.0),
            "overall_latency_p95_ms": entry.get("overall_p95_ms", 0.0),
            "events_processed": entry.get("event_count", 0.0),
            "round_duration_seconds": entry.get("duration_s", 0.0),
            "slo_threshold_p95_ms": entry.get("slo_p95_ms", slo_p95_ms),
            "slo_met": bool(entry.get("sla_met", False)),
            "slo_compliance_ratio": "",
        })
    throughput_rows_csv.append({
        "run_identifier": throughput_average.get("run_id", "AVERAGE"),
        "round_number": "",
        "events_per_second_overall": throughput_average.get("overall_eps", 0.0),
        "events_per_second_sustainable": throughput_average.get("sustainable_eps", 0.0),
        "overall_latency_p95_ms": throughput_average.get("overall_p95_ms", 0.0),
        "events_processed": throughput_average.get("event_count", 0.0),
        "round_duration_seconds": throughput_average.get("duration_s", 0.0),
        "slo_threshold_p95_ms": throughput_average.get("slo_p95_ms", slo_p95_ms),
        "slo_met": "",
        "slo_compliance_ratio": throughput_average.get("sla_met_ratio", 0.0),
    })
    _write_csv(out_base / "throughput_slo_summary.csv", throughput_headers, throughput_rows_csv)

    overview_headers = [
        "run_identifier",
        "round_number",
        "invalid_events_attempted",
        "invalid_events_accepted",
        "policy_violation_rate",
        "valid_events_attempted",
        "valid_events_rejected",
        "false_rejection_rate",
        "command_latency_p50_ms",
        "command_latency_p90_ms",
        "command_latency_p95_ms",
        "events_per_second_overall",
        "events_per_second_sustainable",
        "overall_latency_p95_ms",
        "events_processed",
        "round_duration_seconds",
        "slo_compliance_ratio",
        "avg_validation_latency_ms",
        "avg_simulated_delay_ms",
    ]
    _write_csv(out_base / "round_overview_metrics.csv", overview_headers, [*summary_rows, avg_summary_row])

    _write_csv(out_base / "audit_path_resolution.csv", ["event_id", "event_type", "depth", "latency_ms"], audit)
    _write_csv(out_base / "audit_path_summary.csv", ["avg_latency_ms", "slope_ms_per_link"], [audit_summary])

    analytics = {
        "policy": {
            "runs": policy_runs,
            "average": policy_average,
        },
        "latency": {
            "runs": latency_runs,
            "average": latency_average,
        },
        "throughput": {
            "windows": throughput_windows,
            "summary_runs": throughput_summary_runs,
            "summary_average": throughput_average,
            "slo_p95_ms": slo_p95_ms,
        },
        "network_tps": {
            "runs": network_tps_runs,
            "average": network_tps_average,
        },
        "round_summary": {
            "rows": summary_rows,
            "average": avg_summary_row,
        },
        "audit": audit,
        "audit_summary": audit_summary,
    }

    analytics_path = out_base / "analytics.json"
    with analytics_path.open("w") as f:
        json.dump(analytics, f, indent=2)

    return str(analytics_path)
