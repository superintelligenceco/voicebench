"""Adapter registry.

Built-in adapters: ``mock``, ``websocket``, ``livekit`` (experimental, needs the
``livekit`` extra), and ``pipecat`` (experimental, needs the ``pipecat`` extra).
Load your own with ``module.path:ClassName``.
"""

from __future__ import annotations

import importlib
from typing import Any

from voicebench.adapters.base import (
    Adapter,
    AdapterError,
    AgentAudio,
    AgentClear,
    AgentEvent,
    SessionInfo,
    Transcript,
)

BUILTIN: dict[str, str] = {
    "mock": "voicebench.adapters.mock:MockAdapter",
    "websocket": "voicebench.adapters.websocket:WebSocketAdapter",
    "livekit": "voicebench.adapters.livekit:LiveKitAdapter",
    "pipecat": "voicebench.adapters.pipecat:PipecatAdapter",
}


def load_adapter_class(name: str) -> type[Adapter]:
    """Resolve a built-in name or a ``module:Class`` path to an adapter class."""
    target = BUILTIN.get(name, name)
    if ":" not in target:
        raise AdapterError(
            f"unknown adapter {name!r}; use one of {', '.join(BUILTIN)} or 'module.path:ClassName'"
        )
    module_name, _, cls_name = target.partition(":")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        extra = name if name in ("livekit", "pipecat") else None
        hint = f" (install it with: pip install 'voicebench[{extra}]')" if extra else ""
        raise AdapterError(f"cannot load adapter {name!r}: {exc}{hint}") from exc
    cls = getattr(module, cls_name, None)
    if not isinstance(cls, type) or not issubclass(cls, Adapter):
        raise AdapterError(f"{target} is not a voicebench Adapter subclass")
    return cls


def create_adapter(name: str, options: dict[str, Any] | None = None) -> Adapter:
    """Instantiate an adapter with keyword options."""
    cls = load_adapter_class(name)
    try:
        return cls(**(options or {}))
    except (TypeError, ValueError) as exc:
        raise AdapterError(f"adapter {name!r}: bad options: {exc}") from exc


__all__ = [
    "BUILTIN",
    "Adapter",
    "AdapterError",
    "AgentAudio",
    "AgentClear",
    "AgentEvent",
    "SessionInfo",
    "Transcript",
    "create_adapter",
    "load_adapter_class",
]
