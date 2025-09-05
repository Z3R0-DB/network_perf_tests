import subprocess
import json
import time
from datetime import datetime
from .iperf import Iperf
from .ping import Ping
from .wlan import Wlan
from .platform.macos import get_default_gateway

class NetworkTestRunner:
    def __init__(self, server, test_id, duration=30, udp_target_mbps=100):
        self.server = server
        self.test_id = test_id
        self.duration = duration
        self.udp_target_mbps = udp_target_mbps
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.wlan = Wlan()
        self.ping = Ping()
        self.iperf = Iperf()

    def run_tests(self):
        self.snapshot_wlan_state()
        self.run_iperf_tests()
        self.run_ping_tests()
        print(f"Done. Artifacts written with timestamp {self.timestamp}.")

    def snapshot_wlan_state(self):
        wlan_file = f"wlan_{self.test_id}_{self.timestamp}.txt"
        with open(wlan_file, 'w') as f:
            f.write(self.wlan.get_interface_info())
            f.write("\n----- Get-NetAdapter (active) -----\n")
            f.write(self.wlan.get_active_adapters())
            f.write("\n----- Get-NetAdapterAdvancedProperty (wifi) -----\n")
            f.write(self.wlan.get_advanced_properties())

    def run_iperf_tests(self):
        # TCP Download (reverse)
        tcp_dl_result = self.iperf.run_test(self.server, reverse=True, duration=self.duration)
        self.save_result(tcp_dl_result, "tcp_dl")

        # TCP Upload
        tcp_ul_result = self.iperf.run_test(self.server, duration=self.duration)
        self.save_result(tcp_ul_result, "tcp_ul")

        # UDP Download (reverse)
        udp_dl_result = self.iperf.run_test(self.server, udp=True, bandwidth=self.udp_target_mbps, reverse=True, duration=self.duration)
        self.save_result(udp_dl_result, "udp_dl")

        # UDP Upload
        udp_ul_result = self.iperf.run_test(self.server, udp=True, bandwidth=self.udp_target_mbps, duration=self.duration)
        self.save_result(udp_ul_result, "udp_ul")

    def run_ping_tests(self):
        ping_count = int(self.duration * 5)
        gw = get_default_gateway()
        if not gw:
            raise Exception("Default gateway not found. Are you connected?")
        
        # Gateway ping
        gw_ping_result = self.ping.run_ping(gw, count=ping_count)
        self.save_ping_result(gw_ping_result, "gw")

        # WAN target (Google DNS)
        wan_ping_result = self.ping.run_ping("8.8.8.8", count=ping_count)
        self.save_ping_result(wan_ping_result, "wan")

    def save_result(self, result, test_type):
        with open(f"iperf_{self.test_id}_{self.timestamp}_{test_type}.json", 'w') as f:
            json.dump(result, f)

    def save_ping_result(self, result, target):
        with open(f"ping_{self.test_id}_{self.timestamp}_{target}.txt", 'w') as f:
            f.write(result)

def main():
    # Example usage
    runner = NetworkTestRunner(server="192.0.2.10", test_id="NIC_A_Pos0", duration=30, udp_target_mbps=100)
    runner.run_tests()

if __name__ == "__main__":
    main()