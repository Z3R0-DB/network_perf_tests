import unittest
from src.platform.macos import MacOSPlatform
from src.platform.windows import WindowsPlatform

class TestMacOSPlatform(unittest.TestCase):
    def setUp(self):
        self.platform = MacOSPlatform()

    def test_get_interface_stats(self):
        stats = self.platform.get_interface_stats()
        self.assertIsInstance(stats, dict)
        self.assertIn('interface', stats)
        self.assertIn('signal_strength', stats)

    def test_run_ping(self):
        result = self.platform.run_ping('8.8.8.8', count=4)
        self.assertIsInstance(result, dict)
        self.assertIn('avg_time', result)

class TestWindowsPlatform(unittest.TestCase):
    def setUp(self):
        self.platform = WindowsPlatform()

    def test_get_interface_stats(self):
        stats = self.platform.get_interface_stats()
        self.assertIsInstance(stats, dict)
        self.assertIn('interface', stats)
        self.assertIn('signal_strength', stats)

    def test_run_ping(self):
        result = self.platform.run_ping('8.8.8.8', count=4)
        self.assertIsInstance(result, dict)
        self.assertIn('avg_time', result)

if __name__ == '__main__':
    unittest.main()