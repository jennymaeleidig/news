"""The run-state vocabulary: one enum owns the wire value, the console/Job
Summary word, and the client-side `data-state` (spec D6). Both the badge and
the summary row derive from it, so they cannot drift.
"""

from dataclasses import FrozenInstanceError

import pytest

from feeds.run import RunState, SourceRun


def test_state_wire_values_are_stable():
    assert RunState.OK == "ok"
    assert RunState.STALE == "stale"
    assert RunState.FAILED == "failed"


@pytest.mark.parametrize("state, word", [
    (RunState.OK, "fetched"),
    (RunState.STALE, "STALE — predecessor re-emitted"),
    (RunState.FAILED, "FAILED — empty channel"),
])
def test_state_owns_its_summary_word(state, word):
    assert state.summary_word == word


def test_every_state_has_a_summary_word():
    # Not a guard against a wordless state — the enum's (value, word) shape
    # makes that a TypeError at class creation. This pins the three words.
    for state in RunState:
        assert state.summary_word


def test_source_run_carries_the_vocabulary_not_a_bare_string():
    run = SourceRun(source_id="arxiv-cl", state=RunState.STALE)
    assert run.state is RunState.STALE
    assert run.state.summary_word == "STALE — predecessor re-emitted"
    assert run.item_count == 0 and run.last_build == ""
    assert run.error == "" and run.note == ""


def test_a_state_formats_as_its_wire_value():
    # StrEnum keeps the wire value usable in f-strings and comparisons while
    # `summary_word` stays owned by the enum — and it is frozen, because a Run
    # is a value that flows from publish to render.
    assert f"{RunState.FAILED}" == "failed"
    assert isinstance(RunState.OK, str)
    with pytest.raises(FrozenInstanceError):
        SourceRun(source_id="x", state=RunState.OK).state = RunState.FAILED
