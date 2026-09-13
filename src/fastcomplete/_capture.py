"""Execute a console entrypoint while autocomplete captures its parser."""

import importlib
import sys
from pathlib import Path


def main() -> None:
    entrypoint, build_lib = sys.argv[1:]
    sys.path.insert(0, str(Path(build_lib).resolve()))
    module_name, attribute = entrypoint.split(":")
    module = importlib.import_module(module_name)
    expected = Path(build_lib).resolve().joinpath(*module_name.split(".")).with_suffix(".py")
    if Path(module.__file__).resolve() != expected:
        raise RuntimeError("Capture imported an entrypoint outside the built package")
    sys.argv = [module_name]
    getattr(module, attribute)()
    raise RuntimeError("Entrypoint returned without calling fastcomplete.autocomplete")


if __name__ == "__main__":
    main()
