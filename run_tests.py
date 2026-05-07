"""
Runner for tests — uses unittest directly to avoid ROS pytest plugin conflicts.
Usage:
    python run_tests.py              # all tests
    python run_tests.py -v           # verbose
    python run_tests.py TestChunk    # specific class
"""

import os, sys, unittest

os.environ.setdefault("DEEPSEEK_API_KEY", "test-skip")
os.environ.setdefault("DINGTALK_APP_KEY", "test-skip")
os.environ.setdefault("DINGTALK_APP_SECRET", "test-skip")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    patterns = sys.argv[1:] if len(sys.argv) > 1 else None
    if patterns:
        for p in patterns:
            tests = loader.loadTestsFromName(f"tests.{p}" if not p.startswith("tests.") else p)
            suite.addTests(tests)
    else:
        suite = loader.discover("tests", pattern="test_*.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
