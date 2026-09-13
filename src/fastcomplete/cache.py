"""Build static metadata once; look up sorted candidates during completion."""

import argparse
from bisect import bisect_left
import os
import pickle
from pathlib import Path

from argcomplete import CompletionFinder


class UnsupportedCompletion(ValueError):
    """The static evaluator cannot establish the complete answer."""


def snapshot(parser: object) -> dict:
    """Extract schema 2 metadata, rejecting unsupported parser definitions."""
    identity_code = argparse.ArgumentParser(add_help=False)._registries["type"][None].__code__

    def extract(current: object) -> dict:
        if type(current) is not argparse.ArgumentParser:
            raise UnsupportedCompletion("parser subclasses are unsupported")
        if current.prefix_chars != "-" or current.fromfile_prefix_chars is not None:
            raise UnsupportedCompletion("custom prefixes and argument files are unsupported")
        if current._mutually_exclusive_groups:
            raise UnsupportedCompletion("mutually exclusive groups are unsupported")
        if any(name in current.__dict__ for name in ("parse_args", "parse_known_args", "_parse_known_args")):
            raise UnsupportedCompletion("custom parser methods are unsupported")
        converter = current._registry_get("type", None)
        if getattr(converter, "__code__", None) is not identity_code:
            raise UnsupportedCompletion("custom default type registry is unsupported")
        if current._registry_get("type", str, str) is not str:
            raise UnsupportedCompletion("custom string type registry is unsupported")

        actions = {}
        visible = []
        children = {}
        for action in current._actions:
            if getattr(action, "completer", None) is not None:
                raise UnsupportedCompletion("custom completers are unsupported")
            if action.type is not None and action.type is not str:
                raise UnsupportedCompletion("custom argument types are unsupported")
            if type(action) is argparse._SubParsersAction:
                if any(type(name) is not str or not name or name.startswith("-") for name in action.choices):
                    raise UnsupportedCompletion("subcommands must have non-option names")
                children = {name: extract(child) for name, child in action.choices.items()}
                continue
            if not action.option_strings:
                raise UnsupportedCompletion("positional arguments are unsupported")
            if type(action) in (argparse._StoreTrueAction, argparse._StoreFalseAction):
                kind = "flag"
            elif type(action) is argparse._HelpAction:
                kind = "help"
            elif type(action) is argparse._StoreAction and action.nargs is None:
                kind = "value"
            else:
                raise UnsupportedCompletion("custom actions and argument arities are unsupported")
            choices = None
            if action.choices is not None:
                if type(action.choices) not in (list, tuple, set, frozenset):
                    raise UnsupportedCompletion("choices must be a literal string collection")
                if any(type(choice) is not str or not choice or choice.startswith("-") for choice in action.choices):
                    raise UnsupportedCompletion("choices must contain nonempty strings without a leading dash")
                choices = tuple(sorted(set(action.choices)))
            for option in action.option_strings:
                actions[option] = {"kind": kind, "choices": choices}
                if action.help != argparse.SUPPRESS:
                    visible.append(option)
        return {
            "candidates": tuple(sorted(set(visible) | children.keys())),
            "actions": actions,
            "children": children,
        }

    return {"schema": 2, "root": extract(parser)}


def _choices(action: dict) -> tuple[str, ...]:
    choices = action["choices"]
    if choices is None:
        raise UnsupportedCompletion("option requires dynamic value completion")
    return choices


def _prefix(candidates: tuple[str, ...], prefix: str) -> tuple[str, ...]:
    start = bisect_left(candidates, prefix)
    end = start
    while end < len(candidates) and candidates[end].startswith(prefix):
        end += 1
    return candidates[start:end]


def complete(cache: object, words: list[str]) -> tuple[str, ...]:
    """Complete tokens excluding argv[0], including the final (possibly empty) prefix.

    The caller owns shell lexing and escaping. Unknown tokens and unsupported
    contexts are errors; an empty tuple is a successfully established empty answer.
    """
    if type(cache["schema"]) is not int or cache["schema"] != 2:
        raise UnsupportedCompletion("unsupported cache schema")
    node = cache["root"]
    pending = None
    for word in words[:-1]:
        if word == "--":
            raise UnsupportedCompletion("end-of-options is unsupported")
        if pending is not None:
            if word not in _choices(pending):
                raise UnsupportedCompletion("unsupported or invalid option value")
            pending = None
            continue
        if word in node["actions"]:
            action = node["actions"][word]
            if action["kind"] == "help":
                raise UnsupportedCompletion("help terminates argument parsing")
            if action["kind"] == "value":
                pending = action
        elif word in node["children"]:
            node = node["children"][word]
        else:
            raise UnsupportedCompletion("unsupported or unrecognized argument")
    prefix = words[-1]
    if "=" in prefix:
        raise UnsupportedCompletion("attached values are unsupported")
    if pending is not None and not prefix.startswith("-"):
        return _prefix(_choices(pending), prefix)
    return _prefix(node["candidates"], prefix)


class _CachedFinder(CompletionFinder):
    def _get_completions(self, words, prefix, prequote, wordbreak):
        candidates = complete(self.cache, words[1:] + [prefix])
        self._display_completions = dict.fromkeys(candidates, "")
        return self.quote_completions(candidates, prequote, wordbreak)


def run(entry_file: str) -> None:
    try:
        with Path(entry_file).resolve().with_name("_fastcomplete.cache").open("rb") as stream:
            finder = _CachedFinder()
            finder.cache = pickle.load(stream)
        finder(argparse.ArgumentParser(add_help=False))
    except (OSError, pickle.PickleError, UnsupportedCompletion):
        os._exit(1)
