# wifi_run.ps1 - Windows harness for Wi‑Fi tests (iperf3 + ping + WLAN stats)
# Usage:
#   .\wifi_run.ps1 -Server 192.0.2.10 -TestId NIC_A_Pos0 -Duration 30 -UdpTargetMbps 100
# Notes:
#   - Requires iperf3.exe in PATH (or place iperf3.exe in the same folder as this script).
#   - Produces JSON (iperf_*), TXT ping logs (ping_*), and WLAN interface snapshot (wlan_*).

param(
  [Parameter(Mandatory=$true)][string]$Server,
  [Parameter(Mandatory=$true)][string]$TestId,
  [int]$Duration = 30,
  [int]$UdpTargetMbps = 100
)

$ErrorActionPreference = "Stop"

function Resolve-IperfPath {
  $candidates = @(
    (Join-Path -Path (Split-Path -Parent $MyInvocation.MyCommand.Path) -ChildPath "iperf3.exe"),
    "iperf3.exe"
  )
  foreach ($c in $candidates) {
    try {
      $p = (Get-Command $c -ErrorAction Stop).Source
      if ($p) { return $p }
    } catch {}
  }
  throw "iperf3.exe not found. Put iperf3.exe next to this script or add it to PATH."
}

$iperf = Resolve-IperfPath
$ts = Get-Date -Format "yyyyMMdd_HHmmss"

# Snapshot WLAN / NIC state BEFORE test
$wlanFile = "wlan_{0}_{1}.txt" -f $TestId, $ts
"netsh wlan show interfaces" | Out-File -Encoding ascii $wlanFile
try {
  "----- Get-NetAdapter (active) -----" | Out-File -Append -Encoding ascii $wlanFile
  Get-NetAdapter | Sort-Object -Property Status,Name | Format-Table -AutoSize | Out-String | Out-File -Append -Encoding ascii $wlanFile
  "----- Get-NetAdapterAdvancedProperty (wifi) -----" | Out-File -Append -Encoding ascii $wlanFile
  Get-NetAdapterAdvancedProperty -Name * | Format-Table -AutoSize | Out-String | Out-File -Append -Encoding ascii $wlanFile
} catch {}

# Compute ping count ~5Hz
$PingCount = [int]($Duration * 5)

# Figure out default gateway
$gw = (Get-NetRoute -DestinationPrefix "0.0.0.0/0" |
      Sort-Object -Property RouteMetric |
      Select-Object -First 1).NextHop

if (-not $gw) { throw "Default gateway not found. Are you connected?" }

Write-Host "Running tests against server $Server for ${Duration}s, UDP=${UdpTargetMbps} Mbps"

# --- TCP Download (reverse) ---
& $iperf -c $Server -R -t $Duration -J | Out-File -Encoding ascii ("iperf_{0}_{1}_tcp_dl.json" -f $TestId,$ts)

# --- TCP Upload ---
& $iperf -c $Server -t $Duration -J | Out-File -Encoding ascii ("iperf_{0}_{1}_tcp_ul.json" -f $TestId,$ts)

# --- UDP Download (reverse) ---
& $iperf -c $Server -u -b ("{0}M" -f $UdpTargetMbps) -R -t $Duration -J | Out-File -Encoding ascii ("iperf_{0}_{1}_udp_dl.json" -f $TestId,$ts)

# --- UDP Upload ---
& $iperf -c $Server -u -b ("{0}M" -f $UdpTargetMbps) -t $Duration -J | Out-File -Encoding ascii ("iperf_{0}_{1}_udp_ul.json" -f $TestId,$ts)

# --- ICMP pings to gateway and WAN target ---
# Gateway
ping.exe -n $PingCount $gw | Out-File -Encoding ascii ("ping_{0}_{1}_gw.txt" -f $TestId,$ts)
# WAN target (Google DNS; change if desired)
ping.exe -n $PingCount 8.8.8.8 | Out-File -Encoding ascii ("ping_{0}_{1}_wan.txt" -f $TestId,$ts)

Write-Host "Done. Artifacts written with timestamp $ts."