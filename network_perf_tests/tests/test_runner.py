import unittest
from src.runner import run_tests  # Assuming run_tests is the function to execute tests

class TestRunner(unittest.TestCase):

    def test_run_tests(self):
        # Example test case for the run_tests function
        result = run_tests(server="192.0.2.10", test_id="NIC_A_Pos0", duration=30, udp_target_mbps=100)
        self.assertIsNotNone(result)
        self.assertIn("iperf", result)
        self.assertIn("ping", result)

    def test_invalid_server(self):
        with self.assertRaises(ValueError):
            run_tests(server="", test_id="NIC_A_Pos0", duration=30, udp_target_mbps=100)

    def test_invalid_duration(self):
        with self.assertRaises(ValueError):
            run_tests(server="192.0.2.10", test_id="NIC_A_Pos0", duration=-1, udp_target_mbps=100)

    def test_invalid_udp_target_mbps(self):
        with self.assertRaises(ValueError):
            run_tests(server="192.0.2.10", test_id="NIC_A_Pos0", duration=30, udp_target_mbps=-10)

if __name__ == '__main__':
    unittest.main()