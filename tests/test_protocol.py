"""Compare shell output with argcomplete, without importing application code."""

import argparse
import os
import pickle
import subprocess
import sys

import pytest

from fastcomplete.cache import snapshot


CHOICES = sorted(["blue", "café", "green", "green tea", "żółty"])


def fixture(tmp_path):
    parser = argparse.ArgumentParser()
    parser.add_argument("--color", choices=CHOICES)
    (tmp_path / "_fastcomplete.cache").write_bytes(pickle.dumps(snapshot(parser)))
    cached = tmp_path / "cached.py"
    cached.write_text("import fastcomplete\nfastcomplete.bootstrap()\nraise AssertionError('application imported')\n")
    baseline = tmp_path / "baseline.py"
    baseline.write_text(
        "import argparse, argcomplete\np = argparse.ArgumentParser()\n"
        f"p.add_argument('--color', choices={CHOICES!r})\nargcomplete.autocomplete(p)\n",
        encoding="utf-8",
    )
    return cached, baseline


def environment(line, shell="bash", offset="1", point=None):
    clean = {key: value for key, value in os.environ.items()
             if not key.startswith(("_ARGCOMPLETE", "FASTCOMPLETE_"))}
    return clean | {"_ARGCOMPLETE": offset, "COMP_LINE": line,
                    "COMP_POINT": str(len(line) if point is None else point),
                    "_ARGCOMPLETE_SHELL": shell, "PYTHONUTF8": "1"}


@pytest.mark.parametrize("shell", ["bash", "zsh", "powershell"])
@pytest.mark.parametrize("line,offset,point", [
    ("fixture --color ", "1", None),
    ("fixture --color gr", "1", None),
    ('fixture --color "green t', "1", None),
    ("fixture --color ż", "1", None),
    ("fixture --color green", "1", len("fixture --color gr")),
    ("python fixture.py --color ca", "2", None),
    ("python -m fixture --color gr", "3", None),
])
def test_shell_output_matches_argcomplete(tmp_path, shell, line, offset, point):
    outputs = []
    for index, entry in enumerate(fixture(tmp_path)):
        destination = tmp_path / f"output-{index}"
        env = environment(line, shell, offset, point)
        env["_ARGCOMPLETE_STDOUT_FILENAME"] = str(destination)
        result = subprocess.run([sys.executable, str(entry)], env=env, capture_output=True)
        assert result.returncode == 0, result.stderr
        assert result.stdout == b""
        outputs.append(destination.read_bytes())
    assert outputs[0] == outputs[1]


@pytest.mark.skipif(os.name == "nt", reason="POSIX descriptor transport")
@pytest.mark.parametrize("separator,suppress", [("\v", "0"), ("|", "1")])
def test_descriptor_transport_matches_argcomplete(tmp_path, separator, suppress):
    outputs = []
    for index, entry in enumerate(fixture(tmp_path)):
        destination = tmp_path / f"output-{index}"
        env = environment("fixture --color bl")
        env.update(_ARGCOMPLETE_IFS=separator, _ARGCOMPLETE_SUPPRESS_SPACE=suppress)
        result = subprocess.run(
            ["bash", "-c", 'exec 8>"$1"; "$2" "$3"',
             "test", str(destination), sys.executable, str(entry)],
            env=env, capture_output=True,
        )
        assert result.returncode == 0, result.stderr
        outputs.append(destination.read_bytes())
    assert outputs[0] == outputs[1]


@pytest.mark.parametrize("missing_cache", [False, True])
def test_completion_failure_is_quiet(tmp_path, missing_cache):
    cached, _ = fixture(tmp_path)
    if missing_cache:
        (tmp_path / "_fastcomplete.cache").unlink()
    destination = tmp_path / "output"
    env = environment("fixture --unknown value ")
    env["_ARGCOMPLETE_STDOUT_FILENAME"] = str(destination)
    result = subprocess.run([sys.executable, str(cached)], env=env, capture_output=True)
    assert result.returncode == 1
    assert result.stdout == result.stderr == b""
    assert not destination.exists() or destination.read_bytes() == b""
