#!/usr/bin/env python3
"""
Test runner script for the Volunteer Managing application.
"""

import sys
import subprocess
from pathlib import Path

def run_tests():
    """Run the test suite."""
    project_root = Path(__file__).parent

    # Change to project root
    import os
    os.chdir(project_root)

    # Activate virtual environment if it exists
    venv_path = project_root / "backend" / ".venv" / "bin" / "activate"
    if venv_path.exists():
        activate_cmd = f"source {venv_path}"
        test_cmd = f"{activate_cmd} && python -m pytest"
    else:
        test_cmd = "python -m pytest"

    # Run tests
    try:
        result = subprocess.run(test_cmd, shell=True, check=True)
        return result.returncode
    except subprocess.CalledProcessError as e:
        print(f"Tests failed with return code {e.returncode}")
        return e.returncode

if __name__ == "__main__":
    sys.exit(run_tests())