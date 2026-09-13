"""Install the real example, call HTTP, complete commands, then upgrade it."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import base64
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


IMAGE = base64.b64decode("R0lGODdhAgABAIEAAP8AAAAA/wAAAAAAACwAAAAAAgABAAAIBQABBAgIADs=")

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
    root = tmp_path_factory.mktemp("catcli")
    source = root / "source"
    shutil.copytree(ROOT / "examples/catcli", source,
                    ignore=shutil.ignore_patterns("build", "*.egg-info", "__pycache__"))
    wheels = root / "wheels"
    run("uv", "build", "--wheel", "--out-dir", str(wheels), str(ROOT))
    wheel, = wheels.glob("*.whl")
    project = source / "pyproject.toml"
    project.write_text(re.sub(r"git\+https://[^\"]+", wheel.as_uri(), project.read_text()))
    venv = root / "venv"
    run("uv", "venv", "--seed", "--python", sys.executable, str(venv))
    scripts = venv / ("Scripts" if os.name == "nt" else "bin")
    python = str(scripts / ("python.exe" if os.name == "nt" else "python"))
    # This is the user's installation command: pip builds the cache automatically.
    run(python, "-m", "pip", "install", "--disable-pip-version-check", str(source))
    return SimpleNamespace(root=root, source=source, python=python, scripts=scripts)


@pytest.fixture
def api():
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append((self.path, self.headers["Accept"]))
            body, content_type = IMAGE, "image/gif"
            if "json=true" in self.path:
                body, content_type = b'{"id":"test-cat"}', "application/json"
            elif "html=true" in self.path:
                body, content_type = b'<img src="/cat">', "text/html"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
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


def executable(app, name="catcli"):
    return str(app.scripts / (name + ".exe" if os.name == "nt" else name))


def completion(app, arguments, *, baseline=False, shell="bash", extra_env=None):
    name = "catcli-argcomplete" if baseline else "catcli"
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


def test_pip_installs_generated_cache(app):
    run(app.python, "-c", """
from importlib.metadata import distribution
from pathlib import Path
example = distribution('fastcomplete-catcli-example')
cache, = [f for f in example.files if f.name == '_fastcomplete.cache']
assert cache.hash is not None
assert Path(example.locate_file(cache)).is_file()
""")


@pytest.mark.parametrize("arguments,path,body", [
    ([], "/cat", IMAGE),
    (["--tag", "cute,orange"], "/cat/cute,orange", IMAGE),
    (["--gif"], "/cat/gif", IMAGE),
    (["--filter", "blur"], "/cat?blur=1", IMAGE),
    (["--says", "Hi / cat?"], "/cat/says/Hi%20%2F%20cat%3F", IMAGE),
    (["--tag", "cute", "--says", "Hello"], "/cat/cute/says/Hello", IMAGE),
    (["--gif", "--says", "Hello", "--filter", "mono", "--font-color", "orange",
      "--font-size", "20", "--type", "square"],
     "/cat/gif/says/Hello?type=square&filter=mono&fontSize=20&fontColor=orange", IMAGE),
    (["--filter", "custom", "--brightness", "1.2", "--lightness", "10",
      "--saturation", "0.5", "--hue", "90", "--r", "255", "--g", "20", "--b", "0",
      "--width", "320", "--height", "240"],
     "/cat?filter=custom&brightness=1.2&lightness=10&saturation=0.5&hue=90&r=255&g=20&b=0&width=320&height=240", IMAGE),
    (["--html"], "/cat?html=true", b'<img src="/cat">'),
    (["--json"], "/cat?json=true", b'{"id":"test-cat"}'),
])
def test_real_requests_download(app, api, tmp_path, arguments, path, body):
    url, calls = api
    output = tmp_path / "cat.out"
    result = run(executable(app), *arguments, "--output", str(output),
                 env=ENV | {"CATCLI_API_URL": url, "NO_PROXY": "127.0.0.1"})
    assert result.stdout.strip() == str(output)
    assert output.read_bytes() == body
    assert calls == [(path, "application/json" if "--json" in arguments else "*/*")]


@pytest.mark.parametrize("arguments,size,mode,pixels", [
    (["--rotate", "90"], (1, 2), "RGB", [(0, 0, 255), (255, 0, 0)]),
    (["--black-and-white"], (2, 1), "L", [76, 29]),
    (["--rotate", "90", "--black-and-white"], (1, 2), "L", [29, 76]),
])
def test_local_image_operations(app, api, tmp_path, arguments, size, mode, pixels):
    url, calls = api
    output = tmp_path / "edited.png"
    run(executable(app), *arguments, "--output", str(output),
        env=ENV | {"CATCLI_API_URL": url, "NO_PROXY": "127.0.0.1"})
    run(app.python, "-c", f"""
from PIL import Image
with Image.open({str(output)!r}) as image:
    assert image.size == {size!r}
    assert image.mode == {mode!r}
    assert list(image.getdata()) == {pixels!r}
""")
    assert calls == [("/cat", "*/*")]


@pytest.mark.parametrize("format", ["--html", "--json"])
def test_image_operations_reject_non_image_formats(app, api, format):
    url, calls = api
    result = subprocess.run([executable(app), format, "--rotate", "90"],
                            env=ENV | {"CATCLI_API_URL": url}, capture_output=True, text=True)
    assert result.returncode == 1
    assert "image operations cannot be used" in result.stderr
    assert calls == []


@pytest.mark.parametrize("shell", ["bash", "zsh", "powershell"])
def test_completion_matches_argcomplete_without_sdk_or_http(app, api, shell):
    url, calls = api
    env = {"CATCLI_API_URL": url, "PYTHONPROFILEIMPORTTIME": "1"}
    for arguments in ("", "--fi", "--filter ", "--filter m", '--type "s', "--gif --filter mono --type ", "--rotate ", "--black-and-white --rotate 9"):
        cached, imports, _ = completion(app, arguments, shell=shell, extra_env=env)
        original, original_imports, _ = completion(app, arguments, baseline=True, shell=shell, extra_env=env)
        # Descriptions are not cached. Compare Zsh's candidates independently of them.
        candidates = lambda value: sorted(word.split(":", 1)[0] if shell == "zsh" else word
                                          for word in value.split("\v"))
        assert candidates(cached) == candidates(original)
        assert not re.search(r"\|\s+(requests|PIL(?:\.\w+)?|catcli.cli|catcli.client)$", imports, re.M)
        assert re.search(r"\|\s+requests$", original_imports, re.M)
        assert re.search(r"\|\s+PIL.Image$", original_imports, re.M)
    assert calls == []


def test_completion_latency(app):
    samples = {False: [], True: []}
    for baseline in samples:
        completion(app, "--filter ", baseline=baseline)
    for index in range(20):
        for baseline in ((False, True) if index % 2 == 0 else (True, False)):
            _, _, elapsed = completion(app, "--filter ", baseline=baseline)
            samples[baseline].append(elapsed)
    cached, original = (statistics.median(samples[key]) for key in (False, True))
    print(f"\nInstalled catcli: {cached:.1f} ms cached, {original:.1f} ms argcomplete, {original / cached:.2f}x faster")


def test_pip_upgrade_refreshes_completion(app):
    before, _, _ = completion(app, "--sav")
    assert before == ""
    upgraded = app.root / "upgraded"
    shutil.copytree(app.source, upgraded,
                    ignore=shutil.ignore_patterns("build", "*.egg-info", "__pycache__"))
    project = upgraded / "pyproject.toml"
    project.write_text(project.read_text().replace('version = "0.2.0"', 'version = "0.3.0"'))
    cli = upgraded / "src/catcli/cli.py"
    cli.write_text(cli.read_text().replace('"--output", default=', '"--output", "--save", default='))
    run(app.python, "-m", "pip", "install", "--disable-pip-version-check", "-U", str(upgraded))
    after, _, _ = completion(app, "--sav")
    assert after.strip() == "--save"
