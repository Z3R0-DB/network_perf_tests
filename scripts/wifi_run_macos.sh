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

# Run iperf with retries using exponential backoff with jitter. Args: output_file -- followed by iperf args (without -J)
run_iperf() {
  local outfile="$1"; shift
  local tmpfile="${outfile}.tmp"
  # more aggressive retry policy: up to 8 attempts, exponential backoff (1,2,4,8,...) seconds, capped
  local max_attempts=8
  local base_delay=1
  local max_backoff=16
  local attempt=1
  while true; do
    log "Running iperf (attempt ${attempt}/${max_attempts}) -> ${outfile}"
    # run iperf and capture JSON to a temp file (capture stdout+stderr)
    "$IPERF" "$@" -J > "$tmpfile" 2>&1 || true

    # quick sanity: file should exist and not contain an "error" key
    if [[ -s "$tmpfile" ]]; then
      if grep -q '"error"' "$tmpfile" 2>/dev/null; then
        log "iperf returned error (attempt ${attempt}): $(grep -m1 '"error"' "$tmpfile" | sed -n '1p')"
      else
        mv "$tmpfile" "$outfile"
        return 0
      fi
    else
      log "iperf produced empty output (attempt ${attempt})"
    fi

    # if we've exhausted attempts, save last output and return failure
    if [[ $attempt -ge $max_attempts ]]; then
      log "iperf failed after ${attempt} attempts; saving last output to ${outfile}"
      mv "$tmpfile" "$outfile" 2>/dev/null || true
      return 1
    fi

    # compute exponential backoff with jitter (seconds, fractional allowed)
    # backoff = base_delay * 2^(attempt-1), capped to max_backoff
    local backoff=$(( base_delay * (1 << (attempt - 1)) ))
    if [[ $backoff -gt $max_backoff ]]; then
      backoff=$max_backoff
    fi
    # jitter in milliseconds [0..1000)
    local jitter_ms=$(( RANDOM % 1000 ))
    # compute sleep time as float: backoff + jitter_ms/1000
    local sleep_time
    sleep_time=$(awk -v b=$backoff -v j=$jitter_ms 'BEGIN{printf "%.3f", b + (j/1000)}')
    log "Retrying iperf after ${sleep_time}s (backoff=${backoff}s jitter=${jitter_ms}ms)"
    attempt=$((attempt+1))
    sleep "$sleep_time"
  done
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

# capture network interface state (macOS) - works for both WiFi and Ethernet
WLAN_RAW_FILE="${OUTDIR}/wlan_${TESTID}_${TS}.txt"
WLAN_SUMMARY_FILE="${OUTDIR}/wlan_${TESTID}_${TS}_summary.json"

# Detect the active network interface
ACTIVE_IF=$(route -n get default 2>/dev/null | awk '/interface:/ {print $2}') || true
INTERFACE_NAME=""
INTERFACE_TYPE=""

if [[ -n "$ACTIVE_IF" ]]; then
  # Get friendly name and type from networksetup
  INTERFACE_INFO=$(networksetup -listallhardwareports 2>/dev/null | grep -B 1 "Device: ${ACTIVE_IF}" | head -1) || true
  INTERFACE_NAME=$(echo "$INTERFACE_INFO" | sed 's/Hardware Port: //' || true)
  
  # Determine interface type
  if [[ "$INTERFACE_NAME" =~ "Wi-Fi" ]]; then
    INTERFACE_TYPE="wifi"
  elif [[ "$INTERFACE_NAME" =~ "Ethernet" ]] || [[ "$INTERFACE_NAME" =~ "USB" ]] || [[ "$INTERFACE_NAME" =~ "Thunderbolt" ]]; then
    INTERFACE_TYPE="ethernet"
  else
    INTERFACE_TYPE="other"
  fi
fi

# Try wdutil for WiFi info, otherwise collect basic interface info
if [[ "$INTERFACE_TYPE" == "wifi" ]] && command -v wdutil >/dev/null 2>&1; then
  RAW=$(sudo -n wdutil info 2>/dev/null || wdutil info 2>/dev/null || true)
  echo "$RAW" > "$WLAN_RAW_FILE"
  log "Captured WiFi output to ${WLAN_RAW_FILE} (using wdutil)"

  # Extract WiFi-specific info from wdutil output
  SSID=$(echo "$RAW" | awk '/^[[:space:]]*SSID[[:space:]]*:/ {gsub(/^[[:space:]]*SSID[[:space:]]*:[[:space:]]*/, ""); print; exit}') || true
  BSSID=$(echo "$RAW" | awk '/^[[:space:]]*BSSID[[:space:]]*:/ {gsub(/^[[:space:]]*BSSID[[:space:]]*:[[:space:]]*/, ""); print; exit}') || true
  LASTTX=$(echo "$RAW" | awk '/^[[:space:]]*Tx Rate[[:space:]]*:/ {print $4; exit}') || true
  CHANNEL=$(echo "$RAW" | awk '/^[[:space:]]*Channel[[:space:]]*:/ {gsub(/^[[:space:]]*Channel[[:space:]]*:[[:space:]]*/, ""); print; exit}') || true

  cat > "$WLAN_SUMMARY_FILE" <<JSON
{
  "timestamp": "${TS}",
  "test_id": "${TESTID}",
  "interface_name": "${INTERFACE_NAME}",
  "interface_type": "${INTERFACE_TYPE}",
  "interface_device": "${ACTIVE_IF}",
  "ssid": "${SSID}",
  "bssid": "${BSSID}",
  "last_tx_rate_mbps": "${LASTTX}",
  "channel": "${CHANNEL}"
}
JSON
  log "Network interface summary written to ${WLAN_SUMMARY_FILE}"
else
  # For Ethernet or when wdutil unavailable, collect basic interface info
  networksetup -listallhardwareports > "$WLAN_RAW_FILE" 2>/dev/null || true
  ifconfig "$ACTIVE_IF" >> "$WLAN_RAW_FILE" 2>/dev/null || true
  
  # Get MAC address and link speed if available
  MAC_ADDR=$(ifconfig "$ACTIVE_IF" 2>/dev/null | awk '/ether/ {print $2}') || true
  LINK_SPEED=$(networksetup -getMedia "$INTERFACE_NAME" 2>/dev/null | grep "Active:" | awk '{print $2}') || true
  
  cat > "$WLAN_SUMMARY_FILE" <<JSON
{
  "timestamp": "${TS}",
  "test_id": "${TESTID}",
  "interface_name": "${INTERFACE_NAME}",
  "interface_type": "${INTERFACE_TYPE}",
  "interface_device": "${ACTIVE_IF}",
  "mac_address": "${MAC_ADDR}",
  "link_speed": "${LINK_SPEED}",
  "ssid": "",
  "bssid": "",
  "last_tx_rate_mbps": "",
  "channel": ""
}
JSON
  log "Network interface summary written to ${WLAN_SUMMARY_FILE}"
fi

# compute ping count ≈5Hz
PING_COUNT=$((DURATION * 5))

log "Running tests against server ${SERVER} for ${DURATION}s, UDP=${UDP_M} Mbps"

# --- Traceroutes (run before bandwidth tests) ---
log "Running traceroute to server ${SERVER}"
# Use perl one-liner for timeout on macOS (timeout command not available by default)
perl -e 'alarm shift; exec @ARGV' 60 traceroute -m 20 -q 2 -w 2 "$SERVER" > "${OUTDIR}/traceroute_${TESTID}_${TS}_server.txt" 2>&1 || true
log "Traceroute to server finished: ${OUTDIR}/traceroute_${TESTID}_${TS}_server.txt"

log "Running traceroute to WAN target 8.8.8.8"
perl -e 'alarm shift; exec @ARGV' 60 traceroute -m 20 -q 2 -w 2 8.8.8.8 > "${OUTDIR}/traceroute_${TESTID}_${TS}_wan.txt" 2>&1 || true
log "Traceroute to WAN finished: ${OUTDIR}/traceroute_${TESTID}_${TS}_wan.txt"

echo "Starting iperf tests..."

# --- TCP Download (reverse) ---
log "Starting TCP download (reverse) test"
run_iperf "${OUTDIR}/iperf_${TESTID}_${TS}_tcp_dl.json" -c "$SERVER" -R -t "$DURATION"
log "TCP download test finished: ${OUTDIR}/iperf_${TESTID}_${TS}_tcp_dl.json"

# --- TCP Upload ---
log "Starting TCP upload test"
run_iperf "${OUTDIR}/iperf_${TESTID}_${TS}_tcp_ul.json" -c "$SERVER" -t "$DURATION"
log "TCP upload test finished: ${OUTDIR}/iperf_${TESTID}_${TS}_tcp_ul.json"

# --- UDP Download (reverse) ---
log "Starting UDP download (reverse) test @ ${UDP_M} Mbps"
run_iperf "${OUTDIR}/iperf_${TESTID}_${TS}_udp_dl.json" -c "$SERVER" -u -b "${UDP_M}M" -R -t "$DURATION"
log "UDP download test finished: ${OUTDIR}/iperf_${TESTID}_${TS}_udp_dl.json"

# --- UDP Upload ---
log "Starting UDP upload test @ ${UDP_M} Mbps"
run_iperf "${OUTDIR}/iperf_${TESTID}_${TS}_udp_ul.json" -c "$SERVER" -u -b "${UDP_M}M" -t "$DURATION"
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
