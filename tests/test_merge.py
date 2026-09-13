"""The merge model's canonical cases (ticket 12): wholesale replace,
duplicate guids, age-out, ordering, and cap.

The failure policy lives one level up, in `publish.run_source`, and is
covered by `test_publish.py`."""

from datetime import timedelta

from feeds.merge import merge

from conftest import BUILT_AT, make_item


def test_ordering_pubdate_desc_tiebreak_guid_asc():
    upstream = [
        make_item("b", pub=BUILT_AT - timedelta(hours=1)),
        make_item("a", pub=BUILT_AT - timedelta(hours=1)),  # tie with "b"
        make_item("z", pub=BUILT_AT - timedelta(minutes=1)),
    ]
    merged = merge(upstream, [], BUILT_AT)
    assert [i.guid for i in merged] == ["z", "a", "b"]


def test_cap_100_keeps_newest():
    upstream = [
        make_item(str(n), pub=BUILT_AT - timedelta(hours=n)) for n in range(150)
    ]
    merged = merge(upstream, [], BUILT_AT)
    assert len(merged) == 100
    assert merged[0].guid == "0"          # newest
    assert merged[-1].guid == "99"        # cap cuts the oldest
    assert "149" not in [i.guid for i in merged]


def test_age_out_drops_items_older_than_30_days():
    old = make_item("old", pub=BUILT_AT - timedelta(days=31))
    edge = make_item("edge", pub=BUILT_AT - timedelta(days=29))
    undated = make_item("undated")
    merged = merge([], [old, edge, undated], BUILT_AT)
    assert [i.guid for i in merged] == ["edge", "undated"]


def test_duplicate_guid_keeps_first_occurrence():
    upstream = [make_item("same", title="fresh from upstream")]
    predecessor = [make_item("same", title="stale from predecessor")]
    merged = merge(upstream, predecessor, BUILT_AT)
    assert len(merged) == 1
    assert merged[0].title == "fresh from upstream"


def test_wholesale_replace_never_field_merge():
    upstream = [
        make_item("same", title="New title", description="New description",
                  link="https://example.com/new")
    ]
    predecessor = [
        make_item("same", title="Old title", description="Old description",
                  link="https://example.com/old")
    ]
    merged = merge(upstream, predecessor, BUILT_AT)
    assert len(merged) == 1
    assert merged[0].title == "New title"
    assert merged[0].description == "New description"
    assert merged[0].link == "https://example.com/new"


def test_missing_pubdate_sorts_last():
    upstream = [
        make_item("undated"),
        make_item("dated", pub=BUILT_AT - timedelta(days=2)),
    ]
    merged = merge(upstream, [], BUILT_AT)
    assert [i.guid for i in merged] == ["dated", "undated"]
