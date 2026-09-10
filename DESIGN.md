# NICE-2925: Autocomplete booster

Design proposal by Michał Wilk · 2026-09-10

## Decision

Build a small Python package that lets CLI developers bind command handlers
without importing their implementation modules. Keep the actual argparse
parser and use argcomplete to generate completions from it on every request.

The maintainer separates the lightweight command definitions from SDK-dependent
execution code. The package supplies a reusable `deferred("module:function")`
callable for the references between them. Bash completion reaches argcomplete
without loading the SDK; ordinary execution imports the selected handler only
after parsing arguments.

There is no cached command tree, generated copy of the grammar, daemon, or
installation hook. A successful CLI upgrade replaces the parser used by the
next completion request. This directly addresses automatic command-set updates.

This is deliberately a small package. Argcomplete already recommends delaying
expensive imports; the package makes deferred handler binding explicit and
reusable. It cannot undo SDK imports a CLI has already executed. A CLI that
already separates these paths may need no additional package. [Argcomplete
startup guidance](https://kislyuk.github.io/argcomplete/#argcomplete-autocomplete-parser)

## Scope and assumptions

- Audience: maintainers of Python CLIs using argparse and argcomplete.
- Initial target: CPython 3.10+, Bash on Linux; the validation experiment uses
  a specific interpreter and argcomplete version recorded with its results.
- The executable name remains stable across updates. Adding/removing its
  subcommands, flags, or choices must require no completion refresh.
- Users upgrade the same Python environment whose executable their shell
  resolves. Completion is assessed after a successful, completed pip install.
- Parser construction can be separated from heavy SDK initialization. Static
  command names and options must not require creating an SDK client.
- Existing argcomplete behavior is the semantic reference. Accelerating a
  genuinely expensive remote completion query is outside the import-time
  optimization; its current results must not be replaced with stale guesses.
- Automated shell installation and the publishing process are outside scope.

No transparent acceleration is claimed for an arbitrary CLI with an unchanged
import graph. That would conflict with preserving arbitrary Python parser and
completer behavior while guaranteeing inexpensive startup.

## Package interface

Working package name: `autocomplete_booster`; naming/availability is not a
publishing decision.

```python
deferred(target: str) -> Callable
```

`target` is an absolute dotted Python module name and one top-level callable
attribute name, separated by exactly one colon, for example
`fictional_sdk.commands:list_items`. Each module segment and the attribute must
be a Python identifier. The initial interface is for synchronous callables;
it does not await coroutine results or adapt a different invocation protocol.

The returned callable:

1. Does not import or resolve the target during construction.
2. Imports the target module when called, resolves the named callable, and
   forwards positional/keyword arguments and the return value unchanged.
3. Rejects malformed references at construction. An unavailable module,
   missing/non-callable target, or handler exception fails explicitly at
   invocation. There is no alternate handler or cached result.

Target strings are developer-authored declarations, never values obtained from
the command line. Resolution uses `importlib`, not `eval`. The package's own
imports must be lightweight. No process-wide state or parser introspection is
required. Python's ordinary module cache suffices within a single execution.

The handler seam is a normal callable: callers keep using argparse's existing
`set_defaults` dispatch convention. The package does not own argument parsing,
replace argparse actions, or introduce another command-definition language.

## Maintainer integration

Use a lightweight top-level CLI module. It may live in the same distribution
as the SDK; a separate distribution is unnecessary.

```toml
[project.scripts]
fictional-cli = "fictional_cli_entry:main"
```

```python
# fictional_cli_entry.py — imports no SDK modules
import argparse
import argcomplete
from autocomplete_booster import deferred


def build_parser():
    parser = argparse.ArgumentParser(prog="fictional-cli")
    commands = parser.add_subparsers(dest="command", required=True)

    items = commands.add_parser("list")
    items.add_argument("--format", choices=["json", "table"])
    items.set_defaults(handler=deferred("fictional_sdk.commands:list_items"))
    return parser


def main():
    parser = build_parser()
    argcomplete.autocomplete(parser)
    args = parser.parse_args()
    return args.handler(args)
```

```python
# fictional_sdk/commands.py — imported only on command execution
import requests


def list_items(args):
    # Existing SDK command implementation lives here.
    ...
```

The ellipsis represents the existing application's business logic, not a
replacement implementation supplied by the booster. Production commands keep
their existing return/exit behavior.

Argcomplete detects completion requests, emits candidates and exits at
`autocomplete(parser)`; ordinary invocation continues through that call. Thus
the dispatcher is reached only for real commands. [Argcomplete execution
contract](https://kislyuk.github.io/argcomplete/#argcomplete-autocomplete-parser)

An entry point such as `fictional_sdk.cli:main` is unsuitable if importing
`fictional_sdk` already loads the SDK: Python executes parent package
initializers before a submodule. Use a lightweight top-level module as above,
or make every parent initializer lightweight. Entry-point wrappers import their
designated module before calling the function. [Python imports](https://docs.python.org/3/reference/import.html#regular-packages),
[console entry points](https://packaging.python.org/en/latest/specifications/entry-points/#use-for-scripts)

### Migration cost

For an already separated CLI, adoption is one small dependency plus changing
eager handler references to `deferred(...)`. Its existing parser, options,
choices and argcomplete configuration remain the single source of truth.

For a coupled CLI, the real cost is moving parser construction out of SDK
execution modules and removing eager imports from that path. That work is
necessary; presenting this as a one-line speedup would hide it. The number of
handlers and how intertwined their parser definitions are determine the cost.

Review annotations, decorators, default values, parser helpers, plugin discovery,
custom action/type imports and completer initialization as well as obvious
top-level SDK imports. A deferred reference delays missing-target detection,
so normal execution tests must exercise every handler binding before release.

## Bash registration and upgrades

One-time explicit registration in the user's Bash startup configuration:

```bash
eval "$(register-python-argcomplete fictional-cli --complete-arguments -o nospace)"
```

This uses argcomplete's existing shell integration. The explicit completion
options avoid Bash default completion taking over when no candidates are
returned. Argcomplete's own filename completion remains available for parser
arguments that use it. No custom shell protocol is introduced. [Registration
implementation](https://github.com/kislyuk/argcomplete/blob/v3.7.2/argcomplete/scripts/register_python_argcomplete.py),
[shell integration](https://github.com/kislyuk/argcomplete/blob/v3.7.2/argcomplete/shell_integration.py)

The upgrade argument is:

1. Bash's registered function routes completion to `fictional-cli`; it does
   not contain the parser's command list or a separate interpreter path.
2. Each request starts the installed executable in a fresh process.
3. That process imports the currently installed lightweight parser.
4. After `pip install -U our_fictional_cli` completes in that environment,
   the next request reads the upgraded parser. Removed commands disappear;
   added commands, flags and changed choices appear immediately.

This is an inference from the shell integration and console-entry-point
behavior, tested by upgrading a fixture within a still-running Bash session.
The proof does not rely on a version-number comparison or pip executing a
custom post-install hook. [Shell implementation](https://github.com/kislyuk/argcomplete/blob/v3.7.2/argcomplete/shell_integration.py),
[entry-point specification](https://packaging.python.org/en/latest/specifications/entry-points/#use-for-scripts)

Registration is for the literal command name. `./fictional-cli` and arbitrary
absolute-path spellings are not automatically registered. A renamed executable
needs its own initial registration. Those are different from changing the
command set of the same executable. If the user changes environments, the
executable resolved by Bash must be the intended installation; do not pin a
different Python interpreter in the completion setup. [Registration scope](https://kislyuk.github.io/argcomplete/#global-completion)

Keep a tested argcomplete dependency version/protocol for the first release
(the proof uses 3.7.2). Updating the application's command definitions is
supported without touching shell registration. Arbitrary breaking upgrades of
the underlying completion protocol are not promised. A pip install interrupted
halfway through file replacement is also not a valid installed state.

## Dynamic completion and limits

Existing lightweight completers remain attached to argparse actions. Because
each request runs anew, they observe that request's environment, working
directory and data. There is no candidate cache to invalidate.

A heavy callable-style completer function can itself be referenced through
`deferred(...)`, so unrelated completion requests do not import it. It must
accept argcomplete's completion keyword arguments. Readline-style completers
or classes requiring construction need an explicit lightweight adapter; this
wrapper does not translate their protocols. Once selected, its SDK import
and query still cost time. Deferral does not accelerate that necessary work.
The completer author controls its query budget, timeout and error reporting;
the booster does not silently replace a failed query with old candidates.

Custom type conversion, action behavior, validators and parser subclasses keep
their normal argcomplete semantics. They are not serialized or emulated.
Any completion-path callback that imports the SDK must be addressed during
migration; moving only command handlers is insufficient for that case.

The remaining latency is:

```text
shell completion overhead + Python startup + lightweight imports
+ parser construction + selected completer work
```

There is no blanket sub-100-ms guarantee for enormous parsers, slow disks,
interpreter startup hooks, remote queries or SDK-derived command discovery.
For static completion on the validation machine, use p95 below 100 ms as a
local acceptance target and report measured results rather than treating the
task's example import times as universal measurements.

## Alternatives considered

| Approach | Benefit | Why not choose it here |
| --- | --- | --- |
| Only document local imports | Least additional code | A valid solution for one CLI; a package standardizes deferred bindings across commands and applications, but should stay correspondingly small |
| Serialize/cache the constructed parser | Could avoid repeated parser construction | Arbitrary callbacks, closures and custom attributes make general serialization difficult; loading callbacks can reintroduce SDK imports; dependency/plugin/config changes complicate invalidation |
| Generate a static Bash command tree | Can avoid Python startup | Duplicates parser semantics and complicates dynamic completion; generating once becomes stale, while build-time generation imposes another maintained representation |
| Keep a Python worker alive | Can amortize even unavoidable imports | Requires process ownership, isolation, environment/cwd handling and reliable replacement after upgrades; inherited modules can otherwise remain stale |
| Defer imports while keeping the real parser | Removes irrelevant SDK imports and has no persistent state | Requires maintainer refactoring; chosen because the stated bottleneck is heavy imports rather than parsing itself |

A cache or daemon could be justified by measurements showing that necessary
parser/completer work dominates after this separation. They are not part of
this package design. Wheel installation is not a suitable place to assume an
arbitrary application post-install hook will rebuild a user's shell state.
[Wheel installation model](https://packaging.python.org/en/latest/specifications/binary-distribution-format/#installing-a-wheel-distribution-1-0-py32-none-any-whl)

## Validation

The accompanying proof is a focused design experiment, not a production package
release. It uses a synthetic SDK module with an intentionally slow import.
Its purpose is to test the import separation, completion behavior and upgrade
claim with actual installed fixtures. Results are recorded separately so they
can be reproduced without treating hardware-specific timings as a guarantee.

Included evidence: `validate.py` is a self-contained script, `README.md` gives
reproduction instructions, and `results.json` contains assertions, versions
and every timing sample. Run the script with Python 3.12, Bash 5, and access to
PyPI; it creates and removes its own temporary environment. Fixture versions
are built and installed through pip as ordinary non-editable installations.
The upgrade uses `pip install -U <local-v2-project>` so no fixture needs to be
published.

Measured on Python 3.12.3, argcomplete 3.7.2, Bash 5.2.21 and Linux x86_64
on an AMD Ryzen 7 4800H:

| Completion path | Samples | Median | p95 |
| --- | ---: | ---: | ---: |
| Eager SDK import | 30 | 537.566 ms | 540.452 ms |
| Deferred handler | 30 | 39.178 ms | 44.366 ms |

The fixture SDK deliberately sleeps 500 ms during import. Each sample starts
a new Python process; Bash times the registered completion function, with
one unrecorded warmup per variant. The optimized series runs before the eager
series. p95 uses the nearest-rank method. This demonstrates removing that
synthetic cost, not a benchmark of `requests` or a production SDK.

All seven reported checks passed. Import logging showed no SDK imports for
optimized completion, one per eager completion, and one on real command
execution. Without leaving Bash or registering again, the pip upgrade changed
`legacy` to `modern`, `--old` to `--new`, and `red/green/blue` choices to
`blue/yellow`. A lightweight file completer also observed a changed working
directory between requests.

The experiment calls the actual registered Bash function with completion
variables supplied programmatically. It does not drive interactive Readline
TAB keystrokes or validate its `compopt` behavior. Those remain release tests.

Before production release, the acceptance suite should cover:

- Heavy SDK import absent during static completion and present on command
  execution; help and parse errors should not execute command handlers.
- Existing command/option/choice/positional completions compared with the
  original parser; nested commands, quoting, `--flag=value`, `nargs`, custom
  validators and actions included where the CLI uses them.
- One Bash registration surviving a real v1-to-v2 pip upgrade, including an
  added/removed command and changed options/choices on the first request.
- Two environments exposing the same executable name, verifying that selected
  environment and completion agree after a PATH switch.
- Contextual completers observing changed environment/cwd between requests.
- Explicit failures for malformed/missing handler references and SDK import
  exceptions, without accidentally executing a handler during completion.
- Separate-process latency distribution with versions, platform, sample count
  and timing boundaries stated; compare eager and deferred paths using the
  same parser, SDK fixture and shell integration.

Only scenarios explicitly reported as passed in the proof results are claimed
as implemented tests. The broader list above is the proposed release suite.
