import subprocess
import sys


def test_cli_inspect_reports_missing_manifest(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weread_export.cli",
            "--output",
            str(tmp_path),
            "inspect",
            "missing-book",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "No manifest found" in result.stderr

