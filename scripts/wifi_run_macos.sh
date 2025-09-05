#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<EOF
Usage: $0 --server SERVER --test-id ID [--duration N] [--udp-target-mbps M]
Defaults: duration=30, udp-target-mbps=100
Example:
  $0 --server iperf.he.net --test-id macbook_wifi --duration 10 --udp-target-mbps 50
EOF
  exit 1
}

# defaults
DURATION=30
UDP_M=100
RUN_NAME=""
VERBOSE=0
AUTO_PLOT=0

log() {
  if [[ $VERBOSE -eq 1 ]]; then
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"
  fi
}

# parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --server) SERVER="$2"; shift 2;;
    --test-id) TESTID="$2"; shift 2;;
    --duration) DURATION="$2"; shift 2;;
    --udp-target-mbps) UDP_M="$2"; shift 2;;
  --run-name) RUN_NAME="$2"; shift 2;;
  --verbose) VERBOSE=1; shift 1;;
  --auto-plot) AUTO_PLOT=1; shift 1;;
    -h|--help) usage;;
    *) echo "Unknown arg: $1"; usage;;
  esac
done

if [[ -z "${SERVER:-}" || -z "${TESTID:-}" ]]; then
  usage
fi

# find iperf3
IPERF=$(command -v iperf3 || true)
if [[ -z "$IPERF" ]]; then
  echo "iperf3 not found in PATH. Install with: brew install iperf3"
  exit 2
fi

TS=$(date +%Y%m%d_%H%M%S)
BASE_RESULTS_DIR="results"
mkdir -p "$BASE_RESULTS_DIR"
if [[ -n "$RUN_NAME" ]]; then
  OUTDIR="${BASE_RESULTS_DIR}/artifacts_${TESTID}_${RUN_NAME}_${TS}"
else
  OUTDIR="${BASE_RESULTS_DIR}/artifacts_${TESTID}_${TS}"
fi
mkdir -p "$OUTDIR"

log "Starting test run. server=${SERVER}, test_id=${TESTID}, run_name=${RUN_NAME}, duration=${DURATION}, udp_target_mbps=${UDP_M}"

# capture wifi state (macOS) and parse key metrics
AIRPORT="/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport"
WLAN_RAW_FILE="${OUTDIR}/wlan_${TESTID}_${TS}.txt"
WLAN_SUMMARY_FILE="${OUTDIR}/wlan_${TESTID}_${TS}_summary.json"

if [[ -x "$AIRPORT" ]]; then
  RAW=$($AIRPORT -I 2>/dev/null || true)
  echo "$RAW" > "$WLAN_RAW_FILE"
  log "Captured WLAN raw output to ${WLAN_RAW_FILE}"

  # Extract common keys (agrCtlRSSI or RSSI), agrCtlNoise, lastTxRate, channel, SSID, BSSID
  RSSI=$(echo "$RAW" | awk -F": " '/agrCtlRSSI|RSSI:/ {print $2; exit}') || true
  NOISE=$(echo "$RAW" | awk -F": " '/agrCtlNoise|Noise:/ {print $2; exit}') || true
  LASTTX=$(echo "$RAW" | awk -F": " '/lastTxRate/ {print $2; exit}') || true
  CHANNEL=$(echo "$RAW" | awk -F": " '/channel/ {print $2; exit}') || true
  SSID=$(echo "$RAW" | sed -n 's/^ *SSID: *//p' | head -n1 || true)
  BSSID=$(echo "$RAW" | awk -F": " '/BSSID/ {print $2; exit}') || true

  # normalize numeric values
  RSSI_VAL=""
  NOISE_VAL=""
  if [[ -n "$RSSI" ]]; then RSSI_VAL=$(echo "$RSSI" | tr -d '\r') || true; fi
  if [[ -n "$NOISE" ]]; then NOISE_VAL=$(echo "$NOISE" | tr -d '\r') || true; fi

  # compute signal percent (rough heuristic) and SNR
  SIGNAL_PCT="null"
  SNR="null"
  if [[ -n "$RSSI_VAL" && -n "$NOISE_VAL" ]]; then
    # ensure integers
    RSSI_INT=$(echo "$RSSI_VAL" | awk '{print int($0)}')
    NOISE_INT=$(echo "$NOISE_VAL" | awk '{print int($0)}')
    if [[ $RSSI_INT -ge -50 ]]; then
      SIGNAL_PCT=100
    elif [[ $RSSI_INT -le -100 ]]; then
      SIGNAL_PCT=0
    else
      SIGNAL_PCT=$((2*(RSSI_INT + 100)))
    fi
    SNR=$((RSSI_INT - NOISE_INT))
  elif [[ -n "$RSSI_VAL" ]]; then
    RSSI_INT=$(echo "$RSSI_VAL" | awk '{print int($0)}')
    if [[ $RSSI_INT -ge -50 ]]; then
      SIGNAL_PCT=100
    elif [[ $RSSI_INT -le -100 ]]; then
      SIGNAL_PCT=0
    else
      SIGNAL_PCT=$((2*(RSSI_INT + 100)))
    fi
  fi

  # write JSON summary (minimal, human-readable)
  cat > "$WLAN_SUMMARY_FILE" <<JSON
{
  "timestamp": "${TS}",
  "test_id": "${TESTID}",
  "ssid": "${SSID}",
  "bssid": "${BSSID}",
  "rssi": ${RSSI_VAL:-null},
  "noise": ${NOISE_VAL:-null},
  "snr": ${SNR},
  "signal_percent": ${SIGNAL_PCT},
  "last_tx_rate_mbps": "${LASTTX}",
  "channel": "${CHANNEL}"
}
JSON
  log "WLAN summary written to ${WLAN_SUMMARY_FILE}"
else
  echo "airport utility not found. Falling back to networksetup/ifconfig output."
  networksetup -listallhardwareports > "$WLAN_RAW_FILE" 2>/dev/null || true
  ifconfig > "${OUTDIR}/ifconfig_${TESTID}_${TS}.txt" 2>/dev/null || true
fi

# compute ping count ≈5Hz
PING_COUNT=$((DURATION * 5))

log "Running tests against server ${SERVER} for ${DURATION}s, UDP=${UDP_M} Mbps"

echo "Starting iperf tests..."

# --- TCP Download (reverse) ---
log "Starting TCP download (reverse) test"
"$IPERF" -c "$SERVER" -R -t "$DURATION" -J > "${OUTDIR}/iperf_${TESTID}_${TS}_tcp_dl.json" 2>&1 || true
log "TCP download test finished: ${OUTDIR}/iperf_${TESTID}_${TS}_tcp_dl.json"

# --- TCP Upload ---
log "Starting TCP upload test"
"$IPERF" -c "$SERVER" -t "$DURATION" -J > "${OUTDIR}/iperf_${TESTID}_${TS}_tcp_ul.json" 2>&1 || true
log "TCP upload test finished: ${OUTDIR}/iperf_${TESTID}_${TS}_tcp_ul.json"

# --- UDP Download (reverse) ---
log "Starting UDP download (reverse) test @ ${UDP_M} Mbps"
"$IPERF" -c "$SERVER" -u -b "${UDP_M}M" -R -t "$DURATION" -J > "${OUTDIR}/iperf_${TESTID}_${TS}_udp_dl.json" 2>&1 || true
log "UDP download test finished: ${OUTDIR}/iperf_${TESTID}_${TS}_udp_dl.json"

# --- UDP Upload ---
log "Starting UDP upload test @ ${UDP_M} Mbps"
"$IPERF" -c "$SERVER" -u -b "${UDP_M}M" -t "$DURATION" -J > "${OUTDIR}/iperf_${TESTID}_${TS}_udp_ul.json" 2>&1 || true
log "UDP upload test finished: ${OUTDIR}/iperf_${TESTID}_${TS}_udp_ul.json"

# --- ICMP pings to gateway and WAN target ---
GW=$(route -n get default | awk '/gateway/ {print $2}') || true
if [[ -n "$GW" ]]; then
  log "Pinging gateway ${GW} (${PING_COUNT} samples)"
  ping -c "$PING_COUNT" "$GW" > "${OUTDIR}/ping_${TESTID}_${TS}_gw.txt" 2>&1 || true
  log "Gateway ping finished: ${OUTDIR}/ping_${TESTID}_${TS}_gw.txt"
else
  echo "Default gateway not found; skipping gateway ping"
fi

# WAN target (Google DNS)
log "Pinging WAN target 8.8.8.8 (${PING_COUNT} samples)"
ping -c "$PING_COUNT" 8.8.8.8 > "${OUTDIR}/ping_${TESTID}_${TS}_wan.txt" 2>&1 || true
log "WAN ping finished: ${OUTDIR}/ping_${TESTID}_${TS}_wan.txt"

echo "Done. Artifacts written to ${OUTDIR}."

if [[ $VERBOSE -eq 1 ]]; then
  echo "Summary files:"
  ls -1 "$OUTDIR"
fi

# Optionally run analysis/plotting automatically
if [[ $AUTO_PLOT -eq 1 ]]; then
  log "Auto-plot enabled: running analysis script"
  # prefer venv/python in repo, fall back to system
    if command -v python3 >/dev/null 2>&1; then
    # try both relative locations
    if [[ -f "scripts/plot_results.py" ]]; then
      python3 scripts/plot_results.py --artifacts-root ${BASE_RESULTS_DIR} --outdir ${BASE_RESULTS_DIR}/analysis_output --open-report || log "plot_results.py failed"
    elif [[ -f "../scripts/plot_results.py" ]]; then
      python3 ../scripts/plot_results.py --artifacts-root ${BASE_RESULTS_DIR} --outdir ${BASE_RESULTS_DIR}/analysis_output --open-report || log "plot_results.py failed"
    else
      log "plot_results.py not found in expected paths; skipping auto-plot"
    fi
  else
    log "python3 not found in PATH; cannot run auto-plot"
  fi
fi
