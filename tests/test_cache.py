import argparse
import pickle

import argcomplete
import pytest

from fastcomplete.cache import UnsupportedCompletion, complete, snapshot


def parser_tree():
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--enabled", action="store_true")
    parser.add_argument("--disabled", action="store_false")
    parser.add_argument("--color", choices=["red", "blue", "black"])
    parser.add_argument("--secret", action="store_true", help=argparse.SUPPRESS)
    commands = parser.add_subparsers()
    users = commands.add_parser("users", aliases=["u"])
    users.add_argument("--format", choices=["json", "text"])
    nested = users.add_subparsers()
    show = nested.add_parser("show")
    show.add_argument("--all", action="store_true")
    return parser


@pytest.mark.parametrize(
    "words",
    [
        [""], ["--"], ["--co"], ["u"], ["unknown"],
        ["--verbose", ""], ["-v", "-v", "--v"],
        ["--enabled", "--disabled", ""], ["--secret", "--"],
        ["--color", ""], ["--color", "bl"], ["--color", "none"],
        ["--color", "--"], ["--color", "red", ""],
        ["users", ""], ["u", "--f"], ["users", "--format", "j"],
        ["users", "show", ""], ["users", "show", "--all", "--a"],
        ["--color", "blue", "users", "--format", "text", "sh"],
    ],
)
def test_static_answers_match_argcomplete(words):
    parser = parser_tree()
    cached = complete(snapshot(parser), words)
    finder = argcomplete.CompletionFinder(parser, append_space=False)
    expected = finder._get_completions(["tool"] + words[:-1], words[-1], "", None)
    assert cached == tuple(sorted(expected))


def test_snapshot_excludes_unpickleable_handlers_and_defaults():
    parser = parser_tree()
    parser.set_defaults(handler=lambda args: args, connection=object())
    cache = pickle.loads(pickle.dumps(snapshot(parser)))
    assert set(cache) == {"schema", "root"}
    assert complete(cache, ["--co"]) == ("--color",)


def test_choice_free_option_name_is_static_but_value_is_not():
    parser = argparse.ArgumentParser()
    parser.add_argument("--path")
    cache = snapshot(parser)
    assert complete(cache, ["--pa"]) == ("--path",)
    with pytest.raises(UnsupportedCompletion, match="dynamic"):
        complete(cache, ["--path", ""])
    with pytest.raises(UnsupportedCompletion):
        complete(cache, ["--path", "somewhere", ""])


@pytest.mark.parametrize("words", [
    ["--color", "invalid", ""], ["--color=red", ""], ["--color=r"],
    ["--", ""], ["-vv", ""], ["--verb", ""], ["unknown", ""],
    ["--help", ""], ["users", "--verbose", ""], ["--color", "--enabled", ""],
])
def test_unsupported_requests_raise(words):
    with pytest.raises(UnsupportedCompletion):
        complete(snapshot(parser_tree()), words)


@pytest.mark.parametrize("configure", [
    lambda p: p.add_argument("filename"),
    lambda p: p.add_argument("--many", nargs="*"),
    lambda p: p.add_argument("--pair", nargs=2),
    lambda p: p.add_argument("--number", type=int),
    lambda p: p.add_argument("--append", action="append"),
    lambda p: p.add_argument("--count", action="count"),
    lambda p: p.add_argument("--number", choices=[1, 2]),
    lambda p: p.add_argument("--letter", choices="abc"),
    lambda p: setattr(p.add_argument("--api"), "completer", lambda **kwargs: ["dynamic"]),
    lambda p: p.add_mutually_exclusive_group().add_argument("--one", action="store_true"),
])
def test_unsupported_definitions_raise(configure):
    parser = argparse.ArgumentParser()
    configure(parser)
    with pytest.raises(UnsupportedCompletion):
        snapshot(parser)


def test_custom_parser_and_action_classes_rejected():
    class Parser(argparse.ArgumentParser):
        pass

    class Action(argparse.Action):
        pass

    with pytest.raises(UnsupportedCompletion):
        snapshot(Parser())
    parser = argparse.ArgumentParser()
    parser.add_argument("--custom", action=Action)
    with pytest.raises(UnsupportedCompletion):
        snapshot(parser)


@pytest.mark.parametrize("kwargs", [{"prefix_chars": "+"}, {"fromfile_prefix_chars": "@"}])
def test_unsupported_parser_configuration(kwargs):
    with pytest.raises(UnsupportedCompletion):
        snapshot(argparse.ArgumentParser(**kwargs))


def test_unknown_schema_rejected():
    cache = snapshot(parser_tree())
    cache["schema"] = 2
    with pytest.raises(UnsupportedCompletion, match="schema"):
        complete(cache, [""])


def test_string_indexes_sorted_at_build():
    parser = argparse.ArgumentParser()
    parser.add_argument("--value", choices=["z", "a", "a"])
    cache = snapshot(parser)
    assert cache["root"]["actions"]["--value"]["choices"] == ("a", "z")
    assert complete(cache, ["--value", ""]) == ("a", "z")


@pytest.mark.parametrize("type_key", [None, str])
def test_customized_builtin_type_registry_rejected(type_key):
    parser = argparse.ArgumentParser()
    parser.register("type", type_key, lambda value: value.upper())
    parser.add_argument("--color", type=type_key, choices=["red"])
    with pytest.raises(UnsupportedCompletion, match="type registry"):
        snapshot(parser)


@pytest.mark.parametrize("choice", ["-1", "--other"])
def test_dash_choices_rejected_before_they_can_be_offered(choice):
    parser = argparse.ArgumentParser()
    parser.add_argument("--value", choices=[choice, "red"])
    with pytest.raises(UnsupportedCompletion, match="leading dash"):
        snapshot(parser)
