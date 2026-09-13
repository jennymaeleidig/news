"""The CLI's boundary: it parses arguments, prints the console log, and
writes files. Every table and annotation it emits comes from `feeds.render`,
and the direct-table path never fetches.
"""

import pytest

import feeds.__main__ as cli
from feeds.render import render_direct_table
from feeds.run import RunState, SourceRun


def test_main_logs_and_delegates_every_surface_to_render(monkeypatch, capsys, tmp_path):
    runs = [SourceRun(source_id="reddit-rva", state=RunState.STALE, error="HTTP 403")]
    summary = tmp_path / "summary.md"

    monkeypatch.setattr(cli, "load", lambda *a, **k: object())
    monkeypatch.setattr(cli, "generate_site", lambda *a, **k: runs)
    monkeypatch.setattr(cli, "render_annotations", lambda r: ["::warning::from-the-renderer"])
    monkeypatch.setattr(cli, "render_job_summary", lambda r, b: "SUMMARY-FROM-THE-RENDERER\n")

    assert cli.main([
        "gen", "--out", str(tmp_path / "site"), "--summary-file", str(summary),
        "--built-at", "2026-09-13T12:00:00Z",
    ]) == 0

    printed = capsys.readouterr().out
    assert "reddit-rva: STALE — predecessor re-emitted (0 items" in printed  # the vocabulary
    assert "  error: HTTP 403" in printed
    assert "::warning::from-the-renderer" in printed          # annotations come from render
    # the console log comes first, then the annotations as one block
    assert printed.index("reddit-rva: STALE") < printed.index("::warning::from-the-renderer")
    # the summary file is the renderer's string, written as-is
    assert summary.read_text() == "SUMMARY-FROM-THE-RENDERER\n"


def test_main_writes_the_direct_table_without_fetching(monkeypatch, tmp_path, registry):
    monkeypatch.setattr(cli, "load", lambda *a, **k: registry)
    monkeypatch.setattr(cli, "generate_site",
                        lambda *a, **k: pytest.fail("the direct-table path must not fetch"))

    target = tmp_path / "docs" / "direct-feeds.md"
    assert cli.main(["gen", "--direct-table", str(target)]) == 0

    # byte-for-byte what the committed table says, from the registry alone
    assert target.read_text() == render_direct_table(registry)


def test_built_at_is_frozen_with_a_trailing_z():
    parsed = cli._parse_built_at("2026-09-13T12:00:00Z")
    assert parsed.isoformat() == "2026-09-13T12:00:00+00:00"
