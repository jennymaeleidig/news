# Coding standards

## Tests are committed and run in CI

`tests/` is part of the repo and runs in `publish-feeds.yml` before any
Pages publication — a red test blocks it. The suite is fully offline:
no test ever touches the network; fetch-level behavior is exercised with
fakes and golden files.

Feed fixtures live at `tests/fixtures/<source-id>/` (an upstream snapshot
plus the expected emitted `expected.xml`). They are refreshed manually,
with human diff review, so a hostile upstream can never silently rewrite
what we consider correct:

    PYTHONPATH=. python scripts/refresh_fixture.py <source-id>   # live fetch
    git diff tests/fixtures/                                     # review, then commit

Everything else follows the normal rules: code, configs, docs, and the
registry all get committed.
