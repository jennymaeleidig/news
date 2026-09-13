"""The publish workflow's shape is a decision (ticket 08) — pin it."""

from pathlib import Path

import yaml

WORKFLOW = Path(".github/workflows/publish-feeds.yml")


def load():
    return yaml.safe_load(WORKFLOW.read_text())


def test_cron_is_hourly_at_23():
    wf = load()
    assert wf[True]["schedule"] == [{"cron": "23 * * * *"}]


def test_concurrency_queues_instead_of_cancelling():
    wf = load()
    concurrency = wf["concurrency"]
    assert concurrency["group"] == "publish-feeds"
    assert concurrency["cancel-in-progress"] is False


def test_permissions_are_pages_only():
    wf = load()
    assert wf["permissions"] == {"pages": "write", "id-token": "write"}


def test_tests_run_before_pages_upload():
    wf = load()
    steps = wf["jobs"]["publish"]["steps"]
    names = [s.get("name") or s.get("uses") for s in steps]
    assert names.index("Test") < names.index("actions/upload-pages-artifact@v3")


def test_push_trigger_paths_are_narrow():
    wf = load()
    paths = wf[True]["push"]["paths"]
    assert "sources.toml" in paths
    assert "feeds/**" in paths


def test_no_secrets_are_used():
    text = WORKFLOW.read_text()
    assert "secrets." not in text
    assert "OPENROUTER" not in text and "RESEND" not in text


def test_runtime_limits():
    wf = load()
    job = wf["jobs"]["publish"]
    assert job["timeout-minutes"] == 10
    assert job["environment"]["name"] == "github-pages"
