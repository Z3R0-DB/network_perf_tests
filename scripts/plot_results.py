#!/usr/bin/env python3
"""Robust artifact analyzer for network_perf_tests.

Produces a CSV summary, PNG comparison plots, and a polished HTML report.
This script intentionally omits RSSI/noise/signal_percent fields (they are deprecated
for now). It tolerates older artifacts that may include those fields.
"""
from __future__ import annotations
import argparse
import base64
import glob
import json
import os
import webbrowser
from datetime import datetime
from statistics import mean, stdev
import re

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

PING_TIME_RE = re.compile(r"time=?([0-9]+\.?[0-9]*) ?ms")


def parse_iperf_json(path):
    try:
        with open(path, "r") as f:
            j = json.load(f)
    except Exception:
        return None

    result = {"mbps": None, "jitter_ms": None, "packet_loss_pct": None}

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
            try:
                result["mbps"] = float(bps) / 1e6
            except Exception:
                pass

    jitter = find_key(j, "jitter_ms")
    if jitter is not None:
        try:
            result["jitter_ms"] = float(jitter)
        except Exception:
            pass

    lost_pct = find_key(j, "lost_percent")
    if lost_pct is None:
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
            return json.load(f)
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
    pattern = os.path.join(root, "artifacts_*")
    for d in sorted(glob.glob(pattern)):
        if not os.path.isdir(d):
            continue
        row = {"artifact_dir": d}
        wlan_summary = glob.glob(os.path.join(d, "*wlan*summary.json"))
        if wlan_summary:
            w = parse_wlan_summary(wlan_summary[0])
            if w:
                # intentionally omit rssi/noise/snr/signal_percent
                row.update({
                    "test_id": w.get("test_id"),
                    "timestamp": w.get("timestamp"),
                    "interface_name": w.get("interface_name"),
                    "interface_type": w.get("interface_type"),
                    "interface_device": w.get("interface_device"),
                    "mac_address": w.get("mac_address"),
                    "link_speed": w.get("link_speed"),
                    "ssid": w.get("ssid"),
                    "bssid": w.get("bssid"),
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
                # TCP doesn't provide jitter/loss metrics - only bandwidth. TCP uses reliable delivery with retransmissions, so packet loss is handled transparently.
        if iperf_tcp_ul:
            v = parse_iperf_json(iperf_tcp_ul[0])
            if v:
                row["tcp_ul_mbps"] = v.get("mbps")
                # TCP doesn't provide jitter/loss metrics - only bandwidth
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
    df = df.copy()
    df["label"] = df.apply(lambda r: r.get("test_id") or os.path.basename(r["artifact_dir"]), axis=1)

    numeric_cols = [
        'last_tx_rate_mbps',
        'tcp_dl_mbps', 'tcp_ul_mbps', 'udp_dl_mbps', 'udp_ul_mbps',
        'udp_dl_jitter_ms', 'udp_ul_jitter_ms',
        'udp_dl_packet_loss_pct', 'udp_ul_packet_loss_pct',
        'ping_gw_mean_ms', 'ping_wan_mean_ms'
    ]
    for c in numeric_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')

    csv_path = os.path.join(outdir, 'summary.csv')
    df.to_csv(csv_path, index=False)
    print(f"Wrote summary CSV: {csv_path}")

    sns.set(style='whitegrid')

    # Bandwidth comparison (bar)
    bw_cols = ['tcp_ul_mbps', 'tcp_dl_mbps', 'udp_ul_mbps', 'udp_dl_mbps']
    bw_available = [c for c in bw_cols if c in df.columns]
    if bw_available:
        bw_df = df[['label'] + bw_available].melt(id_vars='label', var_name='metric', value_name='mbps')
        plt.figure(figsize=(10, 6))
        sns.barplot(data=bw_df, x='label', y='mbps', hue='metric')
        plt.title('Bandwidth comparison (Mbps)')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        bw_png = os.path.join(outdir, 'bandwidth_comparison.png')
        plt.savefig(bw_png)
        plt.close()
        print(f"Wrote plot: {bw_png}")
        try:
            with open(bw_png, 'rb') as f:
                b64 = base64.b64encode(f.read()).decode('ascii')
                images.append(('Bandwidth comparison (Mbps)', bw_png, b64))
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
    # Jitter comparison (UDP only - TCP doesn't provide jitter)
    jitter_cols = [c for c in ['udp_dl_jitter_ms', 'udp_ul_jitter_ms'] if c in df.columns]
    if jitter_cols:
        jit_df = df[['label'] + jitter_cols].melt(id_vars='label', var_name='metric', value_name='ms')
        plt.figure(figsize=(10, 6))
        sns.barplot(data=jit_df, x='label', y='ms', hue='metric')
        plt.title('Jitter comparison (ms) - UDP only')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        jit_png = os.path.join(outdir, 'jitter_comparison.png')
        plt.savefig(jit_png)
        plt.close()
        print(f"Wrote plot: {jit_png}")
        try:
            with open(jit_png, 'rb') as f:
                b64 = base64.b64encode(f.read()).decode('ascii')
                images.append(('Jitter comparison (ms) - UDP only', jit_png, b64))
        except Exception:
            pass

    # Packet loss comparison (UDP only - TCP doesn't provide packet loss)
    loss_cols = [c for c in ['udp_dl_packet_loss_pct', 'udp_ul_packet_loss_pct'] if c in df.columns]
    if loss_cols:
        loss_df = df[['label'] + loss_cols].melt(id_vars='label', var_name='metric', value_name='pct')
        plt.figure(figsize=(10, 6))
        sns.barplot(data=loss_df, x='label', y='pct', hue='metric')
        plt.title('Packet loss comparison (%) - UDP only')
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

    # Build HTML report
    html_path = os.path.join(outdir, 'report.html')
    title = 'Network Performance Report'
    now = datetime.now().astimezone().isoformat(sep=' ', timespec='seconds')
    css = '''
    :root{--bg:#f6f8fa;--card:#ffffff;--muted:#6b7280;--accent:#0f62fe;--border:#e6e6e6}
    body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;margin:0;background:var(--bg);color:#111}
    .container{max-width:1200px;margin:28px auto;padding:0 20px}
    .site-header{background:linear-gradient(90deg,#ffffff,#fbfdff);border-bottom:1px solid var(--border)}
    .site-header .inner{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:18px 0}
    .card-row{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;margin:18px 0}
    .card{background:var(--card);border:1px solid var(--border);padding:12px;border-radius:10px}
    .plots{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:12px 0}
    .plotimg{width:100%;height:auto;border-radius:6px}
    /* Compact, scrollable summary table */
    .table-wrap{background:var(--card);border:1px solid var(--border);border-radius:8px;overflow:auto;max-height:360px}
    table{border-collapse:collapse;width:100%;margin:0;background:transparent}
    thead th{position:sticky;top:0;background:#fff;border-bottom:1px solid var(--border);padding:8px 10px;text-align:left;z-index:2}
    tbody td{padding:8px 10px;border-bottom:1px solid #f1f1f1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:160px}
    tr:hover td{background:#fff8}
    .summary-controls{display:flex;gap:8px;align-items:center;margin:8px 0}
    .btn{background:var(--accent);color:#fff;padding:8px 12px;border-radius:6px;border:none;cursor:pointer;font-size:13px}
    .muted{color:var(--muted);font-size:13px}
    @media (max-width:900px){.plots{grid-template-columns:1fr}.card-row{grid-template-columns:repeat(auto-fill,minmax(160px,1fr))}.table-wrap{max-height:240px}}
    '''

    # choose baseline
    baseline_idx = 0
    if 'test_id' in df.columns and df['test_id'].notna().any():
        baseline_idx = df.index[df['test_id'].notna()][0]

    metrics_for_cards = ['tcp_dl_mbps', 'tcp_ul_mbps', 'udp_dl_mbps', 'udp_ul_mbps', 'ping_wan_mean_ms']

    try:
        with open(html_path, 'w') as h:
            h.write(f'<!doctype html><html><head><meta charset="utf-8"><title>{title}</title>')
            h.write(f'<style>{css}</style>')
            h.write('</head><body>')
            h.write('<div class="container">')
            h.write(f'<header class="site-header"><div class="inner"><div><h1>{title}</h1><div class="meta">Generated: {now}</div></div>')
            h.write('<div><button onclick="window.print()">Print</button></div></div></header>')

            # cards
            h.write('<section class="card-row">')
            for _, r in df.iterrows():
                label = r.get('test_id') or os.path.basename(r['artifact_dir'])
                h.write('<div class="card">')
                h.write(f'<h4>{label}</h4>')
                for m in metrics_for_cards:
                    val = r.get(m)
                    display = '' if val is None or (isinstance(val, float) and pd.isna(val)) else (f'{val:.2f}' if isinstance(val, float) else str(val))
                    h.write(f'<div><strong>{display}</strong> <small style="color:#666">{m}</small></div>')
                h.write('</div>')
            h.write('</section>')

            # plots
            h.write('<section class="plots">')
            for title_img, path, b64 in images:
                h.write('<div class="card">')
                h.write(f'<h4>{title_img}</h4>')
                h.write(f'<img class="plotimg" src="data:image/png;base64,{b64}" alt="{title_img}"/>')
                h.write('</div>')
            h.write('</section>')

            # table (compact and scrollable, with toggle for full table)
            h.write('<h2>Summary table</h2>')
            h.write('<div class="summary-controls"><input id="search" placeholder="Filter by label or value..." oninput="filterTable()" style="flex:1;padding:8px;border:1px solid #ddd;border-radius:6px">')
            h.write('<button class="btn" onclick="toggleFull()">Toggle full table</button>')
            h.write('</div>')

            # compact scrolling table
            compact_html = df.to_html(index=False, na_rep='', classes='summary-table compact', table_id='compact-table')
            # full table (hidden by default)
            full_html = df.to_html(index=False, na_rep='', classes='summary-table full', table_id='full-table')
            h.write('<div class="table-wrap" id="compact-wrap">')
            h.write(compact_html)
            h.write('</div>')
            h.write('<div style="display:none;" id="full-wrap">')
            h.write(full_html)
            h.write('</div>')
            # comparison (compact, scrollable table like the summary)
            h.write('<h2>Comparison vs baseline</h2>')
            comp_metrics = [c for c in metrics_for_cards if c in df.columns]
            if comp_metrics and len(df) > 1:
                base = df.loc[baseline_idx, comp_metrics].astype(float)
                # wrap comparison table so it scrolls and uses same compact styling
                h.write('<div class="table-wrap" id="comparison-wrap">')
                h.write('<table class="summary-table compact">')
                # header
                h.write('<thead><tr><th>metric</th>')
                for _, r in df.iterrows():
                    h.write(f'<th>{r.get("test_id") or os.path.basename(r["artifact_dir"])}</th>')
                h.write('</tr></thead>')
                h.write('<tbody>')
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
                h.write('</tbody></table>')
                h.write('</div>')
            else:
                h.write('<p>Not enough runs to compare.</p>')

            h.write('<footer style="color:#666;margin-top:20px">Generated by plot_results.py</footer>')

            # JS: filter, toggle and responsive behaviors
            h.write('''
<script>
function filterTable(){
    const q = document.getElementById('search').value.toLowerCase();
    const compactRows = document.querySelectorAll('#compact-wrap .summary-table tbody tr');
    const fullRows = document.querySelectorAll('#full-wrap .summary-table tbody tr');
    [compactRows, fullRows].forEach(nodeList => {
        nodeList.forEach(r => { r.style.display = r.innerText.toLowerCase().includes(q) ? '' : 'none'; });
    });
}
function toggleFull(){
    const f = document.getElementById('full-wrap');
    f.style.display = (f.style.display === 'none') ? 'block' : 'none';
}
// Improve table column sizing: collapse very long labels
document.addEventListener('DOMContentLoaded', ()=>{
    document.querySelectorAll('.summary-table tbody td').forEach(td=>{
        if(td.innerText.length>40) td.title = td.innerText;
    });
});
</script>
''')
            h.write('</div></body></html>')
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
