from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lfx.components._importing import import_mod
from .pgvector_write import PGVectorWriteComponent

if TYPE_CHECKING:
    from .pgvector import PGVectorStoreComponent, PGVectorWriteComponent
# lfx-bundles-shim
"""Compatibility shim: lfx.components.pgvector moved to lfx-bundles.

_dynamic_imports = {
    "PGVectorStoreComponent": "pgvector",
    "PGVectorWriteComponent": "pgvector_write",
}
This module re-points to the installed bundle distribution. It contains
no component implementations and no third-party dependencies, and is
removed once the deprecation window closes (M4).
"""

__all__ = [
    "PGVectorStoreComponent",
    "PGVectorWriteComponent",
]
import importlib
import sys


def __getattr__(attr_name: str) -> Any:
    """Lazily import pgvector components on attribute access."""
    if attr_name not in _dynamic_imports:
        msg = f"module '{__name__}' has no attribute '{attr_name}'"
        raise AttributeError(msg)
    try:
        result = import_mod(attr_name, _dynamic_imports[attr_name], __spec__.parent)
    except (ModuleNotFoundError, ImportError, AttributeError) as e:
        msg = f"Could not import '{attr_name}' from '{__name__}': {e}"
        raise AttributeError(msg) from e
    globals()[attr_name] = result
    return result


def __dir__() -> list[str]:
    return list(__all__)
