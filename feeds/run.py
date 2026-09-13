"""The run vocabulary: what a source's run did, named once.

`RunState` owns the wire value (which the index's client-side JS reads as
`data-state`), the console/Job Summary word, and nothing else. `SourceRun` is
the per-source record both `publish` and `render` speak.

This module is a stdlib-only leaf: `publish` produces `SourceRun`s and
`render` consumes them. (Publish composes render's pages; render never needs
to know how a Run was produced.)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RunState(StrEnum):
    """The three things a source's run can be.

    `OK` is a successful upstream fetch. `STALE` is a failed fetch whose
    predecessor was re-emitted unchanged — the feed freezes, the badge ages.
    `FAILED` is a failed fetch with no predecessor either: an empty channel.

    Each member is `(wire value, summary word)`, so a new state is one line
    and cannot arrive without the word the console and Job Summary print.
    """

    def __new__(cls, value: str, word: str):
        member = str.__new__(cls, value)
        member._value_ = value
        member._word = word
        return member

    OK = ("ok", "fetched")
    STALE = ("stale", "STALE — predecessor re-emitted")
    FAILED = ("failed", "FAILED — empty channel")

    @property
    def summary_word(self) -> str:
        """How the console line, the Job Summary row and the annotation spell
        this state. Owned here so no caller can invent a second vocabulary."""
        return self._word


@dataclass(frozen=True)
class SourceRun:
    """One source's **Run**: its state, what it published, and the failure
    note when there was one."""

    source_id: str
    state: RunState
    item_count: int = 0
    last_build: str = ""  # what the emitted file's lastBuildDate says (RFC-2822)
    error: str = ""
    note: str = ""
