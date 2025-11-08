# Network Performance Tests

This project is designed to facilitate testing of wireless networks to measure bandwidth, latency, and jitter between a network card and a router. It provides a command-line interface for users to execute various network performance tests using tools like `iperf` and `ping`.

## Features

- **Bandwidth Testing**: Measure upload and download speeds using `iperf`.
- **Latency Testing**: Perform ICMP ping tests to assess latency to specified targets.
- **WLAN Statistics**: Capture and report WLAN interface statistics and configurations.
- **Cross-Platform Support**: Compatible with both macOS and Windows operating systems.

## Installation

To set up the project, clone the repository and navigate to the project directory:

```bash
git clone <repository-url>
cd network_perf_tests
```

### Dependencies

Install the required dependencies using the following command:

```bash
pip3 install -r requirements.txt
```

It's recommended to use a virtual environment. For example:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

### Finding iperf

Ensure that `iperf` is installed and accessible in your system's PATH. You can use the provided script to find the `iperf` executable:

```bash
bash scripts/find_iperf.sh
```

### macOS run script

There's a convenient macOS helper script at `scripts/wifi_run_macos.sh` that collects iperf runs, pings, and WLAN stats.

Make it executable and run it (example):

```bash
chmod +x scripts/wifi_run_macos.sh
```

To automatically generate plots after the test completes, use the `--auto-plot` flag. This requires the Python analysis dependencies from `requirements.txt` (pandas, matplotlib, seaborn):

```bash
./scripts/wifi_run_macos.sh --server iperf.he.net --test-id macbook_wifi --run-name testA --duration 30 --udp-target-mbps 100 --verbose --auto-plot
```

Artifacts are written into an `artifacts_<testid>[_<run-name>]_YYYYMMDD_HHMMSS/` folder. The analyzer writes `analysis_output/summary.csv` and several PNGs by default.

### Running Tests

You can run the network performance tests using the command line. The entry point for the application is located in `src/__main__.py`. Here’s an example of how to execute a test:

```bash
python3 -m src --server <server-ip> --test-id <test-id> --duration <duration> --udp-target-mbps <target-mbps>

We will test against the local fremont iperf server: iperf.he.net
python3 -m src --server iperf.he.net --test-id macbook_wifi --duration 10 --udp-target-mbps <target-mbps>
```

Replace `<server-ip>`, `<test-id>`, `<duration>`, and `<target-mbps>` with your desired values.

## Directory Structure

- `src/`: Contains the main application code.
- `scripts/`: Includes utility scripts for setup and configuration.
- `tests/`: Contains unit tests for the application.
- `pyproject.toml`: Project configuration file.
- `requirements.txt`: Lists required Python packages.
- `.gitignore`: Specifies files to be ignored by version control.
- `LICENSE`: Licensing information for the project.

## Contributing

Contributions are welcome! Please submit a pull request or open an issue for any enhancements or bug fixes.

## License

This project is licensed under the MIT License. See the LICENSE file for more details.