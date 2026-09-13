# Fastcomplete

Answer static CLI completions before importing the SDK. A setuptools build hook
runs the existing argparse parser once and puts a small cache in the wheel.
Upgrades replace code and cache together; no install hook or runtime source hash.

## Use

Call bootstrap in a lightweight entry module, before SDK imports:

```python
import fastcomplete
fastcomplete.bootstrap()

from existing_cli import main
```

Inside the existing CLI, replace `argcomplete.autocomplete(parser)` with
`fastcomplete.autocomplete(parser)`. Keep parser modules and handlers as they are.
Parent package initializers must also be lightweight.

Configure the CLI's build:

```toml
[build-system]
requires = ["setuptools>=77", "fastcomplete[build]", "requests"]
build-backend = "setuptools.build_meta"

[tool.setuptools.cmdclass]
build_py = "fastcomplete.setuptools.BuildPy"

[tool.fastcomplete]
entrypoint = "my_cli.entry:main"
```

Add every dependency needed to construct the parser to build requirements, and
fastcomplete to runtime dependencies. For local experiments, use the built wheel
as a direct dependency; this package has not been published to PyPI.

## Scope

The cache stores subcommands, boolean flags and string choices, never handlers
or parser objects. Lookup uses bisect. Argcomplete handles tokenization, quoting,
Unicode, cursor position and shell output; this package does not implement its
own Bash/Zsh/PowerShell protocol. Shell descriptions are omitted.
Use [argcomplete's registration instructions](https://kislyuk.github.io/argcomplete/).
Windows depends on its PowerShell integration; native Windows execution has not
been verified locally.

This is a static prototype: custom/dynamic parsers and editable builds are not
implemented. Unsupported completion exits quietly with status 1. Build failures
remain explicit. There is no automatic argcomplete handoff.

The trusted `_fastcomplete.cache` sits beside the entry module, one per package
directory. Use clean build output after deleting modules. Existing SDK-dependent
parser code runs only during builds and ordinary commands.

## Check

```bash
uv sync --locked
uv run --locked pytest -q
uv build
uv run --locked python proof/validate.py --wheel dist/fastcomplete-0.2.0-py3-none-any.whl
```

The proof checks real wheel installs/upgrades and benchmarks against requests.
[Results](proof/results.json) report machine-dependent timings, including missed
targets. Argcomplete is the only runtime dependency and is imported only for TAB.
