"""Let argcomplete handle the shell; supply only cached candidates."""

import argparse
import os
import pickle
from pathlib import Path

from argcomplete import CompletionFinder

from .cache import UnsupportedCompletion, complete


class _CachedFinder(CompletionFinder):
    def _get_completions(self, words, prefix, prequote, wordbreak):
        candidates = complete(self.cache, words[1:] + [prefix])
        self._display_completions = dict.fromkeys(candidates, "")
        return self.quote_completions(candidates, prequote, wordbreak)


def run(entry_file: str) -> None:
    try:
        with Path(entry_file).resolve().with_name("_fastcomplete.cache").open("rb") as stream:
            cache = pickle.load(stream)
        finder = _CachedFinder()
        finder.cache = cache
        finder(argparse.ArgumentParser(add_help=False))
    except (OSError, pickle.PickleError, UnsupportedCompletion):
        os._exit(1)
