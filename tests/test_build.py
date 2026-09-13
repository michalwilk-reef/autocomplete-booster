import os
from pathlib import Path
import pickle

import pytest
from setuptools import Distribution
from setuptools.errors import SetupError

from fastcomplete.setuptools import BuildPy


def project(tmp_path, monkeypatch, source):
    monkeypatch.chdir(tmp_path)
    package = tmp_path / "src" / "fixture"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "cli.py").write_text(source)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.fastcomplete]\nentrypoint = "fixture.cli:main"\n'
    )
    distribution = Distribution({
        "name": "capture-fixture", "packages": ["fixture"],
        "package_dir": {"": "src"}, "package_data": {"fixture": ["*.cache"]},
    })
    distribution.script_name = "setup.py"
    command = BuildPy(distribution)
    command.ensure_finalized()
    command.build_lib = str(tmp_path / "build" / "lib")
    return command, package


SOURCE = '''import fastcomplete
fastcomplete.bootstrap()
from .sdk_commands import build_parser

def main():
    parser = build_parser()
    fastcomplete.autocomplete(parser)
    raise RuntimeError("handler must never execute during capture")
'''


def test_capture_builds_sdk_dependent_parser_and_stops_before_dispatch(tmp_path, monkeypatch):
    command, package = project(tmp_path, monkeypatch, SOURCE)
    (package / "sdk_commands.py").write_text(
        'import argparse\nimport requests\n'
        'def build_parser():\n'
        '    parser = argparse.ArgumentParser()\n'
        '    parser.add_argument("--region", choices=["west", "east"])\n'
        '    return parser\n'
    )
    monkeypatch.setenv("_ARGCOMPLETE", "1")
    monkeypatch.setenv("COMP_LINE", "fixture --r")
    cache = Path(command.build_lib) / "fixture" / "_fastcomplete.cache"
    assert str(cache) in command.get_outputs()
    command.run()
    payload = pickle.loads(cache.read_bytes())
    assert payload["schema"] == 1
    assert b"--region" in cache.read_bytes()
    assert str(cache) in command.get_outputs()
    assert not (package / "_fastcomplete.cache").exists()


def test_capture_failure_removes_old_cache(tmp_path, monkeypatch):
    command, _ = project(tmp_path, monkeypatch, 'raise RuntimeError("missing build credentials")\n')
    cache = Path(command.build_lib) / "fixture" / "_fastcomplete.cache"
    cache.parent.mkdir(parents=True)
    cache.write_bytes(b"stale cache")
    with pytest.raises(SetupError, match="missing build credentials"):
        command.run()
    assert not cache.exists()


def test_capture_requires_autocomplete(tmp_path, monkeypatch):
    command, _ = project(tmp_path, monkeypatch, 'def main():\n    pass\n')
    with pytest.raises(SetupError, match="without calling fastcomplete.autocomplete"):
        command.run()


def test_editable_build_is_explicitly_unsupported(tmp_path, monkeypatch):
    command, _ = project(tmp_path, monkeypatch, SOURCE)
    command.editable_mode = True
    with pytest.raises(SetupError, match="editable"):
        command.run()


def test_source_cache_is_not_package_data(tmp_path, monkeypatch):
    command, package = project(tmp_path, monkeypatch, SOURCE)
    (package / "_fastcomplete.cache").write_bytes(b"stale source cache")
    command.manifest_files = {}
    assert command.find_data_files("fixture", str(package)) == []


def test_timeout_removes_partial_cache(tmp_path, monkeypatch):
    command, _ = project(tmp_path, monkeypatch,
        'import os, time\nfrom pathlib import Path\n'
        'def main():\n'
        '    Path(os.environ["FASTCOMPLETE_CAPTURE"]).write_bytes(b"partial")\n'
        '    time.sleep(10)\n'
    )
    with open("pyproject.toml", "a") as stream:
        stream.write("timeout = 0.2\n")
    with pytest.raises(SetupError, match="exceeded"):
        command.run()
    assert not (Path(command.build_lib) / "fixture" / "_fastcomplete.cache").exists()


def test_same_timestamp_same_size_source_change_rebuilds_cache(tmp_path, monkeypatch):
    source = (
        'import argparse, fastcomplete\n'
        'def main():\n'
        '    parser = argparse.ArgumentParser()\n'
        '    parser.add_argument("--mode", choices=["aaaa"])\n'
        '    fastcomplete.autocomplete(parser)\n'
    )
    command, package = project(tmp_path, monkeypatch, source)
    command.run()
    module = package / "cli.py"
    timestamp = module.stat().st_mtime_ns
    module.write_text(source.replace("aaaa", "bbbb"))
    os.utime(module, ns=(timestamp, timestamp))
    command.run()
    cache = Path(command.build_lib) / "fixture" / "_fastcomplete.cache"
    assert b"bbbb" in cache.read_bytes()
    assert b"aaaa" not in cache.read_bytes()
