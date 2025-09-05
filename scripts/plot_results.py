#!/usr/bin/env python3
"""Aggregate artifacts from wifi runs and produce comparison tables and plots.

Usage: python3 scripts/plot_results.py --artifacts-root . --outdir analysis_output

It looks for directories named artifacts_* and extracts:
 - iperf JSON (tcp/udp ul/dl)
 - wlan summary JSON
 - ping outputs (gw, wan)

Outputs a CSV summary and PNG plots comparing metrics across runs.
"""
import argparse
import glob
import json
import os
import re
from statistics import mean, stdev

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

PING_TIME_RE = re.compile(r"time=?([0-9]+\.?[0-9]*) ?ms")


def parse_iperf_json(path):
    """Return a dict with keys: mbps, jitter_ms (optional), packet_loss_pct (optional).
    Returns None on failure.
    """
    try:
        with open(path, "r") as f:
            j = json.load(f)
    except Exception:
        return None

    result = {"mbps": None, "jitter_ms": None, "packet_loss_pct": None}

    # Helper to find a key anywhere in the JSON
    def find_key(obj, key):
        if isinstance(obj, dict):
            if key in obj:
                return obj[key]
            for v in obj.values():
                r = find_key(v, key)
                if r is not None:
                    return r
        elif isinstance(obj, list):
            for item in obj:
                r = find_key(item, key)
                if r is not None:
                    return r
        return None

    # mbps: look for bits_per_second under common summary locations
    end = j.get("end") or j.get("summary") or j
    for key in ("sum_sent", "sum_received", "sum"):
        part = end.get(key) if isinstance(end, dict) else None
        if part and isinstance(part, dict):
            bps = part.get("bits_per_second")
            if bps:
                result["mbps"] = float(bps) / 1e6
                break

    if result["mbps"] is None:
        bps = find_key(j, "bits_per_second")
        if bps:
            result["mbps"] = float(bps) / 1e6

    # jitter_ms: iperf3 JSON commonly includes 'jitter_ms' under sum for UDP
    jitter = find_key(j, "jitter_ms")
    if jitter is not None:
        try:
            result["jitter_ms"] = float(jitter)
        except Exception:
            pass

    # packet loss: iperf3 may include lost_percent, lost_packets/packets
    lost_pct = find_key(j, "lost_percent") or find_key(j, "lost_percent")
    if lost_pct is None:
        # compute if lost and total are present
        lost = find_key(j, "lost_packets") or find_key(j, "lost")
        total = find_key(j, "total_packets") or find_key(j, "packets")
        try:
            if lost is not None and total is not None and float(total) > 0:
                result["packet_loss_pct"] = float(lost) / float(total) * 100.0
        except Exception:
            pass
    else:
        try:
            result["packet_loss_pct"] = float(lost_pct)
        except Exception:
            pass

    return result


def parse_wlan_summary(path):
    try:
        with open(path, "r") as f:
            j = json.load(f)
            return j
    except Exception:
        return None


def parse_ping_file(path):
    times = []
    try:
        with open(path, "r", errors="ignore") as f:
            for line in f:
                m = PING_TIME_RE.search(line)
                if m:
                    times.append(float(m.group(1)))
    except Exception:
        return None
    if not times:
        return None
    return {"count": len(times), "mean_ms": mean(times), "std_ms": stdev(times) if len(times) > 1 else 0.0}


def analyze_artifacts(root):
    rows = []
    # find artifact dirs
    pattern = os.path.join(root, "artifacts_*")
    for d in sorted(glob.glob(pattern)):
        if not os.path.isdir(d):
            continue
        row = {"artifact_dir": d}
        # test id / timestamp from filenames
        # wlan summary
        wlan_summary = glob.glob(os.path.join(d, "*wlan*summary.json"))
        if wlan_summary:
            w = parse_wlan_summary(wlan_summary[0])
            if w:
                row.update({
                    "test_id": w.get("test_id"),
                    "timestamp": w.get("timestamp"),
                    "ssid": w.get("ssid"),
                    "bssid": w.get("bssid"),
                    "rssi": w.get("rssi"),
                    "noise": w.get("noise"),
                    "snr": w.get("snr"),
                    "signal_percent": w.get("signal_percent"),
                    "last_tx_rate_mbps": w.get("last_tx_rate_mbps"),
                    "channel": w.get("channel"),
                })
        # iperf files
        iperf_tcp_dl = glob.glob(os.path.join(d, "*tcp*_dl.json"))
        iperf_tcp_ul = glob.glob(os.path.join(d, "*tcp*_ul.json"))
        iperf_udp_dl = glob.glob(os.path.join(d, "*udp*_dl.json"))
        iperf_udp_ul = glob.glob(os.path.join(d, "*udp*_ul.json"))
        if iperf_tcp_dl:
            v = parse_iperf_json(iperf_tcp_dl[0])
            if v:
                row["tcp_dl_mbps"] = v.get("mbps")
                row["tcp_dl_jitter_ms"] = v.get("jitter_ms")
                row["tcp_dl_packet_loss_pct"] = v.get("packet_loss_pct")
        if iperf_tcp_ul:
            v = parse_iperf_json(iperf_tcp_ul[0])
            if v:
                row["tcp_ul_mbps"] = v.get("mbps")
                row["tcp_ul_jitter_ms"] = v.get("jitter_ms")
                row["tcp_ul_packet_loss_pct"] = v.get("packet_loss_pct")
        if iperf_udp_dl:
            v = parse_iperf_json(iperf_udp_dl[0])
            if v:
                row["udp_dl_mbps"] = v.get("mbps")
                row["udp_dl_jitter_ms"] = v.get("jitter_ms")
                row["udp_dl_packet_loss_pct"] = v.get("packet_loss_pct")
        if iperf_udp_ul:
            v = parse_iperf_json(iperf_udp_ul[0])
            if v:
                row["udp_ul_mbps"] = v.get("mbps")
                row["udp_ul_jitter_ms"] = v.get("jitter_ms")
                row["udp_ul_packet_loss_pct"] = v.get("packet_loss_pct")
        # pings
        ping_gw = glob.glob(os.path.join(d, "*ping*_gw.txt"))
        ping_wan = glob.glob(os.path.join(d, "*ping*_wan.txt"))
        if ping_gw:
            p = parse_ping_file(ping_gw[0])
            if p:
                row.update({"ping_gw_mean_ms": p["mean_ms"], "ping_gw_std_ms": p["std_ms"]})
        if ping_wan:
            p = parse_ping_file(ping_wan[0])
            if p:
                row.update({"ping_wan_mean_ms": p["mean_ms"], "ping_wan_std_ms": p["std_ms"]})
        rows.append(row)
    return pd.DataFrame(rows)


def plot_summary(df, outdir):
    os.makedirs(outdir, exist_ok=True)
    # clean test label
    df = df.copy()
    df['label'] = df.apply(lambda r: r.get('test_id') or os.path.basename(r['artifact_dir']), axis=1)

    # convert numeric columns
    numeric_cols = ['rssi', 'noise', 'snr', 'signal_percent', 'last_tx_rate_mbps',
                        'tcp_dl_mbps', 'tcp_ul_mbps', 'udp_dl_mbps', 'udp_ul_mbps',
                        'tcp_dl_jitter_ms', 'tcp_ul_jitter_ms', 'udp_dl_jitter_ms', 'udp_ul_jitter_ms',
                        'tcp_dl_packet_loss_pct', 'tcp_ul_packet_loss_pct', 'udp_dl_packet_loss_pct', 'udp_ul_packet_loss_pct',
                        'ping_gw_mean_ms', 'ping_wan_mean_ms']
    for c in numeric_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')

    # Save aggregated CSV
    csv_path = os.path.join(outdir, 'summary.csv')
    df.to_csv(csv_path, index=False)
    print(f"Wrote summary CSV: {csv_path}")

    sns.set(style='whitegrid')

    # Bandwidth comparison (bar)
    bw_cols = ['tcp_ul_mbps', 'tcp_dl_mbps', 'udp_ul_mbps', 'udp_dl_mbps']
    bw_df = df[['label'] + [c for c in bw_cols if c in df.columns]].melt(id_vars='label', var_name='metric', value_name='mbps')
    plt.figure(figsize=(10, 6))
    sns.barplot(data=bw_df, x='label', y='mbps', hue='metric')
    plt.title('Bandwidth comparison (Mbps)')
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    bw_png = os.path.join(outdir, 'bandwidth_comparison.png')
    plt.savefig(bw_png)
    plt.close()
    print(f"Wrote plot: {bw_png}")

    # RSSI / Signal
    if 'rssi' in df.columns or 'signal_percent' in df.columns:
        plt.figure(figsize=(8, 5))
        if 'rssi' in df.columns:
            sns.barplot(data=df, x='label', y='rssi')
            plt.ylabel('RSSI (dBm)')
            plt.title('RSSI by test')
        else:
            sns.barplot(data=df, x='label', y='signal_percent')
            plt.ylabel('Signal %')
            plt.title('Signal % by test')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        rssi_png = os.path.join(outdir, 'rssi_comparison.png')
        plt.savefig(rssi_png)
        plt.close()
        print(f"Wrote plot: {rssi_png}")

    # Latency comparison
    lat_cols = [c for c in ['ping_gw_mean_ms', 'ping_wan_mean_ms'] if c in df.columns]
    if lat_cols:
        lat_df = df[['label'] + lat_cols].melt(id_vars='label', var_name='metric', value_name='ms')
        plt.figure(figsize=(10, 6))
        sns.barplot(data=lat_df, x='label', y='ms', hue='metric')
        plt.title('Latency comparison (ms)')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        lat_png = os.path.join(outdir, 'latency_comparison.png')
        plt.savefig(lat_png)
        plt.close()
        print(f"Wrote plot: {lat_png}")

        # Jitter comparison
        jitter_cols = [c for c in ['tcp_dl_jitter_ms', 'tcp_ul_jitter_ms', 'udp_dl_jitter_ms', 'udp_ul_jitter_ms'] if c in df.columns]
        if jitter_cols:
            jit_df = df[['label'] + jitter_cols].melt(id_vars='label', var_name='metric', value_name='ms')
            plt.figure(figsize=(10, 6))
            sns.barplot(data=jit_df, x='label', y='ms', hue='metric')
            plt.title('Jitter comparison (ms)')
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()
            jit_png = os.path.join(outdir, 'jitter_comparison.png')
            plt.savefig(jit_png)
            plt.close()
            print(f"Wrote plot: {jit_png}")

        # Packet loss comparison
        loss_cols = [c for c in ['tcp_dl_packet_loss_pct', 'tcp_ul_packet_loss_pct', 'udp_dl_packet_loss_pct', 'udp_ul_packet_loss_pct'] if c in df.columns]
        if loss_cols:
            loss_df = df[['label'] + loss_cols].melt(id_vars='label', var_name='metric', value_name='pct')
            plt.figure(figsize=(10, 6))
            sns.barplot(data=loss_df, x='label', y='pct', hue='metric')
            plt.title('Packet loss comparison (%)')
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()
            loss_png = os.path.join(outdir, 'packet_loss_comparison.png')
            plt.savefig(loss_png)
            plt.close()
            print(f"Wrote plot: {loss_png}")

    print('Plots generated.')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--artifacts-root', default='.', help='Root folder to search for artifacts_* dirs')
    p.add_argument('--outdir', default='analysis_output', help='Where to write CSV and plots')
    args = p.parse_args()

    df = analyze_artifacts(args.artifacts_root)
    if df.empty:
        print('No artifact directories found. Run the tests first and point --artifacts-root to the folder containing artifacts_* dirs.')
        return
    plot_summary(df, args.outdir)


if __name__ == '__main__':
    main()
