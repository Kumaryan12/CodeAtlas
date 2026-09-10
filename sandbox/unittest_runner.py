"""Trusted entrypoint, executed only inside the restricted test container."""
import pathlib
import sys
import unittest

sys.path.insert(0, "/workspace")
start = "/workspace/tests" if pathlib.Path("/workspace/tests").is_dir() else "/workspace"
suite = unittest.defaultTestLoader.discover(start, pattern="test*.py")
if suite.countTestCases() == 0:
    print("No unittest tests discovered.", file=sys.stderr)
    sys.exit(5)
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
