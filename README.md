# Autocomplete booster design

Design and validation for NICE-2925, recruitment task #1.

Read [DESIGN.md](DESIGN.md) for the package interface, migration cost, update
guarantees, limitations and alternatives. This is a design submission with a
small executable experiment, not a production package release.

## Reproduce the experiment

On Linux with Python 3.12, Bash 5 and access to PyPI:

```bash
python3.12 proof/validate.py
```

The script creates a temporary environment, installs two fixture versions
through pip, and tests actual argcomplete shell integration. It checks that
commands, options and choices update after `pip install -U` in the same Bash
process without registering completion again. It also measures eager versus
deferred imports using a synthetic 500 ms SDK import.

See [proof/README.md](proof/README.md) for methodology and limitations, and
[proof/results.json](proof/results.json) for the recorded local results.
Running the experiment replaces that results file with the new measurements.

## GitHub Actions

[The workflow](.github/workflows/validate.yml) runs on pushes to `main`, pull
requests and manual dispatch. It uses Ubuntu 24.04 and Python 3.12, executes
the same proof, and uploads the successful run's measurements as the
`autocomplete-validation-results` artifact. No credentials are needed.

CI checks functional assertions, not a machine-independent latency threshold.
Runner timings are recorded separately from the committed local measurements.
