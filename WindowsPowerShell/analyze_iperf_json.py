import json, sys, csv, os

def extract_summary(j):
    # Detect protocol
    proto = "TCP"
    start_ts = j.get("start", {}).get("timestamp", {}).get("time", "")
    reverse = j.get("start", {}).get("test_start", {}).get("reverse", 0)
    direction = "DL" if reverse else "UL"  # client perspective

    end = j.get("end", {})
    # Try multiple locations because iperf3 JSON varies
    sum_recv = end.get("sum_received") or {}
    sum_sent = end.get("sum_sent") or {}
    sum_any = end.get("sum") or {}

    # Protocol heuristic: UDP tests populate jitter/loss
    if "jitter_ms" in sum_any or "lost_percent" in sum_any:
        proto = "UDP"

    def bps(d): return (d.get("bits_per_second") or 0)/1e6

    bits_per_second = (sum_recv.get("bits_per_second") or
                       sum_sent.get("bits_per_second") or
                       sum_any.get("bits_per_second") or 0)

    seconds = (sum_recv.get("seconds") or
               sum_sent.get("seconds") or
               sum_any.get("seconds") or 0)

    # UDP fields
    jitter_ms = sum_any.get("jitter_ms")
    lost = sum_any.get("lost_percent")

    # Per-interval P95 throughput
    intervals = j.get("intervals", [])
    series = [i.get("sum", {}).get("bits_per_second", 0) for i in intervals if i.get("sum")]
    p95 = 0
    if series:
        s = sorted(series)
        idx = int(0.95*(len(s)-1))
        p95 = s[idx]

    return {
        "start_time": start_ts,
        "direction": direction,
        "protocol": proto,
        "throughput_mbps_avg": bits_per_second/1e6,
        "throughput_mbps_p95": p95/1e6,
        "udp_jitter_ms": jitter_ms,
        "udp_loss_pct": lost,
        "duration_s": seconds,
    }

def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_iperf_json.py file1.json [file2.json ...]")
        sys.exit(1)
    rows = []
    for path in sys.argv[1:]:
        with open(path, "r") as f:
            j = json.load(f)
        s = extract_summary(j)
        s["source_json"] = os.path.basename(path)
        rows.append(s)
    out = "iperf_summary.csv"
    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {out} with {len(rows)} rows")

if __name__ == "__main__":
    main()