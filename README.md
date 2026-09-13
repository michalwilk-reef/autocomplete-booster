# Fastcomplete

Static argparse completion before expensive SDK imports. The wheel build captures
parser metadata; argcomplete handles shell input/output. No install hook or manual
cache refresh after upgrades.

## Install

```bash
pip install "git+https://github.com/michalwilk-reef/autocomplete-booster.git@0066694c43e9e7b5ec07d8cf008467cf911a1ea1"
```

## Real CLI example

[examples/issuecli](examples/issuecli) is an installable GitHub issues client using
requests:

```bash
pip install "git+https://github.com/michalwilk-reef/autocomplete-booster.git#subdirectory=examples/issuecli"
issuecli issues --repo psf/requests --state open --limit 5 --format text
```

From a local checkout, use `pip install ./examples/issuecli` instead.

Its integration consists of:

1. A lightweight [entry module](examples/issuecli/src/issuecli/entry.py):

   ```python
   import fastcomplete
   fastcomplete.bootstrap()
   from .cli import main
   ```

2. `fastcomplete.autocomplete(parser)` in the [existing CLI](examples/issuecli/src/issuecli/cli.py),
   before `parse_args()`. Its parser still imports the requests-dependent client.
3. The setuptools hook and build dependencies in [pyproject.toml](examples/issuecli/pyproject.toml).
   Parser dependencies must be available during isolated builds.

Use the usual one-time argcomplete registration:

```bash
eval "$(register-python-argcomplete issuecli)"
```

`issuecli-argcomplete` runs the same parser and HTTP client without the bootstrap,
providing a baseline for comparison. `ISSUECLI_API_URL` selects an alternative API
endpoint; by default it uses GitHub.

## Test

```bash
uv sync --locked
uv run --locked pytest -q -s
```

The tests replace the earlier unit/proof suite. They install the example with pip
in a fresh environment, fetching fastcomplete from the published Git revision and
requests from the package index. They make real HTTP requests to a local server,
compare completion with argcomplete, inspect imports, measure fresh processes,
and verify that a pip upgrade changes completion automatically. Requests is not
mocked and no artificial import delay is added.

## Limits

Static subcommands, boolean flags and string choices are supported. Custom/dynamic
parsers and editable builds are not implemented; unsupported completion exits
quietly. There is no automatic argcomplete handoff. The trusted cache is adjacent
to the entry module; keep parent package initializers lightweight and clean build
output after removing modules.

Shell handling comes from [argcomplete](https://kislyuk.github.io/argcomplete/).
Bash/Zsh/PowerShell protocol checks are included; native Windows execution is not
verified locally. Shell descriptions are not cached. Benchmark timings are
machine-dependent, not performance guarantees.
