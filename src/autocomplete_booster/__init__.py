"""Defer CLI handler imports until execution, after argcomplete has exited."""

from collections.abc import Callable
from importlib import import_module

__all__ = ["deferred"]


def deferred(target: str) -> Callable[..., object]:
    """Bind a synchronous ``module:callable`` without importing its module.

    Module names may be dotted; the callable must be a single top-level
    attribute. Invalid references raise ValueError immediately. Import,
    lookup and execution failures propagate when the returned callable runs.
    """
    module, separator, attribute = target.partition(":")
    if (
        not separator
        or not all(part.isidentifier() for part in module.split("."))
        or not attribute.isidentifier()
    ):
        raise ValueError("Expected an absolute module:callable reference")

    def invoke(*args: object, **kwargs: object) -> object:
        handler = getattr(import_module(module), attribute)
        if not callable(handler):
            raise TypeError(f"{target!r} does not resolve to a callable")
        return handler(*args, **kwargs)

    return invoke
