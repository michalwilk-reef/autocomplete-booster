#!/usr/bin/env python3
"""Build/install a coupled-parser fixture and measure actual Bash completion."""

import argparse
import base64
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import textwrap
import zipfile


CLI = '''\
import fastcomplete
fastcomplete.bootstrap()
from .parser import build_parser

def main():
    parser = build_parser()
    fastcomplete.autocomplete(parser)
    args = parser.parse_args()
    return args.handler(args)
'''

PARSER = '''\
import argparse
from .commands import configure

def build_parser():
    parser = argparse.ArgumentParser(prog="reef-proof")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("list", VERSION_COMMAND):
        configure(commands.add_parser(name))
    return parser
'''

COMMANDS = '''\
from .sdk import execute

def configure(parser):
    colors = ("red", "green", "blue") if VERSION_COMMAND == "legacy" else ("blue", "yellow")
    parser.add_argument("--color", choices=colors)
    parser.add_argument("--old" if VERSION_COMMAND == "legacy" else "--new", action="store_true")
    parser.set_defaults(handler=execute)
'''

SDK = '''\
import os
import requests

marker = os.environ.get("REEF_PROOF_IMPORT_LOG")
if marker:
    with open(marker, "a") as stream:
        stream.write("sdk imported\\n")

def execute(args):
    print("executed " + args.command)
    return 0
'''

BASELINE = '''\
import argcomplete
from .parser import build_parser

def main():
    parser = build_parser()
    argcomplete.autocomplete(parser)
    args = parser.parse_args()
    return args.handler(args)
'''

BASH = r'''
set -e
export PATH="$REEF_PROOF_VENV/bin:$PATH"
export REEF_PROOF_IMPORT_LOG="$REEF_PROOF_TMP/imports.log"
export LC_ALL=C
: > "$REEF_PROOF_IMPORT_LOG"
eval "$(register-python-argcomplete reef-proof reef-proof-baseline --complete-arguments -o nospace)"
printf 'registration_before\t%s\n' "$(complete -p reef-proof)"
printf 'shell_before\t%s\n' "$$"

query() {
    local label="$1" command="$2" line="$3"
    COMP_LINE="$line"
    COMP_POINT=${#COMP_LINE}
    COMP_TYPE=9
    COMP_WORDBREAKS=$' \t\n"\047><=;|&(:'
    _python_argcomplete "$command"
    printf 'query\t%s' "$label"
    printf '\t%s' "${COMPREPLY[@]}"
    printf '\n'
}

query v1_commands reef-proof 'reef-proof '
query v1_options reef-proof 'reef-proof list --'
query v1_choices reef-proof 'reef-proof list --color '
query v1_prefix reef-proof 'reef-proof list --color gr'
test ! -s "$REEF_PROOF_IMPORT_LOG"
printf 'check\tstatic_completion_skips_sdk\ttrue\n'
query baseline_commands reef-proof-baseline 'reef-proof-baseline '
query baseline_options reef-proof-baseline 'reef-proof-baseline list --'
query baseline_choices reef-proof-baseline 'reef-proof-baseline list --color '
query baseline_prefix reef-proof-baseline 'reef-proof-baseline list --color gr'
test "$(wc -l < "$REEF_PROOF_IMPORT_LOG")" -eq 4
printf 'check\tbaseline_imports_sdk\ttrue\n'
: > "$REEF_PROOF_IMPORT_LOG"
reef-proof list > "$REEF_PROOF_TMP/execution.txt"
test "$(cat "$REEF_PROOF_TMP/execution.txt")" = 'executed list'
test "$(wc -l < "$REEF_PROOF_IMPORT_LOG")" -eq 1
printf 'check\treal_command_imports_sdk_and_executes\ttrue\n'
: > "$REEF_PROOF_IMPORT_LOG"

measure() {
    local label="$1" command="$2" started finished
    COMP_LINE="$command list --color "
    COMP_POINT=${#COMP_LINE}
    started=$EPOCHREALTIME
    _python_argcomplete "$command"
    finished=$EPOCHREALTIME
    printf 'timing\t%s\t%s\t%s\n' "$label" "$started" "$finished"
}
# Warm both variants, then alternate ordering to reduce order bias.
measure warmup reef-proof
measure warmup reef-proof-baseline
: > "$REEF_PROOF_IMPORT_LOG"
for ((i=0; i<REEF_PROOF_SAMPLES; i++)); do
    if ((i % 2 == 0)); then
        measure cached reef-proof
        measure baseline reef-proof-baseline
    else
        measure baseline reef-proof-baseline
        measure cached reef-proof
    fi
done
test "$(wc -l < "$REEF_PROOF_IMPORT_LOG")" -eq "$REEF_PROOF_SAMPLES"
printf 'check\tbenchmark_import_counts\ttrue\n'
: > "$REEF_PROOF_IMPORT_LOG"

python -m pip install --disable-pip-version-check --no-deps -U "$REEF_PROOF_V2_WHEEL" > "$REEF_PROOF_TMP/upgrade.log"
test ! -s "$REEF_PROOF_IMPORT_LOG"
printf 'check\twheel_upgrade_does_not_import_application\ttrue\n'
printf 'registration_after\t%s\n' "$(complete -p reef-proof)"
printf 'shell_after\t%s\n' "$$"
query v2_commands reef-proof 'reef-proof '
query v2_options reef-proof 'reef-proof list --'
query v2_choices reef-proof 'reef-proof modern --color '
query v2_removed_command reef-proof 'reef-proof leg'
test ! -s "$REEF_PROOF_IMPORT_LOG"
printf 'check\tupgraded_static_completion_skips_sdk\ttrue\n'
'''


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content))


def fixture(root, version, command, core_wheel):
    build_requirements = [
        "setuptools>=77", "fastcomplete[build] @ " + core_wheel.as_uri(),
        "requests==2.34.2", "argcomplete==3.7.0",
    ]
    write(root / "pyproject.toml", f'''
        [build-system]
        requires = {json.dumps(build_requirements)}
        build-backend = "setuptools.build_meta"
        [project]
        name = "reef-autocomplete-proof-fixture"
        version = "{version}"
        dependencies = ["fastcomplete==0.2.0", "requests==2.34.2", "argcomplete==3.7.0"]
        [project.scripts]
        reef-proof = "fixture.cli:main"
        reef-proof-baseline = "fixture.baseline:main"
        [tool.setuptools.cmdclass]
        build_py = "fastcomplete.setuptools.BuildPy"
        [tool.fastcomplete]
        entrypoint = "fixture.cli:main"
    ''')
    package = root / "fixture"
    write(package / "__init__.py", "")
    write(package / "cli.py", CLI)
    write(package / "parser.py", f"VERSION_COMMAND = {command!r}\n" + PARSER)
    write(package / "commands.py", f"VERSION_COMMAND = {command!r}\n" + COMMANDS)
    write(package / "sdk.py", SDK)
    write(package / "baseline.py", BASELINE)


def checked(command, **kwargs):
    result = subprocess.run(command, text=True, capture_output=True, **kwargs)
    if result.returncode:
        raise RuntimeError(f"Command failed: {command!r}\n{result.stdout}\n{result.stderr}")
    return result


def wheel_cache(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        cache = "fixture/_fastcomplete.cache"
        assert cache in names, names
        record, = [name for name in names if name.endswith(".dist-info/RECORD")]
        cache_record, = [row for row in csv.reader(io.StringIO(archive.read(record).decode())) if row[0] == cache]
        content = archive.read(cache)
        expected_hash = "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(content).digest()).decode().rstrip("=")
        assert cache_record[1:] == [expected_hash, str(len(content))], cache_record
        return hashlib.sha256(content).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("results.json"))
    args = parser.parse_args()
    if args.samples < 2:
        parser.error("--samples must be at least 2")
    wheel = args.wheel.resolve(strict=True)
    assert wheel.name == "fastcomplete-0.2.0-py3-none-any.whl", wheel
    with tempfile.TemporaryDirectory(prefix="fastcomplete-proof-") as temp:
        root = Path(temp)
        fixture(root / "v1", "1.0.0", "legacy", wheel)
        fixture(root / "v2", "2.0.0", "modern", wheel)
        # Default python-build behavior builds an sdist, then a wheel from it.
        checked([sys.executable, "-m", "build", str(root / "v1")])
        checked([sys.executable, "-m", "build", "--wheel", str(root / "v2")])
        v1, = (root / "v1" / "dist").glob("*.whl")
        sdist, = (root / "v1" / "dist").glob("*.tar.gz")
        v2, = (root / "v2" / "dist").glob("*.whl")
        v1_cache, v2_cache = wheel_cache(v1), wheel_cache(v2)
        assert v1_cache != v2_cache
        env_root = root / "venv"
        checked(["uv", "venv", "--seed", "--python", sys.executable, str(env_root)])
        python = str(env_root / "bin" / "python")
        import_log = root / "imports.log"
        environment = os.environ | {
            "REEF_PROOF_TMP": str(root), "REEF_PROOF_VENV": str(env_root),
            "REEF_PROOF_V2_WHEEL": str(v2), "REEF_PROOF_SAMPLES": str(args.samples),
            "REEF_PROOF_IMPORT_LOG": str(import_log),
        }
        checked([python, "-m", "pip", "install", "--disable-pip-version-check", str(wheel), str(v1)], env=environment)
        assert not import_log.exists(), "Wheel installation imported fixture code"
        versions = json.loads(checked([python, "-c", "import json; from importlib.metadata import version; print(json.dumps({n: version(n) for n in ['fastcomplete', 'argcomplete', 'requests']}))"]).stdout)
        execution = checked(["bash", "--noprofile", "--norc"], input=BASH, env=environment)
        queries, raw_queries, checks, timings, metadata = {}, {}, {}, {}, {}
        for line in execution.stdout.splitlines():
            kind, *fields = line.split("\t")
            if kind == "query":
                raw_queries[fields[0]] = sorted(value for value in fields[1:] if value)
                queries[fields[0]] = sorted(value.rstrip() for value in fields[1:] if value)
            elif kind == "check":
                checks[fields[0]] = fields[1] == "true"
            elif kind == "timing":
                if fields[0] != "warmup":
                    timings.setdefault(fields[0], []).append((float(fields[2]) - float(fields[1])) * 1000)
            else:
                metadata[kind] = fields[0]
        expected = {
            "v1_commands": ["--help", "-h", "legacy", "list"],
            "v1_options": ["--color", "--help", "--old"],
            "v1_choices": ["blue", "green", "red"],
            "v1_prefix": ["green"],
            "v2_commands": ["--help", "-h", "list", "modern"],
            "v2_options": ["--color", "--help", "--new"],
            "v2_choices": ["blue", "yellow"],
            "v2_removed_command": [],
        }
        for suffix in ("commands", "options", "choices", "prefix"):
            expected["baseline_" + suffix] = expected["v1_" + suffix]
            assert raw_queries["baseline_" + suffix] == raw_queries["v1_" + suffix], raw_queries
        assert queries == expected, (queries, expected)
        assert metadata["shell_before"] == metadata["shell_after"]
        assert metadata["registration_before"] == metadata["registration_after"]
        assert all(checks.values())
        checks.update(
            installed_wheel_contains_recorded_cache=True,
            sdist_build_produces_cached_wheel=sdist.is_file(),
            cache_changes_with_parser=True,
            wheel_install_does_not_import_application=True,
            matches_argcomplete_supported_scenarios=True,
            same_bash_and_registration_after_upgrade=True,
        )
        summaries = {}
        for name, samples in timings.items():
            assert len(samples) == args.samples
            summaries[name] = {
                "samples": len(samples), "p50_ms": round(statistics.median(samples), 3),
                "p95_ms": round(sorted(samples)[math.ceil(0.95 * len(samples)) - 1], 3),
                "raw_ms": [round(value, 3) for value in samples],
            }
        ratio = statistics.median(timings["baseline"]) / statistics.median(timings["cached"])
        result = {
            "purpose": "Installed-wheel proof of restricted static completion with a requests-coupled parser",
            "wheel": {"filename": wheel.name, "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest()},
            "environment": {"python": platform.python_version(), "platform": platform.platform(),
                            "machine": platform.machine(), "bash": checked(["bash", "--version"]).stdout.splitlines()[0],
                            "packages": versions},
            "checks": checks, "completion_results": queries, "raw_completion_results": raw_queries, "shell": metadata,
            "completion_latency": summaries,
            "reference_targets": {
                "cached_median_below_20_ms": statistics.median(timings["cached"]) < 20,
                "median_speedup_at_least_5x": ratio >= 5,
                "median_speedup": round(ratio, 3),
                "policy": "Report target outcomes; functional validation does not fail on hardware-dependent timings.",
            },
            "measurement": "Bash EPOCHREALTIME around registered argcomplete function; fresh Python process per request; one warmup per variant; paired samples with alternating order; nearest-rank p95.",
            "limitations": [
                "Static parser grammar only; unsupported completion exits quietly with status 1.",
                "Dynamic handoff and editable runtime caching are design work, not implemented behavior.",
                "Programmatic Bash completion function calls do not exercise interactive Readline compopt behavior.",
                "Single machine; requests imports only, with no synthetic delay or network request.",
                "No concurrent upgrade or environment-switch validation.",
            ],
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps({"checks": checks, "completion_latency": summaries, "reference_targets": result["reference_targets"]}, indent=2))


if __name__ == "__main__":
    main()
