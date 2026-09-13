"""Explicit setuptools integration for capturing a CLI during wheel builds."""

import importlib
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from setuptools.command.build_py import build_py
from setuptools.errors import SetupError
import tomli


class BuildPy(build_py):
    """Build one static cache beside a configured packaged entry module.

    Editable installs and applications requiring their own compiled extensions
    during parser construction are outside this prototype's build contract.
    Use a clean build directory after deleting modules: setuptools can retain
    removed source files in an existing build tree.
    """

    def find_data_files(self, package, src_dir):
        return [
            path for path in super().find_data_files(package, src_dir)
            if Path(path).name != "_fastcomplete.cache"
        ]

    def _configuration(self):
        with open("pyproject.toml", "rb") as stream:
            config = tomli.load(stream)["tool"]["fastcomplete"]
        entrypoint = config["entrypoint"]
        if not isinstance(entrypoint, str):
            raise SetupError("fastcomplete entrypoint must be a module:callable string")
        module, separator, attribute = entrypoint.partition(":")
        parts = module.split(".")
        if (
            not separator or len(parts) < 2
            or not all(part.isidentifier() for part in parts)
            or not attribute.isidentifier()
        ):
            raise SetupError("fastcomplete requires a packaged module:callable entrypoint")
        timeout = config.get("timeout", 30)
        if (
            isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout) or timeout <= 0
        ):
            raise SetupError("fastcomplete timeout must be a positive finite number")

        build_root = Path(self.build_lib).resolve()
        entry_file = build_root.joinpath(*parts).with_suffix(".py")
        cache = entry_file.with_name("_fastcomplete.cache")
        return entrypoint, parts, timeout, build_root, entry_file, cache

    def run(self):
        if self.editable_mode:
            raise SetupError("fastcomplete does not support editable builds")
        entrypoint, parts, timeout, build_root, entry_file, cache = self._configuration()
        cache.unlink(missing_ok=True)
        # Parser capture must observe edits even when timestamp granularity
        # would otherwise make setuptools reuse its previous source copy.
        self.force = True
        super().run()
        if not entry_file.is_file() or any(
            not build_root.joinpath(*parts[:index], "__init__.py").is_file()
            for index in range(1, len(parts))
        ):
            raise SetupError("fastcomplete entrypoint must be inside regular Python packages")
        environment = {
            key: value for key, value in os.environ.items()
            if not key.startswith(("_ARGCOMPLETE", "COMP_", "FASTCOMPLETE_"))
        }
        environment["FASTCOMPLETE_CAPTURE"] = str(cache)
        try:
            # A separate bytecode directory prevents previous builds' pyc
            # files from hiding same-size edits made in the same second.
            with tempfile.TemporaryDirectory(prefix="fastcomplete-pyc-") as bytecode:
                result = subprocess.run(
                    [sys.executable, "-X", f"pycache_prefix={bytecode}", "-m",
                     "fastcomplete.setuptools", entrypoint, str(build_root)],
                    env=environment, capture_output=True, text=True, timeout=timeout,
                )
            if result.returncode or not cache.is_file():
                details = result.stderr.strip() or result.stdout.strip()
                raise SetupError(f"fastcomplete cache capture failed: {details}")
        except subprocess.TimeoutExpired as error:
            cache.unlink(missing_ok=True)
            raise SetupError(f"fastcomplete cache capture exceeded {timeout} seconds") from error
        except BaseException:
            cache.unlink(missing_ok=True)
            raise

    def get_outputs(self, include_bytecode=True):
        outputs = super().get_outputs(include_bytecode)
        outputs.append(str(self._configuration()[-1]))
        return outputs


if __name__ == "__main__":
    entrypoint, build_lib = sys.argv[1:]
    sys.path.insert(0, build_lib)
    module_name, attribute = entrypoint.split(":")
    module = importlib.import_module(module_name)
    expected = Path(build_lib).joinpath(*module_name.split(".")).with_suffix(".py")
    if Path(module.__file__).resolve() != expected:
        raise RuntimeError("Capture imported an entrypoint outside the built package")
    sys.argv = [module_name]
    getattr(module, attribute)()
    raise RuntimeError("Entrypoint returned without calling fastcomplete.autocomplete")
