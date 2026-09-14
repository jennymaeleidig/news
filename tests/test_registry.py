"""Registry loading and validation — the whole repo derives from
sources.toml, so the loader's guarantees are load-bearing."""

import tomllib

import pytest

from feeds.registry import RegistryError, Source, load


def test_real_registry_shape(registry):
    assert len(registry.sources) == 24
    assert len(registry.direct()) == 23
    assert len(registry.hosted()) == 1
    # Owner-blessed registry order (direct first, hosted last).
    assert registry.direct()[0].id == "radarai"
    assert registry.direct()[-1].id == "reddit-rva"
    assert registry.hosted()[0].id == "richmond-times-dispatch"
    assert registry.hosted()[-1].id == "richmond-times-dispatch"


def test_ids_are_unique(registry):
    ids = [s.id for s in registry.sources]
    assert len(ids) == len(set(ids))


def test_hosted_sources_declare_why_and_strategy(registry):
    for source in registry.hosted():
        assert source.why, f"{source.id} missing why"
        assert source.strategy is not None, f"{source.id} missing strategy"


def test_direct_sources_declare_no_strategy_and_no_why(registry):
    for source in registry.direct():
        assert source.strategy is None
        assert not source.why


def test_feed_meta_and_channel_description(registry):
    assert registry.feed.title == "Jenny's news sources"
    # a source with a note: the note is what the channel says
    noted = Source(id="x", name="X", mode="hosted", url="https://example.com/x.xml",
                   why="because", note="Kept for the LLM subset, topic-filtered server-side.")
    assert registry.feed.channel_description(noted) == (
        "Kept for the LLM subset, topic-filtered server-side."
    )
    # a note-less hosted source falls back to the template naming it
    note_less = registry.hosted()[0]
    assert note_less.note == ""
    assert registry.feed.channel_description(note_less) == (
        "Items from Richmond Times-Dispatch, part of Jenny's source log."
    )


def write_registry(tmp_path, text):
    path = tmp_path / "sources.toml"
    path.write_text(text)
    return path


def test_duplicate_id_rejected(tmp_path):
    path = write_registry(tmp_path, """
[feed]
title = "t"
link = "https://example.com/"
[[sources]]
id = "a"
name = "A"
mode = "direct"
url = "https://example.com/a.xml"
[[sources]]
id = "a"
name = "A again"
mode = "direct"
url = "https://example.com/a2.xml"
""")
    with pytest.raises(RegistryError, match="duplicate id"):
        load(path)


def test_direct_with_strategy_rejected(tmp_path):
    path = write_registry(tmp_path, """
[feed]
title = "t"
link = "https://example.com/"
[[sources]]
id = "a"
name = "A"
mode = "direct"
url = "https://example.com/a.xml"
[sources.strategy]
name = "passthrough"
""")
    with pytest.raises(RegistryError, match="no strategy"):
        load(path)


def test_hosted_without_why_rejected(tmp_path):
    path = write_registry(tmp_path, """
[feed]
title = "t"
link = "https://example.com/"
[[sources]]
id = "a"
name = "A"
mode = "hosted"
url = "https://example.com/a.xml"
[sources.strategy]
name = "passthrough"
""")
    with pytest.raises(RegistryError, match="why"):
        load(path)


def test_unknown_strategy_rejected(tmp_path):
    path = write_registry(tmp_path, """
[feed]
title = "t"
link = "https://example.com/"
[[sources]]
id = "a"
name = "A"
mode = "hosted"
url = "https://example.com/a.xml"
why = "because"
[sources.strategy]
name = "scrape_html"
""")
    with pytest.raises(RegistryError, match="strategy must be one of"):
        load(path)


def test_the_strategy_module_validates_its_own_block(tmp_path):
    """The registry delegates; the strategy's message surfaces under the
    source's label."""
    path = write_registry(tmp_path, """
[feed]
title = "t"
link = "https://example.com/"
[[sources]]
id = "a"
name = "A"
mode = "hosted"
url = "https://example.com/a.xml"
why = "because"
[sources.strategy]
name = "passthrough"
terms = ["llm"]
""")
    with pytest.raises(RegistryError, match=r"sources\[a\].*unknown param"):
        load(path)


def test_hosted_strategy_blocks_validate_into_typed_configs(tmp_path):
    path = write_registry(tmp_path, """
[feed]
title = "t"
link = "https://example.com/"
[[sources]]
id = "a"
name = "A"
mode = "hosted"
url = "https://example.com/a.xml"
why = "because"
[sources.strategy]
name = "passthrough"
""")
    strategy = load(path).hosted()[0].strategy
    assert strategy.name == "passthrough"
    assert strategy.snapshot_filename == "upstream.xml"
    assert not hasattr(strategy, "params")
