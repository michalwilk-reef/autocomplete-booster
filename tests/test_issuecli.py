"""Install the real example, call HTTP, complete commands, then upgrade it."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
ENV = {key: value for key, value in os.environ.items()
       if not key.startswith(("_ARGCOMPLETE", "FASTCOMPLETE_", "COMP_"))}
ENV.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0", PYTHONUTF8="1")


def run(*args, env=ENV):
    result = subprocess.run(args, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return result


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    root = tmp_path_factory.mktemp("issuecli")
    source = root / "source"
    shutil.copytree(ROOT / "examples/issuecli", source,
                    ignore=shutil.ignore_patterns("build", "*.egg-info", "__pycache__"))
    venv = root / "venv"
    run("uv", "venv", "--seed", "--python", sys.executable, str(venv))
    scripts = venv / ("Scripts" if os.name == "nt" else "bin")
    python = str(scripts / ("python.exe" if os.name == "nt" else "python"))
    # This is the user's installation command: pip builds the cache automatically.
    run(python, "-m", "pip", "install", "--disable-pip-version-check", str(source))
    installed = Path(run(python, "-c", "import fastcomplete; print(fastcomplete.__file__)").stdout.strip())
    for module in (ROOT / "src/fastcomplete").glob("*.py"):
        assert installed.with_name(module.name).read_text(encoding="utf-8") == module.read_text(encoding="utf-8"), (
            "Publish the changed library and update the example's Git revision first."
        )
    return SimpleNamespace(root=root, source=source, python=python, scripts=scripts)


@pytest.fixture
def api():
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append((self.path, self.headers["Accept"]))
            body = json.dumps([{"number": 42, "title": "Handle connection timeout"}]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        yield f"http://127.0.0.1:{server.server_port}", calls
        server.shutdown()
        thread.join()


def executable(app, name="issuecli"):
    return str(app.scripts / (name + ".exe" if os.name == "nt" else name))


def completion(app, arguments, *, baseline=False, shell="bash", extra_env=None):
    name = "issuecli-argcomplete" if baseline else "issuecli"
    line = name + " " + arguments
    output = app.root / "completion.txt"
    env = ENV | {
        "_ARGCOMPLETE": "1", "COMP_LINE": line, "COMP_POINT": str(len(line)),
        "_ARGCOMPLETE_STDOUT_FILENAME": str(output), "_ARGCOMPLETE_SHELL": shell,
    } | (extra_env or {})
    started = time.perf_counter()
    result = run(executable(app, name), env=env)
    elapsed = (time.perf_counter() - started) * 1000
    assert result.stdout == ""
    return output.read_text(encoding="utf-8"), result.stderr, elapsed


def test_pip_installs_git_dependency_and_generated_cache(app):
    result = run(app.python, "-c", """
import json
from importlib.metadata import distribution
from pathlib import Path
library = distribution('fastcomplete')
origin = json.loads(library.read_text('direct_url.json'))
assert origin['url'] == 'https://github.com/michalwilk-reef/autocomplete-booster.git'
example = distribution('fastcomplete-issuecli-example')
cache, = [f for f in example.files if f.name == '_fastcomplete.cache']
assert cache.hash is not None
assert Path(example.locate_file(cache)).is_file()
print(origin['vcs_info']['commit_id'])
""")
    assert result.stdout.strip() in (app.source / "pyproject.toml").read_text()


@pytest.mark.parametrize("format,expected", [
    ("text", "#42 Handle connection timeout\n"),
    ("json", '[{"number": 42, "title": "Handle connection timeout"}]\n'),
])
def test_real_requests_call_and_output(app, api, format, expected):
    url, calls = api
    result = run(executable(app), "issues", "--repo", "acme/widgets",
                 "--state", "closed", "--limit", "10", "--format", format,
                 env=ENV | {"ISSUECLI_API_URL": url, "NO_PROXY": "127.0.0.1"})
    assert result.stdout == expected
    assert calls == [("/repos/acme/widgets/issues?state=closed&per_page=10",
                      "application/vnd.github+json")]


@pytest.mark.parametrize("shell", ["bash", "zsh", "powershell"])
def test_completion_matches_argcomplete_without_sdk_or_http(app, api, shell):
    url, calls = api
    env = {"ISSUECLI_API_URL": url, "PYTHONPROFILEIMPORTTIME": "1"}
    for arguments in ("", "iss", "issues --st", "issues --state c", 'issues --format "j'):
        cached, imports, _ = completion(app, arguments, shell=shell, extra_env=env)
        original, original_imports, _ = completion(app, arguments, baseline=True, shell=shell, extra_env=env)
        # Descriptions are not cached. Compare Zsh's candidates independently of them.
        candidates = lambda value: sorted(word.split(":", 1)[0] if shell == "zsh" else word
                                          for word in value.split("\v"))
        assert candidates(cached) == candidates(original)
        assert not re.search(r"\|\s+(requests|issuecli.cli|issuecli.client)$", imports, re.M)
        assert re.search(r"\|\s+requests$", original_imports, re.M)
    assert calls == []


def test_completion_latency(app):
    samples = {False: [], True: []}
    for baseline in samples:
        completion(app, "issues --state ", baseline=baseline)
    for index in range(20):
        for baseline in ((False, True) if index % 2 == 0 else (True, False)):
            _, _, elapsed = completion(app, "issues --state ", baseline=baseline)
            samples[baseline].append(elapsed)
    cached, original = (statistics.median(samples[key]) for key in (False, True))
    print(f"\nInstalled issuecli: {cached:.1f} ms cached, {original:.1f} ms argcomplete, {original / cached:.2f}x faster")


def test_pip_upgrade_refreshes_completion(app):
    before, _, _ = completion(app, "issues --limit ")
    assert sorted(before.split("\v")) == ["10", "5"]
    upgraded = app.root / "upgraded"
    shutil.copytree(app.source, upgraded,
                    ignore=shutil.ignore_patterns("build", "*.egg-info", "__pycache__"))
    project = upgraded / "pyproject.toml"
    project.write_text(project.read_text().replace('version = "0.1.0"', 'version = "0.2.0"'))
    cli = upgraded / "src/issuecli/cli.py"
    cli.write_text(cli.read_text().replace('choices=["5", "10"]', 'choices=["5", "10", "20"]'))
    run(app.python, "-m", "pip", "install", "--disable-pip-version-check", "-U", str(upgraded))
    after, _, _ = completion(app, "issues --limit ")
    assert sorted(after.split("\v")) == ["10", "20", "5"]
