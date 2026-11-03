"""Measure event-to-alert latency.

docs/01 s5, docs/07:
Calculates the latency from event start (trigger time) to alert creation.
Target budget: <= 2.0 seconds (2000 ms).
"""

import argparse
import sys
import time
from typing import Any

from app.core.db import get_connection


def fetch_latencies(camera_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    conn = get_connection()
    query = """
        SELECT
            a.id AS alert_id,
            a.level,
            a.message,
            a.created_at AS alert_ts,
            e.id AS event_id,
            e.camera_id,
            e.started_at AS event_start_ts,
            (a.created_at - e.started_at) AS latency_ms
        FROM alerts a
        JOIN events e ON a.event_id = e.id
        WHERE a.event_id IS NOT NULL
    """
    params = []
    if camera_id:
        query += " AND e.camera_id = ?"
        params.append(camera_id)

    query += " ORDER BY a.created_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def print_stats(latencies: list[dict[str, Any]], target_ms: float = 2000.0) -> None:
    if not latencies:
        print("No paired event-alert records found.")
        return

    vals = [r["latency_ms"] for r in latencies]
    sorted_vals = sorted(vals)
    n = len(sorted_vals)

    p50 = sorted_vals[int(n * 0.50)]
    p95 = sorted_vals[min(int(n * 0.95), n - 1)]
    min_val = sorted_vals[0]
    max_val = sorted_vals[-1]
    avg_val = sum(vals) / n

    passed = max_val <= target_ms

    print("=" * 65)
    print(" EVENT-TO-ALERT LATENCY BENCHMARK REPORT")
    print("=" * 65)
    print(f"Total Paired Events/Alerts Measured: {n}")
    print(f"Target Budget:                      <= {target_ms:.1f} ms (2.0 s)")
    print(f"Min Latency:                         {min_val} ms")
    print(f"Average Latency:                     {avg_val:.1f} ms")
    print(f"p50 (Median) Latency:                {p50} ms")
    print(f"p95 Latency:                         {p95} ms")
    print(f"Max Latency:                         {max_val} ms")
    print(f"Status:                              {'PASS (within budget)' if passed else 'FAIL (exceeded budget)'}")
    print("-" * 65)
    print(f"{'Alert ID':<26} | {'Level':<8} | {'Latency':<10} | {'Camera':<10}")
    print("-" * 65)
    for r in latencies[:10]:
        print(f"{r['alert_id']:<26} | {r['level']:<8} | {r['latency_ms']} ms | {r['camera_id']}")
    if n > 10:
        print(f"... and {n - 10} more records.")
    print("=" * 65)


def watch_latencies(camera_id: str | None = None, interval: float = 1.0) -> None:
    print(f"Watching for new events and alerts (interval={interval}s). Press Ctrl+C to stop...")
    seen_alerts = set()
    try:
        while True:
            records = fetch_latencies(camera_id=camera_id, limit=20)
            for r in reversed(records):
                if r["alert_id"] not in seen_alerts:
                    seen_alerts.add(r["alert_id"])
                    status_flag = "PASS" if r["latency_ms"] <= 2000 else "SLOW"
                    print(
                        f"[{time.strftime('%H:%M:%S')}] [{status_flag}] "
                        f"Alert: {r['alert_id'][:8]}.. | Event: {r['event_id'][:8]}.. | "
                        f"Latency: {r['latency_ms']} ms | Level: {r['level']} | {r['message']}"
                    )
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped latency watcher.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure event-to-alert latency from MCVMS SQLite database.")
    parser.add_argument("--camera", type=str, default=None, help="Filter by camera ID")
    parser.add_argument("--limit", type=int, default=50, help="Number of recent records to evaluate (default: 50)")
    parser.add_argument("--target", type=float, default=2000.0, help="Target latency budget in ms (default: 2000.0)")
    parser.add_argument("--watch", action="store_true", help="Continuously poll and display new event-alert latencies")
    args = parser.parse_args()

    if args.watch:
        watch_latencies(camera_id=args.camera)
    else:
        latencies = fetch_latencies(camera_id=args.camera, limit=args.limit)
        print_stats(latencies, target_ms=args.target)
        if latencies and max(r["latency_ms"] for r in latencies) > args.target:
            sys.exit(1)


if __name__ == "__main__":
    main()

