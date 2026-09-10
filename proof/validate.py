#!/usr/bin/env python3
"""Reproducible Linux design experiment. Run with Python 3.12; requires Bash and pip access.

All environments and fixture builds live in a temporary directory. This writes
results.json beside this script. It is not an installable production package.
"""

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


SAMPLES = 30

DEFERRED = '''\
from importlib import import_module

def deferred(reference):
    module, function = reference.split(":")
    if not all(part.isidentifier() for part in module.split(".")) or not function.isidentifier():
        raise ValueError("Expected module:function")

    def invoke(*args, **kwargs):
        target = getattr(import_module(module), function)
        return target(*args, **kwargs)

    return invoke
'''

CLI = '''\
import argparse
from pathlib import Path
import argcomplete
from .booster import deferred

def items(prefix, **kwargs):
    return [p.name for p in Path.cwd().glob("*.item")
            if p.name.startswith(prefix)]

def build_parser():
    parser = argparse.ArgumentParser(prog="reef-proof")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("list", VERSION_COMMAND):
        command = commands.add_parser(name)
        colors = ("red", "green", "blue") if VERSION_COMMAND == "legacy" else ("blue", "yellow")
        command.add_argument("--color", choices=colors)
        command.add_argument("--old" if VERSION_COMMAND == "legacy" else "--new", action="store_true")
        command.add_argument("--item").completer = items
        command.set_defaults(func=deferred("fixture.sdk:execute"))
    return parser

def main():
    parser = build_parser()
    argcomplete.autocomplete(parser)
    args = parser.parse_args()
    return args.func(args)
'''

SDK = '''\
import os
from pathlib import Path
import time

time.sleep(0.5)
with Path(os.environ["REEF_PROOF_IMPORT_LOG"]).open("a") as stream:
    stream.write("sdk imported\\n")

def execute(args):
    print("executed " + args.command)
    return 0
'''

BASH = r'''
set -e
export PATH="$REEF_PROOF_VENV/bin:$PATH"
export REEF_PROOF_IMPORT_LOG="$REEF_PROOF_TMP/imports.log"
export LC_ALL=C
: > "$REEF_PROOF_IMPORT_LOG"
eval "$(register-python-argcomplete reef-proof reef-proof-eager --complete-arguments -o nospace)"
registration_before=$(complete -p reef-proof)
printf 'registration_before\t%s\n' "$registration_before"
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
mkdir "$REEF_PROOF_TMP/one" "$REEF_PROOF_TMP/two"
touch "$REEF_PROOF_TMP/one/one.item" "$REEF_PROOF_TMP/two/two.item"
cd "$REEF_PROOF_TMP/one"
query cwd_one reef-proof 'reef-proof list --item '
cd "$REEF_PROOF_TMP/two"
query cwd_two reef-proof 'reef-proof list --item '
test ! -s "$REEF_PROOF_IMPORT_LOG"
printf 'check\toptimized_scenarios_no_sdk_import\ttrue\n'

benchmark() {
    local label="$1" command="$2"
    # One unrecorded warmup for filesystem caches, still a new Python process.
    COMP_LINE="$command list --color "
    COMP_POINT=${#COMP_LINE}
    _python_argcomplete "$command"
    local i started finished
    for ((i=0; i<REEF_PROOF_SAMPLES; i++)); do
        started=$EPOCHREALTIME
        _python_argcomplete "$command"
        finished=$EPOCHREALTIME
        printf 'timing\t%s\t%s\t%s\n' "$label" "$started" "$finished"
    done
}

benchmark optimized reef-proof
test ! -s "$REEF_PROOF_IMPORT_LOG"
printf 'check\toptimized_benchmark_no_sdk_import\ttrue\n'
benchmark eager reef-proof-eager
printf 'eager_imports\t%s\n' "$(wc -l < "$REEF_PROOF_IMPORT_LOG")"
: > "$REEF_PROOF_IMPORT_LOG"
reef-proof list > "$REEF_PROOF_TMP/execution.txt"
test "$(cat "$REEF_PROOF_TMP/execution.txt")" = 'executed list'
test "$(wc -l < "$REEF_PROOF_IMPORT_LOG")" -eq 1
printf 'check\treal_command_imports_sdk_and_executes\ttrue\n'
: > "$REEF_PROOF_IMPORT_LOG"

# Upgrade runs inside this same Bash process; registration is not repeated.
python -m pip install --disable-pip-version-check --no-build-isolation --no-deps -U "$REEF_PROOF_TMP/v2" > "$REEF_PROOF_TMP/upgrade.log"
test "$(complete -p reef-proof)" = "$registration_before"
printf 'registration_after\t%s\n' "$(complete -p reef-proof)"
printf 'shell_after\t%s\n' "$$"
query v2_commands reef-proof 'reef-proof '
query v2_options reef-proof 'reef-proof list --'
query v2_choices reef-proof 'reef-proof modern --color '
query v2_removed_command reef-proof 'reef-proof leg'
test ! -s "$REEF_PROOF_IMPORT_LOG"
printf 'check\tupgraded_completion_no_sdk_import\ttrue\n'
'''


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content))


def fixture(root, version, command):
    package = root / 'fixture'
    write(root / 'pyproject.toml', f'''
        [build-system]
        requires = ["setuptools==84.0.0", "wheel==0.48.0"]
        build-backend = "setuptools.build_meta"
        [project]
        name = "reef-autocomplete-proof-fixture"
        version = "{version}"
        dependencies = ["argcomplete==3.7.2"]
        [project.scripts]
        reef-proof = "fixture.cli:main"
        reef-proof-eager = "fixture.eager:main"
    ''')
    write(package / '__init__.py', '')
    write(package / 'booster.py', DEFERRED)
    write(package / 'cli.py', f'VERSION_COMMAND = {command!r}\n' + CLI)
    write(package / 'sdk.py', SDK)
    write(package / 'eager.py', 'from . import sdk\nfrom .cli import main\n')


def checked(command, **kwargs):
    return subprocess.run(command, check=True, text=True, capture_output=True, **kwargs)


def main():
    assert sys.version_info[:2] == (3, 12), 'Run this experiment with Python 3.12'
    with tempfile.TemporaryDirectory(prefix='reef-autocomplete-proof-') as temp:
        root = Path(temp)
        env_root = root / 'venv'
        fixture(root / 'v1', '1.0.0', 'legacy')
        fixture(root / 'v2', '2.0.0', 'modern')
        checked([sys.executable, '-m', 'venv', str(env_root)])
        python = str(env_root / 'bin' / 'python')
        checked([python, '-m', 'pip', 'install', '--disable-pip-version-check',
                 'argcomplete==3.7.2', 'setuptools==84.0.0', 'wheel==0.48.0'])
        checked([python, '-m', 'pip', 'install', '--disable-pip-version-check',
                 '--no-build-isolation', '--no-deps', str(root / 'v1')])
        environment = os.environ | {
            'REEF_PROOF_TMP': str(root), 'REEF_PROOF_VENV': str(env_root),
            'REEF_PROOF_SAMPLES': str(SAMPLES),
        }
        execution = subprocess.run(['bash', '--noprofile', '--norc'], input=BASH,
                                   env=environment, text=True, capture_output=True)
        if execution.returncode:
            raise RuntimeError(execution.stdout + '\n' + execution.stderr)
        queries, checks, timings, metadata = {}, {}, {}, {}
        for line in execution.stdout.splitlines():
            kind, *fields = line.split('\t')
            if kind == 'query':
                queries[fields[0]] = sorted(value.rstrip() for value in fields[1:] if value)
            elif kind == 'check':
                checks[fields[0]] = fields[1] == 'true'
            elif kind == 'timing':
                timings.setdefault(fields[0], []).append(
                    (float(fields[2]) - float(fields[1])) * 1000)
            else:
                metadata[kind] = fields[0]
        expected = {
            'v1_commands': ['--help', '-h', 'legacy', 'list'],
            'v1_options': ['--color', '--help', '--item', '--old'],
            'v1_choices': ['blue', 'green', 'red'],
            'cwd_one': ['one.item'], 'cwd_two': ['two.item'],
            'v2_commands': ['--help', '-h', 'list', 'modern'],
            'v2_options': ['--color', '--help', '--item', '--new'],
            'v2_choices': ['blue', 'yellow'],
            'v2_removed_command': [],
        }
        assert queries == expected, (queries, expected)
        assert metadata['shell_before'] == metadata['shell_after']
        assert metadata['registration_before'] == metadata['registration_after']
        assert int(metadata['eager_imports']) == SAMPLES + 1
        assert all(checks.values())
        checks.update(exact_completion_scenarios=True,
                      same_bash_process_and_unchanged_registration_after_upgrade=True,
                      eager_imports_sdk_for_every_completion=True)
        summaries = {}
        for name, samples in timings.items():
            assert len(samples) == SAMPLES
            summaries[name] = {
                'samples': len(samples), 'p50_ms': round(statistics.median(samples), 3),
                'p95_ms': round(sorted(samples)[math.ceil(0.95 * len(samples)) - 1], 3),
                'raw_ms': [round(value, 3) for value in samples],
            }
        result = {
            'purpose': 'Synthetic design validation, not production performance guarantee',
            'environment': {'python': platform.python_version(), 'platform': platform.platform(),
                            'machine': platform.machine(),
                            'cpu': next(line.split(':', 1)[1].strip()
                                        for line in Path('/proc/cpuinfo').read_text().splitlines()
                                        if line.startswith('model name')),
                            'bash': checked(['bash', '--version']).stdout.splitlines()[0],
                            'argcomplete': '3.7.2', 'synthetic_sdk_import_delay_ms': 500},
            'checks': checks, 'completion_results': queries, 'shell': metadata,
            'completion_latency': summaries,
            'measurement': 'Bash EPOCHREALTIME around the registered argcomplete function; '
                           'one unrecorded warmup per variant; new Python process for each request; '
                           'optimized series precedes eager series; p95 is nearest rank.',
            'limitations': [
                'Synthetic 500 ms sleep represents import latency; no real SDK was benchmarked.',
                'Calls the actually registered Bash completion function with completion variables; '
                'does not drive interactive Readline TAB keystrokes.',
                'The noninteractive function call cannot exercise Readline compopt behavior.',
                'Only one machine, Python version, argcomplete version and basic parser grammar tested.',
                'No network completers, custom argparse actions/types, plugins or environment switching tested.',
                'No concurrent pip upgrade/completion race tested.',
                'Deferred helper is a minimal embedded prototype, not a production package.',
            ],
        }
        destination = Path(__file__).with_name('results.json')
        destination.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps({'checks': checks, 'completion_latency': summaries}, indent=2))


if __name__ == '__main__':
    main()
