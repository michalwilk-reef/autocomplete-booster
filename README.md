# Autocomplete booster

A small Python library for keeping expensive command-handler imports out of
argparse/argcomplete completion. Requires Python 3.10 or newer.

## Install

Install directly from this repository with pip:

```bash
pip install "git+https://github.com/michalwilk-reef/autocomplete-booster.git"
```

Or use uv in an existing project:

```bash
uv add "autocomplete-booster @ git+https://github.com/michalwilk-reef/autocomplete-booster.git"
```

The package is not published on PyPI. For a reproducible Git installation,
append `@<commit-sha>` to the repository URL.

## Use

Keep the CLI entry module and parser construction lightweight, and bind
handlers by name:

```python
from autocomplete_booster import deferred

subparser.set_defaults(handler=deferred("my_sdk.commands:list_items"))

argcomplete.autocomplete(parser)
args = parser.parse_args()
args.handler(args)
```

`deferred` imports the handler module only when the returned callable runs.
It forwards arguments and return values unchanged. Malformed references fail
at binding; import, lookup and execution errors propagate at invocation.

Existing CLIs supply their own argparse/argcomplete integration. Installing
this library does not rewrite their imports or register Bash completion.
See [DESIGN.md](DESIGN.md) for a complete integration example and limitations.

## Develop with uv

```bash
uv sync --locked
uv run --locked pytest
uv build
```

`uv build` produces a wheel and source distribution in `dist/`. The build
backend is `uv_build`; pip can build the package without a separate uv CLI
installation. The library has no runtime dependencies.

Install the built wheel with pip:

```bash
pip install dist/autocomplete_booster-0.1.0-py3-none-any.whl
```

The package implements the interface proposed in NICE-2925. The experiment
below exercises the installed wheel, not a duplicate helper implementation.

## Reproduce the experiment

On Linux with uv, Python 3.12, Bash 5 and access to PyPI:

```bash
uv build
uv run --locked python proof/validate.py --wheel dist/autocomplete_booster-0.1.0-py3-none-any.whl
```

The script creates a temporary environment with uv, installs the package wheel
and two fixture versions through pip, and tests actual argcomplete shell integration. It checks that
commands, options and choices update after `pip install -U` in the same Bash
process without registering completion again. It also measures eager versus
deferred imports using a synthetic 500 ms SDK import.

See [proof/README.md](proof/README.md) for methodology and limitations, and
[proof/results.json](proof/results.json) for the recorded local results.
Running the experiment replaces that results file with the new measurements.

## GitHub Actions

[The workflow](.github/workflows/validate.yml) runs on pushes to `main`, pull
requests and manual dispatch. It builds and tests the wheel on Python 3.10 and
3.14, executes the integration proof on Python 3.12, and uploads the wheel,
source distribution and successful run's measurements. No credentials are needed.

CI checks functional assertions, not a machine-independent latency threshold.
Runner timings are recorded separately from the committed local measurements.
