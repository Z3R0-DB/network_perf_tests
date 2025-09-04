<#
WiFi Test Suite + Auto Plots (Windows)
Author: ChatGPT
Purpose: End-to-end Wiâ€‘Fi testing with automatic plots & per-run HTML reports.
Prereqs:
  - Windows 10/11 with PowerShell 7+ recommended (Windows PowerShell works too)
  - iperf3.exe in PATH (e.g., Chocolatey: choco install iperf3)
  - A wired iperf3 server on your LAN: `iperf3 -s` on a machine connected via Ethernet
Outputs:
  - Per-run folder under .\wifi_tests\<run_id> with iperf JSON, ping CSVs, plots (PNG), and report.html
  - Master CSV at .\wifi_tests\wifi_master.csv (one row per run)
#>

param()

# ------------------------------
# Globals & helpers
# ------------------------------
$Global:WifiOutDir = Join-Path $PWD "wifi_tests"
$Global:WifiMasterCsv = Join-Path $Global:WifiOutDir "wifi_master.csv"

function Ensure-Dir([string]$Path) {
  if(-not (Test-Path $Path)) { New-Item -ItemType Directory -Path $Path | Out-Null }
}

function Get-DefaultGateway {
  try {
    $gw = (Get-NetRoute -DestinationPrefix "0.0.0.0/0" | Sort-Object -Property RouteMetric | Select-Object -First 1).NextHop
    if(-not $gw) { throw "No default route found" }
    return $gw
  } catch {
    throw "Failed to obtain default gateway: $_"
  }
}

function Get-WlanSnapshot {
    # Get the raw output and convert to string array
    $out = @(netsh wlan show interfaces | Where-Object { $_ -match '\S' })
    
    # Initialize the result object
    $obj = [ordered]@{
        Timestamp     = (Get-Date).ToString("s")
        InterfaceName = ""
        SSID         = ""
        BSSID        = ""
        RadioType    = ""
        Channel      = ""
        SignalPct    = $null
        SignalDbm    = $null
        RxRateMbps   = $null
        TxRateMbps   = $null
        State        = ""
        Band         = ""
    }

    # Debug output
    Write-Debug "Processing $(($out | Measure-Object).Count) lines from netsh"
    
    # Process each line
    foreach($line in $out) {
        Write-Debug "Processing line: $line"
        
        if($line -match '^\s*Name\s*:\s*(.+)$') { 
            $obj.InterfaceName = $matches[1].Trim() 
            Write-Debug "Found Interface: $($obj.InterfaceName)"
        }
        elseif($line -match '^\s*State\s*:\s*(.+)$') { 
            $obj.State = $matches[1].Trim() 
        }
        elseif($line -match '^\s*SSID\s*:\s*(.+)$') { 
            $obj.SSID = $matches[1].Trim() 
        }
        elseif($line -match '^\s*AP BSSID\s*:\s*(.+)$') { 
            $obj.BSSID = $matches[1].Trim() 
            Write-Debug "Found BSSID: $($obj.BSSID)"
        }
        elseif($line -match '^\s*Radio type\s*:\s*(.+)$') { 
            $obj.RadioType = $matches[1].Trim() 
        }
        elseif($line -match '^\s*Channel\s*:\s*(.+)$') { 
            $obj.Channel = $matches[1].Trim() 
        }
        elseif($line -match '^\s*Band\s*:\s*(.+)$') { 
            $obj.Band = $matches[1].Trim() 
        }
        elseif($line -match '^\s*Signal\s*:\s*(\d+)%') { 
            $obj.SignalPct = [int]$matches[1]
            $obj.SignalDbm = -100 + ($obj.SignalPct * 0.5)
            Write-Debug "Found Signal: $($obj.SignalPct)% ($($obj.SignalDbm) dBm)"
        }
        elseif($line -match '^\s*Receive rate \(Mbps\)\s*:\s*(.+)$') { 
            $obj.RxRateMbps = [double]$matches[1] 
        }
        elseif($line -match '^\s*Transmit rate \(Mbps\)\s*:\s*(.+)$') { 
            $obj.TxRateMbps = [double]$matches[1] 
        }
    }

    # Create and return the object
    return [pscustomobject]$obj
}

function Invoke-Iperf3 {
  param(
    [Parameter(Mandatory)][string]$Server,
    [int]$Duration=30,
    [switch]$Reverse,
    [switch]$UDP,
    [int]$BitrateMbps=0,
    [string]$OutFile
  )
  $args = @("-c",$Server,"-t",$Duration,"-J")
  if($Reverse) { $args += "-R" }
  if($UDP) { $args += @("-u","-b","$($BitrateMbps)M") }
  $json = & iperf3.exe @args 2>$null
  if($LASTEXITCODE -ne 0 -or -not $json) { throw "iperf3 failed: $($args -join ' ')" }
  if($OutFile) { $json | Out-File -Encoding ascii $OutFile }
  return $json | ConvertFrom-Json
}

function Get-IperfIntervalP95 {
  param([Parameter(Mandatory)][object]$IperfJson)
  $intervals = @()
  foreach($i in $IperfJson.intervals) { if($i.sum.bits_per_second) { $intervals += [double]$i.sum.bits_per_second } }
  if(-not $intervals -or $intervals.Count -eq 0) { return $null }
  $s = $intervals | Sort-Object
  $idx = [math]::Floor(0.95 * ($s.Count - 1))
  return $s[$idx]
}

function Get-IperfSummary {
  param(
    [Parameter(Mandatory, ValueFromPipeline=$true)][object]$IperfJson
  )
  process {
    $end = $IperfJson.end
    $sum = $end.sum_received; if(-not $sum){ $sum = $end.sum_sent }; if(-not $sum){ $sum = $end.sum }
    $bps = [double]($sum.bits_per_second)
    $p95bps = Get-IperfIntervalP95 -IperfJson $IperfJson
    $udp = $end.sum
    [pscustomobject]@{
      Duration_s   = [double]$sum.seconds
      Avg_Mbps     = if($bps){ $bps/1e6 } else { $null }
      P95_Mbps     = if($p95bps){ $p95bps/1e6 } else { $null }
      UDP_Jitter_ms= if($udp.jitter_ms){ [double]$udp.jitter_ms } else { $null }
      UDP_Loss_pct = if($udp.lost_percent){ [double]$udp.lost_percent } else { $null }
      Sender_Mbps  = if($end.sum_sent.bits_per_second){ [double]$end.sum_sent.bits_per_second/1e6 } else { $null }
      Receiver_Mbps= if($end.sum_received.bits_per_second){ [double]$end.sum_received.bits_per_second/1e6 } else { $null }
      Reverse      = [bool]$IperfJson.start.test_start.reverse
      Protocol     = if($IperfJson.start.test_start.udp){ "UDP" } else { "TCP" }
    }
  }
}

function Invoke-PingSeries {
  param(
    [Parameter(Mandatory)][string]$Target,
    [int]$Count=150,
    [int]$IntervalMs=200,
    [string]$OutCsv
  )
  $rows = New-Object System.Collections.Generic.List[object]
  for($i=0; $i -lt $Count; $i++){
    $ts = Get-Date
    try {
      # Use older style Test-Connection for better compatibility
      $res = Test-Connection -ComputerName $Target -Count 1 -ErrorAction Stop
      if ($res.ResponseTime -ne $null) {
        $rtt = [double]$res.ResponseTime
        $ok = $true
      } elseif ($res.Latency -ne $null) {
        $rtt = [double]$res.Latency
        $ok = $true
      } else {
        Write-Warning "No valid ping response time found"
        $rtt = $null
        $ok = $false
      }
    } catch {
      Write-Warning "Ping error: $_"
      $rtt = $null
      $ok = $false
    }
    $rows.Add([pscustomobject]@{
      Timestamp = $ts.ToString("o"); Target = $Target; Success = $ok; RTT_ms = $rtt
    })
    if($IntervalMs -gt 0){ Start-Sleep -Milliseconds $IntervalMs }
  }
  if($OutCsv){ $rows | Export-Csv -NoTypeInformation -Encoding UTF8 $OutCsv }
  return $rows
}

function Get-JitterLossFromSamples {
  param([Parameter(Mandatory)][object[]]$Samples)
  $rtts = $Samples | Where-Object {$_.Success -and $_.RTT_ms -ne $null} | Select-Object -ExpandProperty RTT_ms
  $lossPct = 100.0 * (($Samples.Count - $rtts.Count) / [double]$Samples.Count)
  if($rtts.Count -le 1){ return [pscustomobject]@{ Avg_ms=$null; P95_ms=$null; Jitter_ms=$null; Loss_pct=$lossPct } }
  $avg = ($rtts | Measure-Object -Average).Average
  $sorted = $rtts | Sort-Object
  $p95 = $sorted[[math]::Floor(0.95 * ($sorted.Count-1))]
  $deltas = for($i=1;$i -lt $rtts.Count;$i++){ [math]::Abs($rtts[$i]-$rtts[$i-1]) }
  $jitter = ($deltas | Measure-Object -Average).Average
  [pscustomobject]@{ Avg_ms=$avg; P95_ms=$p95; Jitter_ms=$jitter; Loss_pct=$lossPct }
}

function New-WifiTestRunId {
  param([Parameter(Mandatory)][string]$TestId)
  $ts = Get-Date -Format "yyyyMMdd_HHmmss"
  return "${TestId}_${ts}"
}

function Invoke-WifiSuiteRun {
  [CmdletBinding()]
  param(
    [Parameter(Mandatory)][string]$Server,
    [Parameter(Mandatory)][string]$TestId,
    [int]$Duration=30,
    [int]$UdpMbps=100,
    [string]$Notes="",
    [int]$PingHz=5,
    [switch]$AutoReport
  )
  Ensure-Dir $Global:WifiOutDir
  $runId = New-WifiTestRunId -TestId $TestId
  $runDir = Join-Path $Global:WifiOutDir $runId
  Ensure-Dir $runDir

  $snap = Get-WlanSnapshot
  $gw = Get-DefaultGateway

  # iperf runs
  $tcp_dl = Invoke-Iperf3 -Server $Server -Duration $Duration -Reverse -OutFile (Join-Path $runDir "tcp_dl.json") | Get-IperfSummary
  $tcp_ul = Invoke-Iperf3 -Server $Server -Duration $Duration -OutFile (Join-Path $runDir "tcp_ul.json") | Get-IperfSummary
  $udp_dl = Invoke-Iperf3 -Server $Server -Duration $Duration -Reverse -UDP -BitrateMbps $UdpMbps -OutFile (Join-Path $runDir "udp_dl.json") | Get-IperfSummary
  $udp_ul = Invoke-Iperf3 -Server $Server -Duration $Duration -UDP -BitrateMbps $UdpMbps -OutFile (Join-Path $runDir "udp_ul.json") | Get-IperfSummary

  # pings (Count = Duration * PingHz)
  $count = [int]($Duration * $PingHz)
  $gwSamples  = Invoke-PingSeries -Target $gw -Count $count -IntervalMs (1000/$PingHz) -OutCsv (Join-Path $runDir "ping_gw.csv")
  $wanSamples = Invoke-PingSeries -Target "8.8.8.8" -Count $count -IntervalMs (1000/$PingHz) -OutCsv (Join-Path $runDir "ping_wan.csv")
  $gwStats  = Get-JitterLossFromSamples -Samples $gwSamples
  $wanStats = Get-JitterLossFromSamples -Samples $wanSamples

  # Build master row
  $row = [pscustomobject]@{
    run_id             = $runId
    date_time_local    = (Get-Date).ToString("s")
    interface          = $snap.InterfaceName
    ssid               = $snap.SSID
    bssid              = $snap.BSSID
    radio              = $snap.RadioType
    band               = $snap.Band
    channel            = $snap.Channel
    signal_pct         = $snap.SignalPct
    signal_dbm         = $snap.SignalDbm
    rx_rate_mbps       = $snap.RxRateMbps
    tx_rate_mbps       = $snap.TxRateMbps
    tcp_dl_avg_mbps    = $tcp_dl.Avg_Mbps
    tcp_dl_p95_mbps    = $tcp_dl.P95_Mbps
    tcp_ul_avg_mbps    = $tcp_ul.Avg_Mbps
    tcp_ul_p95_mbps    = $tcp_ul.P95_Mbps
    udp_dl_jitter_ms   = $udp_dl.UDP_Jitter_ms
    udp_dl_loss_pct    = $udp_dl.UDP_Loss_pct
    udp_ul_jitter_ms   = $udp_ul.UDP_Jitter_ms
    udp_ul_loss_pct    = $udp_ul.UDP_Loss_pct
    ping_gw_avg_ms     = $gwStats.Avg_ms
    ping_gw_p95_ms     = $gwStats.P95_ms
    ping_gw_jitter_ms  = $gwStats.Jitter_ms
    ping_gw_loss_pct   = $gwStats.Loss_pct
    ping_wan_avg_ms    = $wanStats.Avg_ms
    ping_wan_p95_ms    = $wanStats.P95_ms
    ping_wan_jitter_ms = $wanStats.Jitter_ms
    ping_wan_loss_pct  = $wanStats.Loss_pct
    notes              = $Notes
  }

  $exists = Test-Path $Global:WifiMasterCsv
  $row | Export-Csv -NoTypeInformation -Append:$exists -Encoding UTF8 $Global:WifiMasterCsv
  $row | Export-Csv -NoTypeInformation -Encoding UTF8 (Join-Path $runDir "summary.csv")

  Write-Host "Run complete: $runDir" -ForegroundColor Green

  if($AutoReport){ Publish-WifiRunReport -RunDir $runDir }
  return $row
}

function Start-WifiRoamWalk {
  [CmdletBinding()]
  param(
    [int]$DurationSec=120,
    [int]$Hz=5,
    [string]$TestId = "ROAM",
    [string]$WanTarget = "8.8.8.8",
    [switch]$AutoReport
  )
  Ensure-Dir $Global:WifiOutDir
  $runId = New-WifiTestRunId -TestId $TestId
  $runDir = Join-Path $Global:WifiOutDir $runId
  Ensure-Dir $runDir

  $gw = Get-DefaultGateway
  $intervalMs = [int](1000/$Hz)
  $stopAt = (Get-Date).AddSeconds($DurationSec)
  $rows = New-Object System.Collections.Generic.List[object]
  $prevBssid = $null

  while(Get-Date -lt $stopAt){
    $ts = Get-Date
    $snap = Get-WlanSnapshot
    # One ping each to GW and WAN for time series
    $gwRes = Invoke-PingSeries -Target $gw -Count 1 -IntervalMs 0
    $wanRes = Invoke-PingSeries -Target $WanTarget -Count 1 -IntervalMs 0
    $gwRtt = if($gwRes[0].Success){ $gwRes[0].RTT_ms } else { $null }
    $wanRtt = if($wanRes[0].Success){ $wanRes[0].RTT_ms } else { $null }
    $rows.Add([pscustomobject]@{
      Timestamp  = $ts.ToString("o")
      SSID       = $snap.SSID
      BSSID      = $snap.BSSID
      Channel    = $snap.Channel
      SignalPct  = $snap.SignalPct
      RxRateMbps = $snap.RxRateMbps
      TxRateMbps = $snap.TxRateMbps
      GW_RTT_ms  = $gwRtt
      WAN_RTT_ms = $wanRtt
      RoamEvent  = if($prevBssid -and $prevBssid -ne $snap.BSSID){ "BSSID_CHANGE" } else { "" }
    })
    $prevBssid = $snap.BSSID
    Start-Sleep -Milliseconds $intervalMs
  }

  $outCsv = Join-Path $runDir "roam_timeseries.csv"
  $rows | Export-Csv -NoTypeInformation -Encoding UTF8 $outCsv
  Write-Host "Roam timeseries written to $outCsv" -ForegroundColor Green

  if($AutoReport){ Publish-WifiRunReport -RunDir $runDir }
  return $rows
}

# ------------------------------
# Plotting utilities (PNG + HTML report)
# ------------------------------
function Import-ChartAssemblies {
  try {
    Add-Type -AssemblyName System.Windows.Forms | Out-Null
    Add-Type -AssemblyName System.Windows.Forms.DataVisualization | Out-Null
    return $true
  } catch {
    Write-Warning "Charting assemblies not available: $_"; return $false
  }
}

function New-Chart {
  param(
    [string]$Title,
    [int]$Width=1200,
    [int]$Height=600,
    [string]$XAxisTitle="",
    [string]$YAxisTitle=""
  )
  $chart = New-Object System.Windows.Forms.DataVisualization.Charting.Chart
  $chart.Width = $Width; $chart.Height = $Height
  
  # Add ChartArea
  $ca = New-Object System.Windows.Forms.DataVisualization.Charting.ChartArea "ca1"
  $ca.AxisX.MajorGrid.LineDashStyle = 'Dash'
  $ca.AxisY.MajorGrid.LineDashStyle = 'Dash'
  $ca.AxisX.Title = $XAxisTitle; $ca.AxisY.Title = $YAxisTitle
  $chart.ChartAreas.Add($ca)
  
  # Add Legend
  $legend = New-Object System.Windows.Forms.DataVisualization.Charting.Legend
  $legend.Docking = 'Top'
  $legend.Alignment = 'Center'
  $legend.IsDockedInsideChartArea = $false
  $chart.Legends.Add($legend)
  
  if($Title){ [void]$chart.Titles.Add($Title) }
  return $chart
}

function Add-LineSeries {
  param(
    [Parameter(Mandatory)][object]$Chart,
    [Parameter(Mandatory)][string]$Name,
    [Parameter(Mandatory)][object[]]$X,
    [Parameter(Mandatory)][object[]]$Y,
    [ValidateSet('Double','DateTime')][string]$XType='Double',
    [switch]$SecondaryAxis,
    [System.Drawing.Color]$Color = $null
  )
  $s = New-Object System.Windows.Forms.DataVisualization.Charting.Series $Name
  $s.ChartType = 'FastLine'
  $s.BorderWidth = 2
  $s.XValueType = $XType
  if ($Color) {
    $s.Color = $Color
  }
  if($SecondaryAxis){ $s.YAxisType = 'Secondary' }
  for($i=0;$i -lt $X.Count;$i++){
    $yval = $Y[$i]
    $pt = New-Object System.Windows.Forms.DataVisualization.Charting.DataPoint
    if($XType -eq 'DateTime'){
      $pt.SetValueXY([datetime]$X[$i], $yval)
    } else {
      $pt.SetValueXY([double]$X[$i], $yval)
    }
    if($null -eq $yval){ $pt.IsEmpty = $true }
    [void]$s.Points.Add($pt)
  }
  [void]$Chart.Series.Add($s)
}

function Save-Chart {
  param([Parameter(Mandatory)][object]$Chart,[Parameter(Mandatory)][string]$Path)
  $dir = Split-Path -Parent $Path; if(-not (Test-Path $dir)){ New-Item -ItemType Directory -Path $dir | Out-Null }
  $Chart.SaveImage($Path,'Png')
}

function Plot-IperfThroughput {
  param([Parameter(Mandatory)][string]$RunDir)
  $tcpdl = Join-Path $RunDir 'tcp_dl.json'
  $tcpul = Join-Path $RunDir 'tcp_ul.json'
  if(-not (Test-Path $tcpdl) -or -not (Test-Path $tcpul)) { return $null }
  $jdl = Get-Content $tcpdl | ConvertFrom-Json
  $jul = Get-Content $tcpul | ConvertFrom-Json
  $xdl = @(); $ydl = @(); foreach($iv in $jdl.intervals){ $xdl += [double]$iv.sum.end; $ydl += [double]$iv.sum.bits_per_second/1e6 }
  $xul = @(); $yul = @(); foreach($iv in $jul.intervals){ $xul += [double]$iv.sum.end; $yul += [double]$iv.sum.bits_per_second/1e6 }
  $chart = New-Chart -Title 'TCP Throughput' -XAxisTitle 'Seconds' -YAxisTitle 'Mbps'
  Add-LineSeries -Chart $chart -Name 'Download' -X $xdl -Y $ydl -Color ([System.Drawing.Color]::FromArgb(255, 0, 120, 212))
  Add-LineSeries -Chart $chart -Name 'Upload' -X $xul -Y $yul -Color ([System.Drawing.Color]::FromArgb(255, 0, 153, 0))
  $out = Join-Path $RunDir 'plot_throughput_tcp.png'
  Save-Chart -Chart $chart -Path $out
  return $out
}

function Plot-PingRtt {
  param([Parameter(Mandatory)][string]$RunDir)
  $gwCsv = Join-Path $RunDir 'ping_gw.csv'
  $wanCsv = Join-Path $RunDir 'ping_wan.csv'
  if(-not (Test-Path $gwCsv) -or -not (Test-Path $wanCsv)) { return $null }
  $gw = Import-Csv $gwCsv
  $wan = Import-Csv $wanCsv
  $xg = @($gw | Select-Object -ExpandProperty Timestamp)
  $yg = @($gw | ForEach-Object { if($_.Success -eq 'True' -and $_.RTT_ms){ [double]$_.RTT_ms } else { 0 } })
  $xw = @($wan | Select-Object -ExpandProperty Timestamp)
  $yw = @($wan | ForEach-Object { if($_.Success -eq 'True' -and $_.RTT_ms){ [double]$_.RTT_ms } else { 0 } })
  $chart = New-Chart -Title 'Ping RTT (Gateway & WAN)' -XAxisTitle 'Time' -YAxisTitle 'RTT (ms)'
  $chart.ChartAreas[0].AxisX.LabelStyle.Format = 'HH:mm:ss'
  Add-LineSeries -Chart $chart -Name 'Gateway' -X $xg -Y $yg -XType DateTime -Color ([System.Drawing.Color]::FromArgb(255, 0, 120, 212))
  Add-LineSeries -Chart $chart -Name 'WAN (8.8.8.8)' -X $xw -Y $yw -XType DateTime -Color ([System.Drawing.Color]::FromArgb(255, 153, 0, 0))
  $out = Join-Path $RunDir 'plot_ping_rtt.png'
  Save-Chart -Chart $chart -Path $out
  return $out
}

function Plot-RoamTimeseries {
  param([Parameter(Mandatory)][string]$RunDir)
  $csv = Join-Path $RunDir 'roam_timeseries.csv'
  if(-not (Test-Path $csv)) { return $null }
  $rows = Import-Csv $csv
  $t = $rows | Select-Object -ExpandProperty Timestamp
  $gw = $rows | Select-Object -ExpandProperty GW_RTT_ms | ForEach-Object { if($_){ [double]$_ } else { $null } }
  $wan= $rows | Select-Object -ExpandProperty WAN_RTT_ms | ForEach-Object { if($_){ [double]$_ } else { $null } }
  $sig= $rows | Select-Object -ExpandProperty SignalPct | ForEach-Object { if($_){ [double]$_ } else { $null } }

  $chart = New-Chart -Title 'Roam Walk â€” RTT & Signal' -XAxisTitle 'Time' -YAxisTitle 'RTT (ms)'
  $chart.ChartAreas[0].AxisX.LabelStyle.Format = 'HH:mm:ss'
  $chart.ChartAreas[0].AxisY2.Enabled = 'True'
  $chart.ChartAreas[0].AxisY2.Title = 'Signal (%)'

  Add-LineSeries -Chart $chart -Name 'Gateway RTT' -X $t -Y $gw -XType DateTime -Color ([System.Drawing.Color]::FromArgb(255, 0, 120, 212))
  Add-LineSeries -Chart $chart -Name 'WAN RTT' -X $t -Y $wan -XType DateTime -Color ([System.Drawing.Color]::FromArgb(255, 153, 0, 0))
  Add-LineSeries -Chart $chart -Name 'Signal Strength' -X $t -Y $sig -XType DateTime -SecondaryAxis -Color ([System.Drawing.Color]::FromArgb(255, 0, 153, 0))

  # Mark BSSID changes as event markers at top
  $maxRtt = @($gw + $wan | Where-Object {$_ -ne $null}) | Measure-Object -Maximum
  $yMark = if($maxRtt.Maximum){ [double]$maxRtt.Maximum + 10 } else { 10 }
  $ev = $rows | Where-Object { $_.RoamEvent -eq 'BSSID_CHANGE' }
  if($ev.Count -gt 0){
    $s = New-Object System.Windows.Forms.DataVisualization.Charting.Series 'Roam Events'
    $s.ChartType = 'Point'; $s.MarkerStyle='Cross'; $s.MarkerSize=10
    $s.Color = [System.Drawing.Color]::Red
    $s.XValueType='DateTime'
    foreach($e in $ev){
      $pt = New-Object System.Windows.Forms.DataVisualization.Charting.DataPoint
      $pt.SetValueXY([datetime]$e.Timestamp, $yMark)
      [void]$s.Points.Add($pt)
    }
    [void]$chart.Series.Add($s)
  }

  $out = Join-Path $RunDir 'plot_roam_timeseries.png'
  Save-Chart -Chart $chart -Path $out
  return $out
}

function Publish-WifiRunReport {
  [CmdletBinding()]
  param([Parameter(Mandatory)][string]$RunDir)
  if(-not (Import-ChartAssemblies)) { Write-Warning "Skipping plots (charting unavailable)."; return $null }

  $plots = @{}
  $p1 = Plot-IperfThroughput -RunDir $RunDir; if($p1){ $plots['TCP Throughput'] = Split-Path -Leaf $p1 }
  $p2 = Plot-PingRtt        -RunDir $RunDir; if($p2){ $plots['Ping RTT']       = Split-Path -Leaf $p2 }
  $p3 = Plot-RoamTimeseries -RunDir $RunDir; if($p3){ $plots['Roam Timeseries'] = Split-Path -Leaf $p3 }

  $sumPath = Join-Path $RunDir 'summary.csv'
  $sumHtml = ''
  if(Test-Path $sumPath){
    $row = (Import-Csv $sumPath)[0]
    $sumHtml = @"
<table border=1 cellpadding=6 cellspacing=0>
<tr><th>Run ID</th><td>$($row.run_id)</td></tr>
<tr><th>Date</th><td>$($row.date_time_local)</td></tr>
<tr><th>SSID</th><td>$($row.ssid)</td></tr>
<tr><th>BSSID</th><td>$($row.bssid)</td></tr>
<tr><th>Radio/Band/Channel</th><td>$($row.radio) / $($row.band) / $($row.channel)</td></tr>
<tr><th>Signal Strength</th><td>$($row.signal_pct)% (~$([math]::Round($row.signal_dbm, 1)) dBm)</td></tr>
<tr><th>AP BSSID</th><td>$($row.bssid)</td></tr>
<tr><th>TCP DL avg/p95 (Mb/s)</th><td>$([math]::Round([double]$row.tcp_dl_avg_mbps,1)) / $([math]::Round([double]$row.tcp_dl_p95_mbps,1))</td></tr>
<tr><th>TCP UL avg/p95 (Mb/s)</th><td>$([math]::Round([double]$row.tcp_ul_avg_mbps,1)) / $([math]::Round([double]$row.tcp_ul_p95_mbps,1))</td></tr>
<tr><th>UDP DL jitter/loss</th><td>$($row.udp_dl_jitter_ms) ms / $($row.udp_dl_loss_pct) %</td></tr>
<tr><th>UDP UL jitter/loss</th><td>$($row.udp_ul_jitter_ms) ms / $($row.udp_ul_loss_pct) %</td></tr>
<tr><th>GW RTT avg/p95/jitter</th><td>$([math]::Round([double]$row.ping_gw_avg_ms,1)) / $([math]::Round([double]$row.ping_gw_p95_ms,1)) / $([math]::Round([double]$row.ping_gw_jitter_ms,1))</td></tr>
<tr><th>WAN RTT avg/p95/jitter</th><td>$([math]::Round([double]$row.ping_wan_avg_ms,1)) / $([math]::Round([double]$row.ping_wan_p95_ms,1)) / $([math]::Round([double]$row.ping_wan_jitter_ms,1))</td></tr>
<tr><th>Notes</th><td>$($row.notes)</td></tr>
</table>
"@
  }

  $html = @"
<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>WiFi Run Report</title></head>
<body style="font-family:Segoe UI,Arial,sans-serif; margin:24px;">
<h1>WiFi Run Report</h1>
$sumHtml
<h2>Plots</h2>
<ul>
$(($plots.GetEnumerator() | ForEach-Object { "<li><b>$($_.Key)</b><br><img src='$(($_.Value))' style='max-width:100%;height:auto;border:1px solid #ddd;'/></li>" }) -join "`n")
</ul>
<p style="color:#666">Generated $(Get-Date -Format s)</p>
</body></html>
"@
  $reportPath = Join-Path $RunDir 'report.html'
  $html | Out-File -Encoding UTF8 $reportPath
  Write-Host "Report written: $reportPath" -ForegroundColor Green
  return $reportPath
}

# ------------------------------
# Example Recipes (copy/paste)
# ------------------------------
<#
# 1) Orientation sweep (rotate NIC manually between runs) with auto-reports
Invoke-WifiSuiteRun -Server 192.168.0.205 -TestId "NIC_A_pos0"  -Duration 30 -UdpMbps 100 -AutoReport
Invoke-WifiSuiteRun -Server 192.168.0.205 -TestId "NIC_A_pos45" -Duration 30 -UdpMbps 100 -AutoReport
Invoke-WifiSuiteRun -Server 192.168.0.205 -TestId "NIC_A_pos90" -Duration 30 -UdpMbps 100 -AutoReport

# 2) NIC comparison (switch adapters between runs) with auto-reports
Invoke-WifiSuiteRun -Server 192.168.0.205 -TestId "NIC_A_midroom" -AutoReport
Invoke-WifiSuiteRun -Server 192.168.0.205 -TestId "NIC_B_midroom" -AutoReport

# 3) Mesh roaming walk (while on a live call), then make a report
Start-WifiRoamWalk -DurationSec 180 -Hz 5 -TestId "ROAM_evening_walk" -AutoReport
# or later:
#   Publish-WifiRunReport -RunDir .\wifi_tests\ROAM_evening_walk_20250101_120000

# Master results accumulate in: $Global:WifiMasterCsv
# Per-run artifacts live under:  .\wifi_tests\<run_id>\
#>
