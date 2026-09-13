"""Registry loading and validation — the whole repo derives from
sources.toml, so the loader's guarantees are load-bearing."""

import tomllib

import pytest

from feeds.registry import RegistryError, load


def test_real_registry_shape(registry):
    assert len(registry.sources) == 26
    assert len(registry.direct()) == 20
    assert len(registry.hosted()) == 6
    # Owner-blessed registry order (direct first, hosted last).
    assert registry.direct()[0].id == "hf-blog"
    assert registry.direct()[-1].id == "true-anon"
    assert registry.hosted()[0].id == "arxiv-cl"
    assert registry.hosted()[-1].id == "richmond-times-dispatch"


def test_ids_are_unique(registry):
    ids = [s.id for s in registry.sources]
    assert len(ids) == len(set(ids))


def test_hosted_sources_declare_why_and_strategy(registry):
    for source in registry.hosted():
        assert source.why, f"{source.id} missing why"
        assert source.strategy is not None, f"{source.id} missing strategy"
        assert source.strategy.name in ("topic_filter", "passthrough", "json_api")


def test_direct_sources_declare_no_strategy_and_no_why(registry):
    for source in registry.direct():
        assert source.strategy is None
        assert not source.why


def test_arxiv_term_lists_are_intact(registry):
    by_id = {s.id: s for s in registry.hosted()}
    assert len(by_id["arxiv-cl"].strategy.terms) == 42
    assert len(by_id["arxiv-se"].strategy.terms) == 28
    assert "sw bench" in by_id["arxiv-se"].strategy.terms


def test_feed_meta_and_channel_description(registry):
    assert registry.feed.title == "Jenny's source log"
    cl = registry.hosted()[0]
    assert registry.feed.channel_description(cl) == (
        "Kept for the LLM subset of the comp-ling firehose; "
        "topic-filtered server-side."
    )
    rva = [s for s in registry.hosted() if s.id == "reddit-rva"][0]
    assert registry.feed.channel_description(rva) == (
        "Items from Reddit r/rva, part of Jenny's source log."
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
name = "topic_filter"
terms = []
""")
    with pytest.raises(RegistryError, match=r"sources\[a\].*terms"):
        load(path)


def test_hosted_strategy_blocks_validate_into_typed_configs(registry):
    by_id = {s.id: s for s in registry.hosted()}
    assert by_id["arxiv-se"].strategy.terms[-1] == "llms"          # topic_filter
    assert by_id["reddit-rva"].strategy.name == "passthrough"       # passthrough
    hf = by_id["hf-daily-papers"].strategy                          # json_api
    assert hf.item == "$" and hf.link == "paper.id"
    assert not hasattr(hf, "params")
