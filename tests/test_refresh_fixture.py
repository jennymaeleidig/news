"""The fixture-refresh script's one piece of logic that is not I/O: which
files a fixture directory is allowed to contain.

The script itself fetches upstream and is run by hand (CODING_STANDARDS.md);
`drop_stale` is what keeps a fixture directory from accumulating the snapshot
shape of a strategy that no longer exists.
"""

import importlib.util
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

_spec = importlib.util.spec_from_file_location(
    "refresh_fixture", SCRIPTS / "refresh_fixture.py"
)
refresh_fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(refresh_fixture)


def fixture_dir(tmp_path, *names):
    for name in names:
        (tmp_path / name).write_bytes(b"x")
    return tmp_path


def test_drop_stale_keeps_the_current_snapshot_and_the_golden(tmp_path):
    fixture_dir(tmp_path, "upstream.xml", "expected.xml", "upstream.json")

    dropped = refresh_fixture.drop_stale(tmp_path, "upstream.xml")

    assert dropped == ["upstream.json"]                       # a former shape
    assert sorted(p.name for p in tmp_path.iterdir()) == ["expected.xml", "upstream.xml"]


def test_drop_stale_is_a_no_op_on_a_fixture_that_is_already_current(tmp_path):
    fixture_dir(tmp_path, "upstream.xml", "expected.xml")

    assert refresh_fixture.drop_stale(tmp_path, "upstream.xml") == []
    assert sorted(p.name for p in tmp_path.iterdir()) == ["expected.xml", "upstream.xml"]


def test_drop_stale_leaves_directories_alone(tmp_path):
    fixture_dir(tmp_path, "upstream.xml", "expected.xml")
    (tmp_path / "nested").mkdir()

    refresh_fixture.drop_stale(tmp_path, "upstream.xml")

    assert (tmp_path / "nested").is_dir()                     # only files are dropped
