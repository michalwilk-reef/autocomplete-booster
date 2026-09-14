"""Static completion prototype. Importing this module loads no application code."""

import os

__all__ = ["bootstrap", "autocomplete"]


def bootstrap() -> None:
    """Try cached completion before importing the application and its parser."""
    if "_ARGCOMPLETE" not in os.environ or "FASTCOMPLETE_CAPTURE" in os.environ:
        return

    import sys
    from .cache import run

    run(sys._getframe(1).f_globals["__file__"])


def autocomplete(parser: object) -> None:
    """Capture build metadata or complete using the application's parser."""
    destination = os.environ.get("FASTCOMPLETE_CAPTURE")
    if destination is not None:
        import pickle
        from .cache import snapshot

        payload = snapshot(parser)
        with open(destination, "wb") as stream:
            pickle.dump(payload, stream, protocol=4)
        os._exit(0)

    if "_ARGCOMPLETE" in os.environ:
        import argcomplete

        argcomplete.autocomplete(parser)
