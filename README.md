# Network Performance Testing Suite

A comprehensive network performance testing toolkit designed for measuring bandwidth, latency, jitter, and packet loss across wireless and ethernet networks. Ideal for autonomous vessel diagnostics, satellite communications testing, and network infrastructure validation.

## Table of Contents
- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage](#usage)
  - [Single Test Execution](#single-test-execution)
  - [Loop Testing](#loop-testing)
  - [Test Parameters](#test-parameters)
- [Results and Analysis](#results-and-analysis)
  - [Artifact Structure](#artifact-structure)
  - [Generating Reports](#generating-reports)
  - [Network Topology Analysis](#network-topology-analysis)
- [Advanced Features](#advanced-features)
- [Public iperf3 Servers](#public-iperf3-servers)
- [Troubleshooting](#troubleshooting)

## Features

### Core Testing Capabilities
- ✅ **TCP Bandwidth Testing**: Upload and download throughput measurements
- ✅ **UDP Bandwidth Testing**: Controlled-rate UDP testing with jitter and packet loss metrics
- ✅ **Latency Testing**: ICMP ping tests to gateway and WAN targets
- ✅ **Traceroute Analysis**: Network path discovery and hop-by-hop latency
- ✅ **Network Interface Detection**: Automatic WiFi/Ethernet interface identification
- ✅ **WiFi Statistics**: RSSI, BSSID, channel, and link speed capture (macOS)

### Analysis & Reporting
- 📊 **Automated HTML Reports**: Summary statistics with comparison plots
- 📈 **Time-Series Visualization**: Bandwidth, latency, jitter, and packet loss trends
- 🗺️ **Network Topology Graphs**: Visual representation of network paths
- 📋 **CSV Export**: Summary data for external analysis
- 🔄 **Continuous Testing**: Loop mode for long-duration monitoring

### Platform Support
- 🍎 **macOS**: Full support with native WiFi tools (wdutil)
- 🪟 **Windows**: PowerShell scripts (see `wifi_tests/`)
- 🐧 **Linux**: Compatible with standard network tools

## Installation

### Prerequisites
- **iperf3**: Network bandwidth testing tool
- **Python 3.8+**: For analysis and plotting
- **Bash/Zsh**: For test execution scripts (macOS/Linux)

### macOS Installation

#### 1. Install iperf3
```bash
brew install iperf3
```

Verify installation:
```bash
iperf3 --version
```

#### 2. Install Python Dependencies
```bash
# Navigate to project directory
cd network_perf_tests

# Install required packages
pip3 install --break-system-packages pandas matplotlib seaborn networkx

# Or using a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate
pip3 install pandas matplotlib seaborn networkx
```

#### 3. Make Scripts Executable
```bash
chmod +x scripts/wifi_run_macos.sh
```

### Windows Installation
See `wifi_tests/wifi_test_suite.ps1` for PowerShell-based testing on Windows.

## Quick Start

### Run a Single Test
```bash
./scripts/wifi_run_macos.sh \
  --server 109.61.86.65 \
  --test-id My_Network_Test \
  --run-name testA \
  --duration 30 \
  --udp-target-mbps 50 \
  --verbose \
  --auto-plot
```

This will:
1. Run traceroute to server and WAN
2. Execute TCP download/upload tests
3. Execute UDP download/upload tests at 50 Mbps
4. Ping gateway and 8.8.8.8
5. Capture WiFi/network interface stats
6. Generate HTML report with plots
7. Automatically open report in browser

### Run Continuous Tests (Loop Mode)
```bash
./scripts/wifi_run_macos.sh \
  --server 109.61.86.65 \
  --test-id Boston_Monitor \
  --duration 30 \
  --udp-target-mbps 50 \
  --loop-minutes 120 \
  --loop-interval 60 \
  --verbose \
  --auto-plot
```

This runs 30-second tests every 60 seconds for 2 hours, automatically naming iterations (test1, test2, test3...).

## Usage

### Single Test Execution

#### Basic Command Structure
```bash
./scripts/wifi_run_macos.sh --server SERVER --test-id TEST_ID [OPTIONS]
```

#### Required Parameters
- `--server SERVER`: iperf3 server IP or hostname
- `--test-id TEST_ID`: Identifier for this test series (e.g., "macbook_wifi", "vessel_network")

#### Optional Parameters
- `--run-name NAME`: Custom name for this test run (e.g., "testA", "baseline")
- `--duration N`: Duration of each iperf test in seconds (default: 30)
- `--udp-target-mbps M`: Target UDP bandwidth in Mbps (default: 100)
- `--verbose`: Enable detailed logging
- `--auto-plot`: Automatically generate and open HTML report after test

#### Examples

**Quick test with default settings:**
```bash
./scripts/wifi_run_macos.sh --server 100.101.52.16 --test-id vessel_test
```

**High-bandwidth test with verbose logging:**
```bash
./scripts/wifi_run_macos.sh \
  --server 185.93.1.65 \
  --test-id high_bandwidth \
  --run-name test1 \
  --duration 60 \
  --udp-target-mbps 1000 \
  --verbose \
  --auto-plot
```

**Low-bandwidth test for satellite connections:**
```bash
./scripts/wifi_run_macos.sh \
  --server 109.61.86.65 \
  --test-id viasat_test \
  --duration 30 \
  --udp-target-mbps 50 \
  --verbose \
  --auto-plot
```

### Loop Testing

Loop testing runs multiple test iterations over a specified time period, ideal for monitoring network stability and performance trends.

#### Loop Parameters
- `--loop-minutes N`: Run tests continuously for N minutes
- `--loop-interval N`: Wait N seconds between iterations (default: 60)

#### Loop Examples

**2-hour monitoring with 2-minute intervals:**
```bash
./scripts/wifi_run_macos.sh \
  --server 109.61.86.65 \
  --test-id daily_monitor \
  --duration 30 \
  --udp-target-mbps 50 \
  --loop-minutes 120 \
  --loop-interval 120 \
  --verbose \
  --auto-plot
```

**All-day monitoring (8 hours) with 5-minute intervals:**
```bash
./scripts/wifi_run_macos.sh \
  --server 100.101.52.16 \
  --test-id vessel_ops \
  --duration 30 \
  --udp-target-mbps 50 \
  --loop-minutes 480 \
  --loop-interval 300 \
  --verbose \
  --auto-plot
```

**Intensive testing with 30-second intervals for 1 hour:**
```bash
./scripts/wifi_run_macos.sh \
  --server 109.61.86.65 \
  --test-id stress_test \
  --duration 10 \
  --udp-target-mbps 100 \
  --loop-minutes 60 \
  --loop-interval 30 \
  --verbose \
  --auto-plot
```

**Custom run names with loop mode:**
```bash
./scripts/wifi_run_macos.sh \
  --server 109.61.86.65 \
  --test-id experiment \
  --run-name trial \
  --loop-minutes 30 \
  --loop-interval 60 \
  --verbose \
  --auto-plot
```
This creates: `trial1`, `trial2`, `trial3`, etc.

### Test Parameters

#### Duration Selection
- **10 seconds**: Quick connectivity checks
- **30 seconds**: Standard testing (recommended)
- **60 seconds**: Detailed analysis, better statistics

#### UDP Target Bandwidth Guidelines
- **10 Mbps**: Minimal telemetry and low-quality video
- **25-50 Mbps**: Single HD video stream + telemetry (recommended for vessel ops)
- **100 Mbps**: Multiple HD streams with headroom
- **500-1000 Mbps**: High-bandwidth infrastructure testing

**Note**: For satellite and Silvus radio links, use 50 Mbps or less to avoid overwhelming the connection.

## Results and Analysis

### Artifact Structure

Test results are stored in the `results/` directory with the following structure:

```
results/
├── artifacts_<test_id>_<run_name>_<timestamp>/
│   ├── iperf_<test_id>_<timestamp>_tcp_dl.json      # TCP download results
│   ├── iperf_<test_id>_<timestamp>_tcp_ul.json      # TCP upload results
│   ├── iperf_<test_id>_<timestamp>_udp_dl.json      # UDP download results
│   ├── iperf_<test_id>_<timestamp>_udp_ul.json      # UDP upload results
│   ├── ping_<test_id>_<timestamp>_gw.txt            # Gateway ping results
│   ├── ping_<test_id>_<timestamp>_wan.txt           # WAN ping results (8.8.8.8)
│   ├── traceroute_<test_id>_<timestamp>_server.txt  # Traceroute to iperf server
│   ├── traceroute_<test_id>_<timestamp>_wan.txt     # Traceroute to 8.8.8.8
│   ├── wlan_<test_id>_<timestamp>.txt               # Raw WiFi/interface info
│   └── wlan_<test_id>_<timestamp>_summary.json      # Parsed network interface data
└── analysis_output/
    ├── summary.csv                                   # Combined results from all tests
    ├── comparison_report.html                        # Interactive HTML report
    ├── plot_tcp_bandwidth.png                        # TCP throughput comparison
    ├── plot_udp_bandwidth.png                        # UDP throughput comparison
    ├── plot_latency.png                              # Latency comparison
    ├── plot_udp_jitter.png                           # UDP jitter comparison
    └── plot_udp_packet_loss.png                      # UDP packet loss comparison
```

### Generating Reports

#### Automatic Report Generation
When using `--auto-plot`, reports are generated automatically after each test (or after each loop iteration).

#### Manual Report Generation
Regenerate reports anytime from existing test data:

```bash
python3 scripts/plot_results.py \
  --artifacts-root results \
  --outdir results/analysis_output \
  --open-report
```

#### Report Contents
The HTML report includes:
- **Summary Statistics Table**: All tests with key metrics
- **TCP Bandwidth Plots**: Upload and download throughput over time
- **UDP Bandwidth Plots**: Upload and download throughput over time
- **Latency Plots**: Gateway and WAN ping latency with mean/median/P95
- **UDP Jitter Plots**: Jitter measurements (UDP only)
- **UDP Packet Loss Plots**: Packet loss percentage (UDP only)

#### CSV Export
Access raw data in `results/analysis_output/summary.csv` for:
- Custom analysis
- Importing into Excel/Google Sheets
- Integration with other tools

### Network Topology Analysis

Generate network topology visualizations from traceroute data:

```bash
python3 scripts/analyze_traceroute.py \
  --artifacts-root results \
  --outdir results/traceroute_analysis \
  --open-report
```

#### Filter Specific Tests
Analyze only tests matching a pattern:
```bash
python3 scripts/analyze_traceroute.py \
  --artifacts-root results \
  --outdir results/traceroute_analysis_paolo \
  --filter paolo \
  --open-report
```

#### Topology Report Features
- **Network Graph Visualization**: Color-coded nodes by type (client, LAN, gateway, radio, satellite, ISP, WAN, iperf server)
- **Edge Latency Display**: Average RTT shown on connection lines between nodes
- **Traffic Flow Indicators**: 
  - Arrows show direction of data flow
  - Line thickness indicates usage frequency (thicker = more frequently used)
  - Usage count displayed on edges (e.g., "2x" means used twice)
  - Color-coded by usage: light gray (single use), medium gray (dual use), dark gray (heavy use 3+)
- **Hop-by-Hop Analysis**: Detailed latency at each hop
- **Path Summary**: Number of hops, total nodes, unique paths
- **Node Classification**: Automatic identification of network segments

#### Node Types
- 🔵 **Client**: Your local machine
- 🟢 **LAN**: Local network devices
- 🟡 **Gateway**: Router/gateway devices
- 🟠 **Radio**: Silvus or other radio equipment
- 🔴 **Satellite**: Viasat or other satellite terminals
- 🟣 **ISP**: Internet service provider infrastructure
- ⚫ **WAN**: Internet backbone and destination servers
- 🟨 **iperf Server**: The iperf3 server endpoint being tested (highlighted in gold)
- 💗 **Endpoint**: Final destinations like DNS servers (8.8.8.8) or other test targets (highlighted in deep pink)

## Advanced Features

### Interface Detection
The script automatically detects and logs:
- **WiFi**: SSID, BSSID, RSSI, channel, link speed (via `wdutil` on macOS)
- **Ethernet**: Interface name, device, MAC address, link speed
- **Thunderbolt/USB**: Network adapters

### Gateway Auto-Detection
Automatically discovers and pings your default gateway using:
```bash
route -n get default | awk '/gateway/ {print $2}'
```

### Retry Logic
iperf tests use exponential backoff with jitter:
- Up to 8 retry attempts
- Base delay: 1 second
- Maximum backoff: 16 seconds
- Handles temporary network interruptions gracefully

### Traceroute Timeout
Uses Perl-based timeout for macOS compatibility:
```bash
perl -e 'alarm shift; exec @ARGV' 60 traceroute -m 20 -q 2 -w 2 <target>
```
- 60-second total timeout
- Maximum 20 hops
- 2 queries per hop
- 2-second wait per query

## Public iperf3 Servers

### Recommended Servers

#### Boston, USA (East Coast)
```bash
--server 109.61.86.65
```
- Location: Boston, US
- Bandwidth: 2x10 Gbps
- Supports: TCP, UDP (-R, -u flags)
- Port: 5201 (default)

#### California, USA (West Coast)
```bash
--server iperf.he.net
```
- Provider: Hurricane Electric
- Supports: TCP, UDP
- Port: 5201

#### European Test Server
```bash
--server 185.93.1.65
```
- Supports: TCP, UDP
- Port: 5201

### Private Server Setup
If testing against your own iperf3 server:

**Server side:**
```bash
iperf3 -s -p 5201
```

**Client side (this script):**
```bash
./scripts/wifi_run_macos.sh --server <your-server-ip> --test-id my_test
```

## Troubleshooting

### iperf3 Not Found
```bash
# Install via Homebrew (macOS)
brew install iperf3

# Verify installation
iperf3 --version
```

### Python Packages Missing
```bash
pip3 install --break-system-packages pandas matplotlib seaborn networkx
```

Or use a virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip3 install pandas matplotlib seaborn networkx
```

### wdutil Requires sudo
The script attempts `sudo -n wdutil` (no password prompt) first, then falls back to regular `wdutil`. If you see permission errors:

```bash
# Allow sudo without password for wdutil (optional)
sudo visudo
# Add: your_username ALL=(ALL) NOPASSWD: /usr/sbin/wdutil
```

### Connection Refused / No Route to Host
- Verify iperf3 server is running: `iperf3 -c <server> -t 5`
- Check firewall settings on server
- Ensure network connectivity: `ping <server>`

### Empty Traceroute Files
If traceroute files show timeout errors, the script now uses Perl-based timeout (fixed in latest version). Re-run tests to capture proper traceroute data.

### Report Not Opening Automatically
Manually open the report:
```bash
open results/analysis_output/comparison_report.html
```

Or specify the full path:
```bash
python3 scripts/plot_results.py \
  --artifacts-root results \
  --outdir results/analysis_output \
  --open-report
```

## Example Workflows

### Baseline Network Testing
```bash
# Test 1: High bandwidth baseline
./scripts/wifi_run_macos.sh \
  --server 109.61.86.65 \
  --test-id baseline \
  --run-name high_bw \
  --duration 30 \
  --udp-target-mbps 100 \
  --verbose --auto-plot

# Test 2: Low bandwidth (realistic vessel ops)
./scripts/wifi_run_macos.sh \
  --server 109.61.86.65 \
  --test-id baseline \
  --run-name low_bw \
  --duration 30 \
  --udp-target-mbps 50 \
  --verbose --auto-plot
```

### Continuous Monitoring
```bash
# Monitor network for 4 hours with 5-minute intervals
./scripts/wifi_run_macos.sh \
  --server 100.101.52.16 \
  --test-id vessel_monitor \
  --duration 30 \
  --udp-target-mbps 50 \
  --loop-minutes 240 \
  --loop-interval 300 \
  --verbose --auto-plot
```

### Pre/Post Configuration Testing
```bash
# Before configuration change
./scripts/wifi_run_macos.sh \
  --server 109.61.86.65 \
  --test-id config_test \
  --run-name before \
  --duration 30 \
  --udp-target-mbps 50 \
  --verbose --auto-plot

# (Make configuration changes)

# After configuration change
./scripts/wifi_run_macos.sh \
  --server 109.61.86.65 \
  --test-id config_test \
  --run-name after \
  --duration 30 \
  --udp-target-mbps 50 \
  --verbose --auto-plot

# Compare results in the HTML report
```

## Contributing

Contributions welcome! Areas for improvement:
- Linux-specific WiFi statistics collection
- Windows Bash/WSL support
- Additional network metrics (DNS resolution time, HTTP latency)
- Real-time plotting during long test runs
- Database storage for historical analysis

## License

This project is licensed under the MIT License. See the LICENSE file for details.

## Support

For issues, questions, or feature requests, please open an issue on GitHub.

---

**Note**: This toolkit is designed for network diagnostics and performance validation. Always ensure you have permission to run bandwidth tests against any iperf3 server you use.
