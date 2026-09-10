# Autocomplete design experiment

Run on Linux with Python 3.12, Bash 5 and access to PyPI:

```bash
python3.12 validate.py
```

The script creates a temporary virtual environment, installs argcomplete 3.7.2,
builds and installs fixture version 1, and starts one Bash process. That process
registers both fixture commands once, runs completion checks and benchmarks,
then runs `pip install -U` for fixture version 2. It verifies the same process
and registration see the updated commands, options and choices. Temporary
environments and builds are deleted; `results.json` is written next to the
script.

The embedded `deferred("module:function")` helper is a minimal prototype. It
validates reference syntax without importing the target and imports/resolves
the callable only when invoked. This experiment adds it to a fixture package,
not a separately distributed production library.

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
