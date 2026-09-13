"""Strategies: one module per hosted source shape.

Each module exports a `NAME`, a `build(block)` that validates that source's
`[sources.strategy]` block into a typed strategy, and a strategy whose
`.headers()`, `.parse(bytes)`, and `.filter(items)` do the work.

Modules are discovered, not registered: drop a module here with a `NAME` and
a `build()` and `feeds.registry` resolves it. There is no table to update.
"""

from __future__ import annotations

import importlib
import pkgutil


def _modules() -> list:
    """Every module in this package that declares a `NAME`, by name order.

    Helpers (`base`, `rss`) declare no `NAME` and are skipped.
    """
    found = []
    for info in pkgutil.iter_modules(__path__):
        module = importlib.import_module(f"{__name__}.{info.name}")
        if getattr(module, "NAME", None):
            found.append(module)
    return sorted(found, key=lambda m: m.NAME)


def names() -> tuple[str, ...]:
    """Every declared strategy name."""
    return tuple(m.NAME for m in _modules())


def resolve(name: str):
    """The module for a strategy name, or None. The registry turns None into
    its loud-startup RegistryError."""
    return next((m for m in _modules() if m.NAME == name), None)
