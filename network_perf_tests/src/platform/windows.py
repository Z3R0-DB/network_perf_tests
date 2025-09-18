# This file contains platform-specific implementations for Windows, which may be used for reference or future compatibility.

def get_iperf_path():
    import os
    # Check if iperf3 is in the current directory or in PATH
    candidates = [
        os.path.join(os.path.dirname(__file__), "iperf3.exe"),
        "iperf3.exe"
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    raise FileNotFoundError("iperf3.exe not found. Ensure it is in the same directory or in PATH.")

def run_ping(target, count):
    import subprocess
    command = ["ping", "-n", str(count), target]
    result = subprocess.run(command, capture_output=True, text=True)
    return result.stdout

def capture_wlan_info():
    import subprocess
    command = ["netsh", "wlan", "show", "interfaces"]
    result = subprocess.run(command, capture_output=True, text=True)
    return result.stdout

def get_default_gateway():
    import subprocess
    command = ["ipconfig"]
    result = subprocess.run(command, capture_output=True, text=True)
    for line in result.stdout.splitlines():
        if "Default Gateway" in line:
            return line.split(":")[-1].strip()
    raise RuntimeError("Default gateway not found. Are you connected?")