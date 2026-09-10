# Autocomplete wheel validation

Run from the repository root on Linux with uv, Python 3.12, Bash 5 and access to PyPI:

```bash
uv build
uv run python proof/validate.py --wheel dist/autocomplete_booster-0.1.0-py3-none-any.whl
```

The script uses `uv venv --seed` to create a temporary virtual environment, then
uses pip to install the supplied package wheel and argcomplete 3.7.2. It builds
and installs fixture version 1, and starts one Bash process. That process
registers both fixture commands once, runs completion checks and benchmarks,
then runs `pip install -U` for fixture version 2. It verifies the same process
and registration see the updated commands, options and choices. Temporary
environments and builds are deleted; `results.json` is written next to the
script.

Both fixture versions declare `autocomplete-booster==0.1.0` as a dependency and
import `deferred` from the installed `autocomplete_booster` package. No helper
implementation is embedded in the experiment. The output records the wheel's
filename, SHA-256 hash and installed distribution version.

The eager and optimized commands share parser definitions. The eager command
imports a synthetic SDK that sleeps for 500 ms; the optimized command imports
it only when dispatching a real command. An import log checks this distinction.

The recorded checks cover:

- Root subcommands, long options and choice values.
- A lightweight dynamic completer which reads `.item` filenames from the current
  directory; changing directories changes suggestions immediately.
- Real command execution imports the synthetic SDK and executes its handler.
- An upgrade replaces `legacy` with `modern`, `--old` with `--new`, and the choice
  list `red/green/blue` with `blue/yellow`, without repeating Bash registration.
- Thirty completion timings per variant, plus one unrecorded warmup each. Each
  request starts a new Python process. Median and nearest-rank p95 are recorded
  along with all raw samples and the environment.

The script calls the registered Bash completion function with the completion
environment populated programmatically. It does not send TAB keystrokes to
interactive Readline or test Readline's `compopt` behavior. Trailing completion
spaces are stripped before comparing suggestions. No real SDK, network
completer, custom argparse action/type, plugin, concurrent upgrade or Python
environment switch is tested. Timings demonstrate the synthetic import cost
being removed; they are not a guarantee for arbitrary CLIs or machines.

`--complete-arguments -o nospace` is explicit in the Bash registration so no
shell fallback completion options are added by the experiment.
