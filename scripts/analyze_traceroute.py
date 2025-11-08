#!/usr/bin/env python3
"""Analyze traceroute data from network performance tests.

Parses traceroute files, identifies network nodes, and creates visualizations
showing the network topology including forward and return paths.
"""

import argparse
import glob
import os
import re
from collections import defaultdict
from datetime import datetime

import matplotlib.pyplot as plt
import networkx as nx


# Regex to parse traceroute lines
# Format: " 1  gateway (192.168.1.1)  1.234 ms  1.456 ms  1.789 ms"
TRACEROUTE_LINE_RE = re.compile(
    r'^\s*(\d+)\s+([^\(]+?)\s*\(([0-9\.]+)\)\s+([\d\.]+)\s+ms'
)


def parse_traceroute_file(filepath):
    """Parse a traceroute file and extract hop information.
    
    Returns:
        dict: {
            'target': target IP/hostname,
            'hops': [
                {'hop': 1, 'hostname': 'gateway', 'ip': '192.168.1.1', 'rtt_ms': 1.234},
                ...
            ]
        }
    """
    result = {'target': None, 'hops': []}
    
    with open(filepath, 'r') as f:
        lines = f.readlines()
    
    if not lines:
        return result
    
    # First line typically shows target: "traceroute to 8.8.8.8 (8.8.8.8), 30 hops max..."
    first_line = lines[0]
    target_match = re.search(r'traceroute to ([^\s,]+)', first_line)
    if target_match:
        result['target'] = target_match.group(1)
    
    for line in lines[1:]:
        match = TRACEROUTE_LINE_RE.match(line)
        if match:
            hop_num = int(match.group(1))
            hostname = match.group(2).strip()
            ip = match.group(3)
            rtt = float(match.group(4))
            
            result['hops'].append({
                'hop': hop_num,
                'hostname': hostname,
                'ip': ip,
                'rtt_ms': rtt
            })
        elif '*' in line and re.match(r'^\s*\d+\s+\*', line):
            # Handle timeouts: " 5  * * *"
            hop_match = re.match(r'^\s*(\d+)\s+\*', line)
            if hop_match:
                hop_num = int(hop_match.group(1))
                result['hops'].append({
                    'hop': hop_num,
                    'hostname': 'timeout',
                    'ip': 'timeout',
                    'rtt_ms': None
                })
    
    return result


def classify_node(ip, hostname):
    """Classify a network node based on IP address and hostname.
    
    Returns:
        str: One of 'lan', 'gateway', 'radio', 'satellite', 'isp', 'wan'
    """
    if ip == 'timeout':
        return 'unknown'
    
    # Private IP ranges (LAN)
    if ip.startswith('192.168.') or ip.startswith('10.') or ip.startswith('172.'):
        if 'gateway' in hostname.lower() or ip.endswith('.1'):
            return 'gateway'
        return 'lan'
    
    # Check hostname for clues
    hostname_lower = hostname.lower()
    if any(x in hostname_lower for x in ['silvus', 'radio', 'mesh']):
        return 'radio'
    if any(x in hostname_lower for x in ['viasat', 'satellite', 'sat']):
        return 'satellite'
    if any(x in hostname_lower for x in ['isp', 'comcast', 'att', 'verizon', 'spectrum']):
        return 'isp'
    
    # Public IPs are typically WAN
    return 'wan'


def analyze_all_traceroutes(artifacts_root, name_filter=None):
    """Analyze all traceroute files in artifacts directories.
    
    Args:
        artifacts_root: Root directory to search
        name_filter: Optional string to filter artifact names
    
    Returns:
        dict: Analysis results grouped by test run and target
    """
    results = []
    pattern = os.path.join(artifacts_root, "artifacts_*", "traceroute_*.txt")
    
    for filepath in sorted(glob.glob(pattern)):
        dirname = os.path.dirname(filepath)
        artifact_name = os.path.basename(dirname)
        
        # Apply filter if specified
        if name_filter and name_filter.lower() not in artifact_name.lower():
            continue
        filename = os.path.basename(filepath)
        
        # Determine if this is server or wan traceroute
        if 'server' in filename:
            target_type = 'server'
        elif 'wan' in filename:
            target_type = 'wan'
        else:
            target_type = 'unknown'
        
        trace_data = parse_traceroute_file(filepath)
        
        # Include even if no hops were found (to show failures in report)
        results.append({
            'artifact': artifact_name,
            'filepath': filepath,
            'target_type': target_type,
            'target': trace_data['target'],
            'hops': trace_data['hops']
        })
    
    return results


def build_network_graph(traceroute_results):
    """Build a NetworkX graph from traceroute data.
    
    Returns:
        nx.DiGraph: Directed graph with nodes and edges
    """
    G = nx.DiGraph()
    
    # Track all unique nodes and paths
    node_info = {}  # {ip: {'hostname': ..., 'type': ..., 'rtts': []}}
    
    for result in traceroute_results:
        source = 'client'  # Starting point
        
        for hop in result['hops']:
            ip = hop['ip']
            hostname = hop['hostname']
            
            if ip == 'timeout':
                continue
            
            # Track node information
            if ip not in node_info:
                node_info[ip] = {
                    'hostname': hostname,
                    'type': classify_node(ip, hostname),
                    'rtts': []
                }
            
            if hop['rtt_ms'] is not None:
                node_info[ip]['rtts'].append(hop['rtt_ms'])
            
            # Add edge from previous hop to this hop
            if not G.has_edge(source, ip):
                G.add_edge(source, ip, paths=[])
            
            G[source][ip]['paths'].append({
                'artifact': result['artifact'],
                'target_type': result['target_type'],
                'hop_num': hop['hop'],
                'rtt_ms': hop['rtt_ms']
            })
            
            source = ip
        
        # Add edge to final target if we have hops
        if result['hops'] and result['target']:
            target = result['target']
            if not G.has_edge(source, target):
                G.add_edge(source, target, paths=[])
            G[source][target]['paths'].append({
                'artifact': result['artifact'],
                'target_type': result['target_type'],
                'hop_num': len(result['hops']) + 1,
                'rtt_ms': None
            })
    
    # Add node attributes
    for node in G.nodes():
        if node == 'client':
            G.nodes[node]['type'] = 'client'
            G.nodes[node]['hostname'] = 'Test Computer'
            G.nodes[node]['avg_rtt'] = 0
        elif node in node_info:
            G.nodes[node]['hostname'] = node_info[node]['hostname']
            G.nodes[node]['type'] = node_info[node]['type']
            rtts = node_info[node]['rtts']
            G.nodes[node]['avg_rtt'] = sum(rtts) / len(rtts) if rtts else 0
    
    return G


def visualize_network_graph(G, outdir):
    """Create a visualization of the network topology graph."""
    plt.figure(figsize=(16, 12))
    
    # Define colors for different node types
    node_colors = {
        'client': '#4CAF50',      # Green
        'lan': '#2196F3',         # Blue
        'gateway': '#FF9800',     # Orange
        'radio': '#9C27B0',       # Purple
        'satellite': '#F44336',   # Red
        'isp': '#00BCD4',         # Cyan
        'wan': '#607D8B',         # Gray
        'unknown': '#9E9E9E'      # Light Gray
    }
    
    # Assign colors and labels
    colors = []
    labels = {}
    for node in G.nodes():
        node_type = G.nodes[node].get('type', 'unknown')
        colors.append(node_colors.get(node_type, '#9E9E9E'))
        
        hostname = G.nodes[node].get('hostname', node)
        avg_rtt = G.nodes[node].get('avg_rtt', 0)
        
        if node == 'client':
            labels[node] = 'Test Computer'
        else:
            # Create label with hostname/IP and average RTT
            if hostname == node or hostname == 'timeout':
                label = node
            else:
                label = f"{hostname}\n{node}"
            
            if avg_rtt > 0:
                label += f"\n({avg_rtt:.1f}ms)"
            
            labels[node] = label
    
    # Use hierarchical layout
    pos = nx.spring_layout(G, k=2, iterations=50, seed=42)
    
    # Draw the graph
    nx.draw_networkx_nodes(G, pos, node_color=colors, node_size=2000, alpha=0.9)
    nx.draw_networkx_labels(G, pos, labels, font_size=8, font_weight='bold')
    nx.draw_networkx_edges(G, pos, edge_color='gray', arrows=True, 
                          arrowsize=20, width=2, alpha=0.6,
                          connectionstyle='arc3,rad=0.1')
    
    # Add legend
    legend_elements = [
        plt.Line2D([0], [0], marker='o', color='w', label=node_type.capitalize(),
                  markerfacecolor=color, markersize=10)
        for node_type, color in node_colors.items()
    ]
    plt.legend(handles=legend_elements, loc='upper left', fontsize=10)
    
    plt.title('Network Topology from Traceroute Analysis', fontsize=16, fontweight='bold')
    plt.axis('off')
    plt.tight_layout()
    
    # Save the plot
    output_path = os.path.join(outdir, 'network_topology.png')
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Saved network topology visualization: {output_path}")
    plt.close()


def generate_traceroute_report(traceroute_results, G, outdir):
    """Generate an HTML report with traceroute analysis."""
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Traceroute Analysis Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        h1 {{ color: #333; }}
        h2 {{ color: #555; margin-top: 30px; }}
        .summary {{ background: white; padding: 20px; border-radius: 5px; margin-bottom: 20px; }}
        .node {{ background: white; padding: 15px; margin: 10px 0; border-radius: 5px; border-left: 4px solid #2196F3; }}
        .node.gateway {{ border-left-color: #FF9800; }}
        .node.radio {{ border-left-color: #9C27B0; }}
        .node.satellite {{ border-left-color: #F44336; }}
        .node.isp {{ border-left-color: #00BCD4; }}
        .node.wan {{ border-left-color: #607D8B; }}
        table {{ width: 100%; border-collapse: collapse; margin: 10px 0; background: white; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background-color: #2196F3; color: white; }}
        .topology-img {{ max-width: 100%; height: auto; margin: 20px 0; background: white; padding: 20px; border-radius: 5px; }}
    </style>
</head>
<body>
    <h1>Network Traceroute Analysis</h1>
    <p>Generated: {timestamp}</p>
"""
    
    # Summary statistics
    num_runs = len(traceroute_results)
    num_nodes = len(G.nodes()) - 1  # Exclude 'client'
    num_edges = len(G.edges())
    
    html += f"""
    <div class="summary">
        <h2>Summary</h2>
        <ul>
            <li>Total traceroute runs: {num_runs}</li>
            <li>Unique network nodes discovered: {num_nodes}</li>
            <li>Network paths analyzed: {num_edges}</li>
        </ul>
    </div>
"""
    
    # Network topology image
    html += """
    <div class="summary">
        <h2>Network Topology Visualization</h2>
        <img src="network_topology.png" class="topology-img" alt="Network Topology">
    </div>
"""
    
    # Node details
    html += """
    <div class="summary">
        <h2>Network Nodes</h2>
"""
    
    for node in sorted(G.nodes()):
        if node == 'client':
            continue
        
        node_data = G.nodes[node]
        node_type = node_data.get('type', 'unknown')
        hostname = node_data.get('hostname', node)
        avg_rtt = node_data.get('avg_rtt', 0)
        
        # Count how many times this node appeared
        appearances = sum(1 for u, v in G.edges() if v == node)
        
        html += f"""
        <div class="node {node_type}">
            <h3>{hostname}</h3>
            <p><strong>IP:</strong> {node}</p>
            <p><strong>Type:</strong> {node_type.capitalize()}</p>
            <p><strong>Average RTT:</strong> {avg_rtt:.2f} ms</p>
            <p><strong>Appearances in traces:</strong> {appearances}</p>
        </div>
"""
    
    html += "</div>"
    
    # Path details by test run
    html += """
    <div class="summary">
        <h2>Traceroute Paths by Test Run</h2>
"""
    
    for result in traceroute_results:
        html += f"""
        <h3>{result['artifact']} - {result['target_type'].upper()} ({result['target']})</h3>
        <table>
            <tr>
                <th>Hop</th>
                <th>Hostname</th>
                <th>IP Address</th>
                <th>RTT (ms)</th>
                <th>Type</th>
            </tr>
"""
        
        for hop in result['hops']:
            node_type = classify_node(hop['ip'], hop['hostname'])
            rtt_display = f"{hop['rtt_ms']:.2f}" if hop['rtt_ms'] is not None else "timeout"
            
            html += f"""
            <tr>
                <td>{hop['hop']}</td>
                <td>{hop['hostname']}</td>
                <td>{hop['ip']}</td>
                <td>{rtt_display}</td>
                <td>{node_type.capitalize()}</td>
            </tr>
"""
        
        html += "</table>"
    
    html += """
    </div>
</body>
</html>
"""
    
    # Write HTML report
    report_path = os.path.join(outdir, 'traceroute_report.html')
    with open(report_path, 'w') as f:
        f.write(html)
    
    print(f"Saved traceroute report: {report_path}")
    return report_path


def main():
    parser = argparse.ArgumentParser(
        description='Analyze traceroute data from network performance tests'
    )
    parser.add_argument(
        '--artifacts-root',
        default='results',
        help='Root folder to search for artifacts_* dirs'
    )
    parser.add_argument(
        '--outdir',
        default='results/traceroute_analysis',
        help='Where to write traceroute analysis and visualizations'
    )
    parser.add_argument(
        '--filter',
        default=None,
        help='Filter artifacts by name (e.g., "Paolo" to only analyze Paolo tests)'
    )
    parser.add_argument(
        '--open-report',
        action='store_true',
        help='Open the generated HTML report in the default browser'
    )
    
    args = parser.parse_args()
    
    # Create output directory
    os.makedirs(args.outdir, exist_ok=True)
    
    # Analyze all traceroute files
    filter_msg = f" (filtering by '{args.filter}')" if args.filter else ""
    print(f"Analyzing traceroute files in {args.artifacts_root}{filter_msg}...")
    traceroute_results = analyze_all_traceroutes(args.artifacts_root, args.filter)
    
    if not traceroute_results:
        print("No traceroute files found!")
        return
    
    print(f"Found {len(traceroute_results)} traceroute files")
    
    # Build network graph
    print("Building network topology graph...")
    G = build_network_graph(traceroute_results)
    print(f"Graph has {len(G.nodes())} nodes and {len(G.edges())} edges")
    
    # Create visualization
    print("Generating network topology visualization...")
    visualize_network_graph(G, args.outdir)
    
    # Generate HTML report
    print("Generating HTML report...")
    report_path = generate_traceroute_report(traceroute_results, G, args.outdir)
    
    # Open report if requested
    if args.open_report:
        import webbrowser
        webbrowser.open(f'file://{os.path.abspath(report_path)}')
        print("Opened report in default browser")
    
    print("\nTraceroute analysis complete!")


if __name__ == '__main__':
    main()
