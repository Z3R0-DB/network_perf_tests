#!/usr/bin/env python3
"""Robust artifact analyzer for network_perf_tests.

Usage:
    python3 scripts/plot_results.py --artifacts-root results --outdir results/analysis_output --open-report

Searches for artifact directories named `artifacts_*` under --artifacts-root and extracts:
 - iperf JSON outputs (tcp/udp dl/ul)
 - wlan summary JSON
 - ping outputs (gw, wan)

Produces:
 - CSV summary at {outdir}/summary.csv
 - combined PNG plots and a self-contained HTML report (report.html)
"""
from __future__ import annotations
import argparse
import base64
import glob
import json
import os
import webbrowser
from pathlib import Path
from statistics import mean, stdev
import re

import pandas as pd
import numpy as np
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
    images = []
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
    # embed
    try:
        with open(bw_png, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('ascii')
            images.append(('Bandwidth comparison (Mbps)', bw_png, b64))
    except Exception:
        pass

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
        try:
            with open(rssi_png, 'rb') as f:
                b64 = base64.b64encode(f.read()).decode('ascii')
                images.append(('RSSI / Signal', rssi_png, b64))
        except Exception:
            pass

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
        try:
            with open(lat_png, 'rb') as f:
                b64 = base64.b64encode(f.read()).decode('ascii')
                images.append(('Latency comparison (ms)', lat_png, b64))
        except Exception:
            pass

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
            try:
                with open(jit_png, 'rb') as f:
                    b64 = base64.b64encode(f.read()).decode('ascii')
                    images.append(('Jitter comparison (ms)', jit_png, b64))
            except Exception:
                pass

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
            try:
                with open(loss_png, 'rb') as f:
                    b64 = base64.b64encode(f.read()).decode('ascii')
                    images.append(('Packet loss comparison (%)', loss_png, b64))
            except Exception:
                pass

    print('Plots generated.')
    # Build a prettier HTML report with summary cards and comparison table
    try:
        html_path = os.path.join(outdir, 'report.html')
        title = 'Network Performance Report'
        css = '''
        body{font-family:Inter,Arial,Helvetica,sans-serif;margin:20px;color:#222}
        h1{font-size:24px;margin-bottom:8px}
        .row{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:18px}
        .card{background:#fff;border:1px solid #e6e6e6;padding:12px;border-radius:6px;box-shadow:0 1px 2px rgba(0,0,0,0.04)}
        .card.small{flex:0 0 180px}
        .card.large{flex:1 1 600px}
        .card h4{margin:0 0 6px 0;font-size:13px;color:#666}
        table{border-collapse:collapse;width:100%;margin-top:8px}
        th,td{border:1px solid #eee;padding:8px;text-align:left}
        th{background:#fafafa}
        img.plotimg{max-width:100%;height:auto;border:1px solid #ddd;padding:6px;border-radius:4px}
        .metric{font-weight:700;font-size:18px}
        '''

        # choose a baseline run (first non-empty test_id or first row)
        baseline_idx = 0
        if 'test_id' in df.columns and df['test_id'].notna().any():
            baseline_idx = df.index[df['test_id'].notna()][0]

        metrics_for_cards = ['tcp_dl_mbps', 'tcp_ul_mbps', 'udp_dl_mbps', 'udp_ul_mbps', 'rssi', 'snr', 'ping_wan_mean_ms']

        with open(html_path, 'w') as h:
            h.write(f'<!doctype html><html><head><meta charset="utf-8"><title>{title}</title>')
            h.write(f'<style>{css}</style>')
            h.write('</head><body>')
            h.write(f'<h1>{title}</h1>')

            # Summary cards for each run
            h.write('<div class="row">')
            for _, r in df.iterrows():
                label = r.get('test_id') or os.path.basename(r['artifact_dir'])
                h.write('<div class="card small">')
                h.write(f'<h4>{label}</h4>')
                for m in metrics_for_cards:
                    val = r.get(m)
                    display = '' if val is None or (isinstance(val, float) and pd.isna(val)) else (f'{val:.2f}' if isinstance(val, float) else str(val))
                    h.write(f'<div><span class="metric">{display}</span> <small style="color:#666">{m}</small></div>')
                h.write('</div>')
            h.write('</div>')

            # Embedded plots in two-column layout
            h.write('<div class="row">')
            for title_img, path, b64 in images:
                h.write('<div class="card large">')
                h.write(f'<h4>{title_img}</h4>')
                h.write(f'<img class="plotimg" src="data:image/png;base64,{b64}" alt="{title_img}"/>')
                h.write(f'<p style="font-size:12px;color:#888">Source: {os.path.basename(path)}</p>')
                h.write('</div>')
            h.write('</div>')

            # Full summary table
            h.write('<h2>Summary table</h2>')
            try:
                h.write(df.to_html(index=False, na_rep=''))
            except Exception:
                h.write('<p>Unable to render table.</p>')

            # Comparison section: percent change vs baseline
            h.write('<h2>Comparison vs baseline</h2>')
            try:
                comp_metrics = [c for c in ['tcp_dl_mbps', 'tcp_ul_mbps', 'udp_dl_mbps', 'udp_ul_mbps', 'rssi', 'snr', 'ping_wan_mean_ms'] if c in df.columns]
                if comp_metrics and len(df) > 1:
                    base = df.loc[baseline_idx, comp_metrics].astype(float)
                    h.write('<table>')
                    # header
                    h.write('<tr><th>metric</th>')
                    for _, r in df.iterrows():
                        h.write(f'<th>{r.get("test_id") or os.path.basename(r["artifact_dir"])}</th>')
                    h.write('</tr>')
                    for m in comp_metrics:
                        h.write(f'<tr><td>{m}</td>')
                        for _, r in df.iterrows():
                            v = r.get(m)
                            try:
                                vnum = float(v)
                                b = float(base[m]) if not pd.isna(base[m]) else None
                                if b is None or b == 0 or pd.isna(b):
                                    h.write(f'<td>{vnum:.2f}</td>')
                                else:
                                    pct = (vnum - b) / b * 100.0
                                    h.write(f'<td>{vnum:.2f} <small style="color:#666">({pct:+.1f}%)</small></td>')
                            except Exception:
                                h.write(f'<td>{v}</td>')
                        h.write('</tr>')
                    h.write('</table>')
                else:
                    h.write('<p>Not enough runs to compare.</p>')
            except Exception as e:
                h.write(f'<p>Comparison failed: {e}</p>')

            h.write('<p style="color:#666">Generated by plot_results.py</p>')
            h.write('</body></html>')

        print(f'Wrote HTML report: {html_path}')
    except Exception as e:
        print('Failed to write HTML report:', e)
    return html_path, images


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--artifacts-root', default='.', help='Root folder to search for artifacts_* dirs')
    p.add_argument('--outdir', default='analysis_output', help='Where to write CSV and plots')
    p.add_argument('--open-report', action='store_true', help='Open the generated HTML report in the default browser')
    args = p.parse_args()

    df = analyze_artifacts(args.artifacts_root)
    if df.empty:
        print('No artifact directories found. Run the tests first and point --artifacts-root to the folder containing artifacts_* dirs.')
        return
    html_path, images = plot_summary(df, args.outdir)
    if args.open_report and html_path:
        try:
            webbrowser.open('file://' + os.path.abspath(html_path))
            print('Opened report in default browser')
        except Exception as e:
            print('Failed to open report:', e)


if __name__ == '__main__':
    main()
