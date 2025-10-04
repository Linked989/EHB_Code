"""Analytics helpers to derive secondary metrics for visualization."""
from __future__ import annotations

import csv
import json
import math
import os
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
            ))
    return rows


def _latest_run_rows(rows: List[EventLogRow]) -> List[EventLogRow]:
    runs: Dict[str, float] = {}
    for row in rows:
        if row.run_id and row.run_started is not None:
            runs[row.run_id] = max(runs.get(row.run_id, float("-inf")), float(row.run_started))
    if not runs:
        return rows
    latest_run_id = max(runs.items(), key=lambda kv: kv[1])[0]
    return [row for row in rows if row.run_id == latest_run_id]


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


def _write_csv(path: Path, headers: List[str], rows: Iterable[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in headers})


def build_reports(metrics_csv_path: str, contract, out_dir: str = "data", slo_p95_ms: float = VALIDATION_SLO_P95_MS_DEFAULT) -> str:
    out_base = Path(out_dir)
    rows = _load_event_rows(Path(metrics_csv_path))
    rows = _latest_run_rows(rows)

    policy = _compute_policy_metrics(rows)
    latency = _compute_latency_metrics(rows)
    throughput_windows, throughput_summary = _compute_throughput(rows, slo_p95_ms)
    audit = _compute_audit_metrics(contract)
    audit_summary = _compute_audit_summary(audit)

    _write_csv(out_base / "policy_metrics.csv", ["invalid_attempted", "invalid_accepted", "pv_ar", "valid_attempted", "valid_rejected", "frr"], [policy])

    _write_csv(out_base / "latency_metrics.csv", ["event_type", "count", "p50_ms", "p90_ms", "p95_ms", "mean_ms"], latency)

    _write_csv(out_base / "throughput_windows.csv", ["window_start_s", "eps", "p95_ms", "count", "sla_met"], throughput_windows)

    throughput_summary_headers = ["sustainable_eps", "slo_p95_ms", "overall_eps", "overall_p95_ms"]
    _write_csv(out_base / "throughput_summary.csv", throughput_summary_headers, [throughput_summary])

    _write_csv(out_base / "audit_resolution.csv", ["event_id", "event_type", "depth", "latency_ms"], audit)

    _write_csv(out_base / "audit_summary.csv", ["avg_latency_ms", "slope_ms_per_link"], [audit_summary])

    analytics = {
        "policy": policy,
        "latency": latency,
        "throughput": {
            "windows": throughput_windows,
            "summary": throughput_summary,
        },
        "audit": audit,
        "audit_summary": audit_summary,
    }

    analytics_path = out_base / "analytics.json"
    with analytics_path.open("w") as f:
        json.dump(analytics, f, indent=2)

    return str(analytics_path)
