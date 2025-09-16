import subprocess
import json
import time
from datetime import datetime

class Iperf:
    def __init__(self, server, test_id, duration=30, udp_target_mbps=100):
        self.server = server
        self.test_id = test_id
        self.duration = duration
        self.udp_target_mbps = udp_target_mbps
        self.ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    def run_tcp_download(self):
        command = ["iperf3", "-c", self.server, "-R", "-t", str(self.duration), "-J"]
        return self._run_command(command, "tcp_dl")

    def run_tcp_upload(self):
        command = ["iperf3", "-c", self.server, "-t", str(self.duration), "-J"]
        return self._run_command(command, "tcp_ul")

    def run_udp_download(self):
        command = ["iperf3", "-c", self.server, "-u", "-b", f"{self.udp_target_mbps}M", "-R", "-t", str(self.duration), "-J"]
        return self._run_command(command, "udp_dl")

    def run_udp_upload(self):
        command = ["iperf3", "-c", self.server, "-u", "-b", f"{self.udp_target_mbps}M", "-t", str(self.duration), "-J"]
        return self._run_command(command, "udp_ul")

    def _run_command(self, command, test_type):
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            output_file = f"iperf_{self.test_id}_{self.ts}_{test_type}.json"
            with open(output_file, 'w') as f:
                json.dump(json.loads(result.stdout), f)
            return output_file
        except subprocess.CalledProcessError as e:
            print(f"Error running command {command}: {e.stderr}")
            return None

    def ping(self, target, count=5):
        command = ["ping", "-c", str(count), target]
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            output_file = f"ping_{self.test_id}_{self.ts}_{target}.txt"
            with open(output_file, 'w') as f:
                f.write(result.stdout)
            return output_file
        except subprocess.CalledProcessError as e:
            print(f"Error running ping command: {e.stderr}")
            return None

    def snapshot_wlan(self):
        wlan_file = f"wlan_{self.test_id}_{self.ts}.txt"
        try:
            with open(wlan_file, 'w') as f:
                subprocess.run(["netsh", "wlan", "show", "interfaces"], stdout=f, text=True)
            return wlan_file
        except Exception as e:
            print(f"Error capturing WLAN snapshot: {e}")
            return None