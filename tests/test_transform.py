"""Transform semantics: filters only — item identity never changes."""

from feeds.transform import filter_items

from conftest import make_item


def _items():
    return [
        make_item("1", title="Kitten pictures considered harmful", description="<p>no terms</p>"),
        make_item("2", title="LLM agents for code review", description="we study <b>rlhf</b>"),
        make_item("3", title="City council zoning fight", description="prompt: nothing here"),
    ]


def _topic_filter_source(registry, sid="arxiv-cl"):
    return [s for s in registry.hosted() if s.id == sid][0]


def test_topic_filter_keeps_title_and_description_matches(registry):
    kept = filter_items(_topic_filter_source(registry), _items())
    assert [i.guid for i in kept] == ["2", "3"]  # title "LLM agents…"; description "prompt: …"


def test_topic_filter_is_case_insensitive(registry):
    items = [make_item("x", title="IN-CONTEXT LEARNING AT SCALE")]
    kept = filter_items(_topic_filter_source(registry), items)
    assert [i.guid for i in kept] == ["x"]


def test_passthrough_is_identity(registry):
    rva = [s for s in registry.hosted() if s.id == "reddit-rva"][0]
    items = _items()
    assert filter_items(rva, items) is items


def test_json_api_is_identity_at_transform_time(registry):
    hf = [s for s in registry.hosted() if s.id == "hf-daily-papers"][0]
    items = _items()
    assert filter_items(hf, items) is items
