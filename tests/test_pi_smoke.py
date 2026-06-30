import shutil
import subprocess

import pytest

pytestmark = pytest.mark.smoke


def test_omp_binary_available():
    omp_path = shutil.which("omp")
    assert omp_path is not None, "omp binary not found"
    result = subprocess.run([omp_path, "--help"], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0
