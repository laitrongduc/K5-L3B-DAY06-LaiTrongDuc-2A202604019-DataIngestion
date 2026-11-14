"""Regression check for standalone-script versus module import consistency."""
import subprocess
import sys
import unittest
from pathlib import Path


class CliTests(unittest.TestCase):
    def test_pipeline_module_imports_and_shows_help(self):
        starter = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, "-m", "src.run", "--help"], cwd=starter,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ingest", result.stdout)
        self.assertIn("search", result.stdout)


if __name__ == "__main__":
    unittest.main()
