import subprocess
import json
import time
from datetime import datetime

class MacOSPlatform:
    def __init__(self, test_id, duration, udp_target_mbps):
        self.test_id = test_id
        self.duration = duration
        self.udp_target_mbps = udp_target_mbps
        self.ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    def resolve_iperf_path(self):
        try:
            result = subprocess.run(['which', 'iperf3'], capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            raise FileNotFoundError("iperf3 not found. Please install iperf3 and ensure it's in your PATH.")

    def snapshot_wlan_state(self):
        wlan_file = f"wlan_{self.test_id}_{self.ts}.txt"
        with open(wlan_file, 'w') as f:
            subprocess.run(['netstat', '-nr'], stdout=f)
            f.write("----- ifconfig -----\n")
            subprocess.run(['ifconfig'], stdout=f)
        return wlan_file

    def run_ping(self, target):
        ping_file = f"ping_{self.test_id}_{self.ts}.txt"
        with open(ping_file, 'w') as f:
            subprocess.run(['ping', '-c', str(int(self.duration * 5)), target], stdout=f)
        return ping_file

    def run_iperf_tests(self, server):
        iperf_path = self.resolve_iperf_path()
        results = {}

        # TCP Download
        result = subprocess.run([iperf_path, '-c', server, '-R', '-t', str(self.duration), '-J'], capture_output=True, text=True)
        results['tcp_dl'] = json.loads(result.stdout)

        # TCP Upload
        result = subprocess.run([iperf_path, '-c', server, '-t', str(self.duration), '-J'], capture_output=True, text=True)
        results['tcp_ul'] = json.loads(result.stdout)

        # UDP Download
        result = subprocess.run([iperf_path, '-c', server, '-u', '-b', f"{self.udp_target_mbps}M", '-R', '-t', str(self.duration), '-J'], capture_output=True, text=True)
        results['udp_dl'] = json.loads(result.stdout)

        # UDP Upload
        result = subprocess.run([iperf_path, '-c', server, '-u', '-b', f"{self.udp_target_mbps}M", '-t', str(self.duration), '-J'], capture_output=True, text=True)
        results['udp_ul'] = json.loads(result.stdout)

        return results

    def run_tests(self, server):
        print(f"Running tests against server {server} for {self.duration}s, UDP={self.udp_target_mbps} Mbps")
        wlan_file = self.snapshot_wlan_state()
        print(f"WLAN state snapshot saved to {wlan_file}")

        results = self.run_iperf_tests(server)
        print("Iperf test results:", results)

        ping_gw = self.run_ping("8.8.8.8")  # Example target
        print(f"Ping results saved to {ping_gw}")

        print("Done. Artifacts written with timestamp", self.ts)