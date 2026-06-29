import shutil
import subprocess

import pytest

pytestmark = pytest.mark.smoke


def test_pi_binary_available():
    pi_path = shutil.which("pi")
    assert pi_path is not None, "pi binary not found"
    result = subprocess.run([pi_path, "--help"], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0
