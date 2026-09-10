import sys

import pytest

from autocomplete_booster import deferred


@pytest.fixture
def handlers(tmp_path, monkeypatch):
    package = tmp_path / "example_handlers"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "commands.py").write_text(
        "not_callable = 42\n"
        "def execute(*args, **kwargs):\n"
        "    return args, kwargs\n"
        "def fail(error):\n"
        "    raise error\n"
    )
    (package / "broken.py").write_text("raise RuntimeError('SDK import failed')\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    yield
    for name in list(sys.modules):
        if name == "example_handlers" or name.startswith("example_handlers."):
            del sys.modules[name]


def test_binding_defers_entire_package_import_and_forwards_values(handlers):
    handler = deferred("example_handlers.commands:execute")
    assert "example_handlers" not in sys.modules
    assert "example_handlers.commands" not in sys.modules

    value = object()
    args, kwargs = handler(value, count=3)
    assert args == (value,)
    assert kwargs == {"count": 3}
    assert "example_handlers.commands" in sys.modules


@pytest.mark.parametrize(
    "reference",
    ["", "module", ":run", "module:", "module:run:again", ".module:run",
     "module..commands:run", "module:object.run", "not-a-module:run", "module:bad name"],
)
def test_malformed_reference_fails_at_binding(reference):
    with pytest.raises(ValueError, match="module:callable"):
        deferred(reference)


def test_missing_module_fails_only_on_invocation():
    handler = deferred("missing_autocomplete_booster_test_module:run")
    with pytest.raises(ModuleNotFoundError):
        handler()


def test_missing_attribute_fails_on_invocation(handlers):
    handler = deferred("example_handlers.commands:missing")
    with pytest.raises(AttributeError):
        handler()


def test_non_callable_target_fails_explicitly(handlers):
    handler = deferred("example_handlers.commands:not_callable")
    with pytest.raises(TypeError, match="does not resolve to a callable"):
        handler()


def test_handler_exception_is_preserved(handlers):
    error = RuntimeError("command failed")
    handler = deferred("example_handlers.commands:fail")
    with pytest.raises(RuntimeError) as caught:
        handler(error)
    assert caught.value is error


def test_sdk_import_exception_is_preserved(handlers):
    handler = deferred("example_handlers.broken:run")
    with pytest.raises(RuntimeError, match="SDK import failed"):
        handler()
