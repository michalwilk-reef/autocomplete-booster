"""Guard the startup seam independently of the static evaluator."""

import os
import subprocess
import sys


def test_ordinary_import_and_calls_load_only_fastcomplete():
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("_ARGCOMPLETE", "FASTCOMPLETE_"))
    }
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; before = set(sys.modules); "
            "import fastcomplete; fastcomplete.bootstrap(); "
            "fastcomplete.autocomplete(object()); "
            "assert set(sys.modules) - before == {'fastcomplete'}, "
            "sorted(set(sys.modules) - before)",
        ],
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
