import subprocess
import json
from datetime import datetime

class PingTest:
    def __init__(self, target, count=30):
        self.target = target
        self.count = count
        self.results = []

    def run(self):
        command = ["ping", "-c", str(self.count), self.target]
        try:
            output = subprocess.check_output(command, stderr=subprocess.STDOUT, universal_newlines=True)
            self.parse_output(output)
        except subprocess.CalledProcessError as e:
            print(f"Error running ping: {e.output}")

    def parse_output(self, output):
        lines = output.splitlines()
        for line in lines:
            if "time=" in line:
                self.results.append(line)

    def save_results(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"ping_results_{self.target}_{timestamp}.json"
        with open(filename, 'w') as f:
            json.dump(self.results, f)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run ICMP ping tests.")
    parser.add_argument("target", help="Target IP address or hostname to ping")
    parser.add_argument("--count", type=int, default=30, help="Number of ping requests to send")
    args = parser.parse_args()

    ping_test = PingTest(args.target, args.count)
    ping_test.run()
    ping_test.save_results()