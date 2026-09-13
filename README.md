# Fastcomplete

Static argparse completion before expensive SDK imports. The wheel build captures
parser metadata; argcomplete handles shell input/output. No install hook or manual
cache refresh after upgrades.

## Install

```bash
pip install "git+https://github.com/michalwilk-reef/autocomplete-booster.git@0066694c43e9e7b5ec07d8cf008467cf911a1ea1"
```

## Real CLI example

[examples/catcli](examples/catcli) downloads cats from [Cataas](https://cataas.com/)
using requests and Pillow:

```bash
pip install "git+https://github.com/michalwilk-reef/autocomplete-booster.git#subdirectory=examples/catcli"
catcli
catcli --tag cute,orange --output cute.jpg
catcli --gif --output cat.gif
catcli --tag cute --says "Hello!" --font-size 30 --font-color orange --output hello.jpg
catcli --gif --says Hello --filter mono --type square --output hello.gif
catcli --filter custom --brightness 1.2 --saturation 0.5 --hue 90 --lightness 10
catcli --filter custom --r 255 --g 20 --b 0 --width 320 --height 240
catcli --html --output cat.html
catcli --json --output cat.json
catcli --rotate 90 --black-and-white --output portrait.png
```

The response is saved as-is to `--output` (default `cat.jpg`); choose the extension
for the requested format. `--type` and `--filter` have static completion choices.
`--filter blur` uses the current API’s `blur=1` parameter.
Local Pillow operations use the first frame and save according to the output extension;
they cannot be combined with `--html` or `--json`.
Other values are passed to the API; free-text and filename completion are unsupported.

From a local checkout, use `pip install ./examples/catcli` instead.

Its integration consists of:

1. A lightweight [entry module](examples/catcli/src/catcli/entry.py):

   ```python
   import fastcomplete
   fastcomplete.bootstrap()
   from .cli import main
   ```

2. `fastcomplete.autocomplete(parser)` in the [existing CLI](examples/catcli/src/catcli/cli.py),
   before `parse_args()`. Its parser still imports the requests-dependent client.
3. The setuptools hook and build dependencies in [pyproject.toml](examples/catcli/pyproject.toml).
   Parser dependencies must be available during isolated builds.

Use the usual one-time argcomplete registration:

```bash
eval "$(register-python-argcomplete catcli)"
```

`catcli-argcomplete` runs the same parser and HTTP client without the bootstrap,
providing a baseline for comparison. `CATCLI_API_URL` selects an alternative API
endpoint; by default it uses `https://cataas.com`.

## Test

```bash
uv sync --locked
uv run --locked pytest -q -s
```

The tests replace the earlier unit/proof suite. They build fastcomplete from the current checkout and install its wheel with the
example in a fresh environment, using real requests and Pillow dependencies. They make real HTTP requests to a local server,
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
