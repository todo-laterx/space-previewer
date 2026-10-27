"""Lightweight in-process viewer plugin registry.

Plugin directories are scanned in order, so the user directory overrides the
system directory (same file name wins, and later directories are consulted
first while matching). Each ``*.py`` file is imported exactly once per process
with a unique module name. Plugins run unsandboxed with the user's
permissions; set ``SPACE_PREVIEWER_PLUGINS=0`` to disable the registry
entirely.

Plugin module contract (``PLUGIN_API = 1``)::

    PLUGIN_API = 1                  # optional, must equal 1 when present
    content_types = ["text/x-foo"]  # optional list of MIME types
    extensions = [".foo"]           # optional list of extensions
    def supports(mime, ext): ...    # optional extra predicate

    class Viewer(Gtk.Widget):
        def __init__(self, file_path): ...

``find_plugin`` matches extensions case-insensitively first, then exact MIME
types, then MIME descendants through ``Gio.content_type_is_a`` when Gio is
available. ``supports`` is used as a final fallback for plugins that do not
declare static metadata. A failure in one plugin is logged and skipped; it
never prevents the remaining plugins (or the built-in dispatch) from running.
"""

from __future__ import annotations

import hashlib
import importlib.util
import logging
import os
import sys
import threading
from pathlib import Path
from types import ModuleType
from typing import Any

PLUGIN_API = 1

SYSTEM_PLUGIN_DIR = Path("/usr/share/space-previewer/plugins") / str(PLUGIN_API)
USER_PLUGIN_DIR = (
    Path.home() / ".local" / "share" / "space-previewer" / "plugins" / str(PLUGIN_API)
)

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_modules: list[ModuleType] | None = None

_gio: Any = None
_gio_checked = False


def plugins_enabled() -> bool:
    """Return ``False`` when the ``SPACE_PREVIEWER_PLUGINS=0`` kill switch is set."""
    value = os.environ.get("SPACE_PREVIEWER_PLUGINS", "")
    return value.strip().lower() != "0"


def _plugin_dirs() -> tuple[Path, Path]:
    """Return plugin directories in load order (system first, user last)."""
    return SYSTEM_PLUGIN_DIR, USER_PLUGIN_DIR


def _collect_plugin_paths() -> list[Path]:
    """Discover ``*.py`` files in load order.

    Files are sorted by name inside each directory. A later directory replaces
    an earlier file with the same name, and the replacement is re-appended at
    its new position so that reverse-order matching gives user plugins
    precedence.
    """
    selected: dict[str, Path] = {}
    for directory in _plugin_dirs():
        try:
            entries = sorted(directory.glob("*.py"), key=lambda path: path.name)
        except OSError:
            logger.debug("Cannot scan plugin directory %s", directory, exc_info=True)
            continue

        for path in entries:
            try:
                if not path.is_file():
                    continue
            except OSError:
                logger.debug("Cannot stat plugin candidate %s", path, exc_info=True)
                continue
            if path.name in selected:
                del selected[path.name]
            selected[path.name] = path

    return list(selected.values())


def _unique_module_name(path: Path) -> str:
    """Build a deterministic, collision-free import name for a plugin path."""
    digest = hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:16]
    return f"space_previewer_plugin_{PLUGIN_API}_{digest}"


def _drop_module(module_name: str) -> None:
    sys.modules.pop(module_name, None)


def _load_plugin_module(path: Path) -> ModuleType | None:
    """Import one plugin file, returning ``None`` when it is unusable."""
    try:
        module_name = _unique_module_name(path)
    except KeyboardInterrupt:
        raise
    except BaseException:
        logger.exception("Could not derive a module name for plugin %s", path)
        return None

    try:
        spec = importlib.util.spec_from_file_location(module_name, str(path))
    except KeyboardInterrupt:
        raise
    except BaseException:
        logger.exception("Could not build an import spec for plugin %s", path)
        return None

    if spec is None or spec.loader is None:
        logger.warning("Skipping plugin %s: no import loader available", path)
        return None

    try:
        module = importlib.util.module_from_spec(spec)
    except KeyboardInterrupt:
        raise
    except BaseException:
        logger.exception("Could not create a module for plugin %s", path)
        return None

    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except KeyboardInterrupt:
        _drop_module(module_name)
        raise
    except BaseException:
        _drop_module(module_name)
        logger.exception("Failed to import plugin %s", path)
        return None

    try:
        api_version = getattr(module, "PLUGIN_API", None)
    except KeyboardInterrupt:
        raise
    except BaseException:
        _drop_module(module_name)
        logger.exception("Could not read PLUGIN_API from plugin %s", path)
        return None

    if api_version is not None and api_version != PLUGIN_API:
        _drop_module(module_name)
        logger.warning(
            "Skipping plugin %s: PLUGIN_API %r is not %d",
            path,
            api_version,
            PLUGIN_API,
        )
        return None

    return module


def _ensure_loaded() -> list[ModuleType]:
    """Discover and import every plugin once, caching the result for the process."""
    global _modules

    with _lock:
        if _modules is not None:
            return _modules

        loaded: list[ModuleType] = []
        for path in _collect_plugin_paths():
            module = _load_plugin_module(path)
            if module is not None:
                loaded.append(module)

        _modules = loaded
        return _modules


def _get_gio() -> Any:
    """Return the Gio namespace, or ``None`` when introspection is unavailable."""
    global _gio, _gio_checked

    if not _gio_checked:
        _gio_checked = True
        try:
            import gi

            gi.require_version("Gio", "2.0")
            from gi.repository import Gio

            _gio = Gio
        except KeyboardInterrupt:
            raise
        except BaseException:
            logger.debug("Gio unavailable for MIME inheritance checks", exc_info=True)
            _gio = None

    return _gio


def _normalize_ext(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    normalized = value.strip().lower()
    if normalized.startswith("."):
        normalized = normalized[1:]
    return normalized


def _module_extensions(module: ModuleType) -> set[str]:
    raw = getattr(module, "extensions", None)
    if not isinstance(raw, (list, tuple, set, frozenset)):
        return set()
    return {normalized for item in raw if (normalized := _normalize_ext(item))}


def _module_content_types(module: ModuleType) -> set[str]:
    raw = getattr(module, "content_types", None)
    if not isinstance(raw, (list, tuple, set, frozenset)):
        return set()
    return {
        item.strip().lower()
        for item in raw
        if isinstance(item, str) and item.strip()
    }


def _matches_extension(module: ModuleType, ext: str) -> bool:
    return bool(ext) and ext in _module_extensions(module)


def _matches_mime(module: ModuleType, mime: str) -> bool:
    return bool(mime) and mime in _module_content_types(module)


def _matches_mime_descendant(module: ModuleType, mime: str) -> bool:
    if not mime:
        return False

    gio = _get_gio()
    if gio is None:
        return False

    for candidate in _module_content_types(module):
        if candidate == mime:
            continue
        try:
            if gio.content_type_is_a(mime, candidate):
                return True
        except Exception:
            logger.debug(
                "Gio.content_type_is_a(%r, %r) failed", mime, candidate, exc_info=True
            )
    return False


def _supports(module: ModuleType, mime: str, ext: str) -> bool:
    try:
        supports = getattr(module, "supports", None)
        if not callable(supports):
            return False
        return bool(supports(mime, ext))
    except KeyboardInterrupt:
        raise
    except BaseException:
        logger.exception(
            "Plugin %s raised in supports()",
            getattr(module, "__name__", repr(module)),
        )
        return False


def _instantiate(module: ModuleType, file_path: str) -> Any | None:
    try:
        viewer_class = getattr(module, "Viewer", None)
    except KeyboardInterrupt:
        raise
    except BaseException:
        logger.exception(
            "Could not read Viewer from plugin %s",
            getattr(module, "__name__", repr(module)),
        )
        return None

    if not callable(viewer_class):
        logger.warning(
            "Plugin %s does not define a Viewer class",
            getattr(module, "__name__", repr(module)),
        )
        return None

    try:
        viewer = viewer_class(file_path)
    except KeyboardInterrupt:
        raise
    except BaseException:
        logger.exception(
            "Plugin %s failed to create a viewer for %s",
            getattr(module, "__name__", repr(module)),
            file_path,
        )
        return None

    if viewer is None:
        logger.warning(
            "Plugin %s returned no viewer for %s",
            getattr(module, "__name__", repr(module)),
            file_path,
        )
    return viewer


def _detect_mime(file_path: str) -> str:
    try:
        from utils.mime_detector import detect_mime_type
    except KeyboardInterrupt:
        raise
    except BaseException:
        logger.debug("MIME detection is unavailable", exc_info=True)
        return ""

    try:
        return (detect_mime_type(file_path) or "").lower()
    except KeyboardInterrupt:
        raise
    except BaseException:
        logger.debug("MIME detection failed for %s", file_path, exc_info=True)
        return ""


def find_plugin(
    file_path: str, mime: str | None = None, ext: str | None = None
) -> Any | None:
    """Return a viewer instance from a matching plugin, or ``None``.

    ``mime`` and ``ext`` may be supplied by the caller (the dispatcher already
    has them). Missing values are derived from ``file_path``. Every plugin is
    isolated: import, match and construction errors are logged and skipped.
    """
    if not plugins_enabled():
        return None

    try:
        modules = _ensure_loaded()
    except KeyboardInterrupt:
        raise
    except BaseException:
        logger.exception("Plugin discovery failed")
        return None

    if not modules:
        return None

    if not ext:
        ext = os.path.splitext(file_path)[1]
    normalized_ext = _normalize_ext(ext)

    normalized_mime = (mime or "").strip().lower()
    if not normalized_mime:
        normalized_mime = _detect_mime(file_path)

    # User plugins come later in load order; matching in reverse gives them
    # precedence over system plugins with different file names.
    ordered = list(reversed(modules))

    match_passes = (
        ("extension", lambda module: _matches_extension(module, normalized_ext)),
        ("mime", lambda module: _matches_mime(module, normalized_mime)),
        (
            "descendant",
            lambda module: _matches_mime_descendant(module, normalized_mime),
        ),
    )
    for _pass_name, matches in match_passes:
        for module in ordered:
            try:
                matched = matches(module)
            except KeyboardInterrupt:
                raise
            except BaseException:
                logger.exception("Plugin matcher failed")
                continue
            if matched:
                viewer = _instantiate(module, file_path)
                if viewer is not None:
                    return viewer

    for module in ordered:
        if _supports(module, normalized_mime, normalized_ext):
            viewer = _instantiate(module, file_path)
            if viewer is not None:
                return viewer

    return None
