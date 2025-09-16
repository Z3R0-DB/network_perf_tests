import argparse
import sys
from src.runner import run_tests

def main():
    parser = argparse.ArgumentParser(description="Network Performance Testing Tool")
    
    parser.add_argument('-s', '--server', required=True, help='IP address of the server to test against')
    parser.add_argument('-t', '--test_id', required=True, help='Identifier for the test run')
    parser.add_argument('-d', '--duration', type=int, default=30, help='Duration of the test in seconds (default: 30)')
    parser.add_argument('-u', '--udp_target_mbps', type=int, default=100, help='Target UDP bandwidth in Mbps (default: 100)')
    
    args = parser.parse_args()

    try:
        run_tests(args.server, args.test_id, args.duration, args.udp_target_mbps)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()