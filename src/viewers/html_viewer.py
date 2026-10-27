"""Sandboxed local HTML renderer with opt-in remote content.

Remote navigation is blocked by default and links are handed to the default
browser. WebKitGTK 6.0 is optional: when the introspection namespace is
missing, the viewer falls back to the plain text viewer and a one-line notice
instead of raising.
"""

from __future__ import annotations

import html as html_module
import logging
import os
import re
import urllib.parse
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")

from gi.repository import Gio, GLib, Gtk, Pango

from utils.formatters import format_size
from utils.i18n import _

try:
    from .base import teardown_viewer
except ImportError:  # Direct import when ``src`` is on sys.path.
    from base import teardown_viewer

logger = logging.getLogger(__name__)

MAX_HTML_BYTES = 5 * 1024 * 1024

# Local pages may use their own scripts and assets, but cannot reach the
# network. This is the only reliable way to block subresources with WebKitGTK
# 6.0: decide-policy only sees navigations, not <img>/<link>/<script> loads.
LOCAL_POLICY = (
    "default-src 'none'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self' data:; "
    "media-src 'self' data:; "
    "connect-src 'none'; "
    "frame-src 'none'; "
    "object-src 'none'; "
    "base-uri 'self'"
)

HAS_WEBKIT = False
WebKit = None

try:
    gi.require_version("WebKit", "6.0")
    from gi.repository import WebKit  # type: ignore[attr-defined]

    HAS_WEBKIT = True
except KeyboardInterrupt:
    raise
except BaseException:
    # WebKit is optional; do not fail module import when it is absent.
    WebKit = None
    HAS_WEBKIT = False
    logger.debug("WebKitGTK 6.0 is not available; HTML viewer will fall back")


class HtmlViewer(Gtk.Box):
    """Local HTML preview with remote content blocked by default."""

    _ALLOWED_SCHEMES = frozenset({"file", "data", "about"})
    _REMOTE_SCHEMES = frozenset({"http", "https"})

    def __init__(self, file_path: str) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        self.file_path = file_path
        self._remote_allowed = False
        self._remote_blocked = False
        self._current_uri = ""
        self._web_view = None
        self._fallback_viewer = None
        self._search_state_callback = None

        self._build_controls()
        self._build_notice()
        self._build_content()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_controls(self) -> None:
        """Build the header controls; the window hosts them."""
        self._remote_toggle = Gtk.ToggleButton()
        self._remote_toggle.set_icon_name("network-wired-symbolic")
        self._remote_toggle.add_css_class("flat")
        self._remote_toggle.set_active(False)
        self._remote_toggle.set_tooltip_text(
            _("Allow remote content in this preview")
        )
        self._remote_toggle.update_property(
            [Gtk.AccessibleProperty.LABEL], [_("Allow remote content")]
        )
        self._remote_toggle.connect("toggled", self._on_remote_toggled)

        self._open_button = Gtk.Button.new_from_icon_name("web-browser-symbolic")
        self._open_button.add_css_class("flat")
        self._open_button.set_tooltip_text(
            _("Open this file in the default browser")
        )
        self._open_button.update_property(
            [Gtk.AccessibleProperty.LABEL], [_("Open in browser")]
        )
        self._open_button.connect("clicked", self._on_open_clicked)

    def get_header_controls(self) -> list:
        if self._web_view is None and self._fallback_viewer is not None:
            getter = getattr(self._fallback_viewer, "get_header_controls", None)
            if callable(getter):
                try:
                    return list(getter() or [])[:3]
                except Exception:
                    logger.exception("Fallback header controls failed")
        return [self._remote_toggle, self._open_button]

    def get_status_items(self) -> list[tuple[str, str]]:
        if self._web_view is None and self._fallback_viewer is not None:
            getter = getattr(self._fallback_viewer, "get_status_items", None)
            if callable(getter):
                try:
                    return list(getter() or [])
                except Exception:
                    logger.exception("Fallback status items failed")

        items: list[tuple[str, str]] = []
        try:
            items.append((_("Size"), format_size(os.path.getsize(self.file_path))))
        except OSError:
            pass
        if self._remote_blocked:
            items.append((_("Remote"), _("Blocked")))
        return items

    def toggle_search(self) -> None:
        if self._fallback_viewer is not None and hasattr(self._fallback_viewer, "toggle_search"):
            self._fallback_viewer.toggle_search()

    def close_search(self) -> None:
        if self._fallback_viewer is not None and hasattr(self._fallback_viewer, "close_search"):
            self._fallback_viewer.close_search()

    def is_search_open(self) -> bool:
        if self._fallback_viewer is not None and hasattr(self._fallback_viewer, "is_search_open"):
            return bool(self._fallback_viewer.is_search_open())
        return False

    def get_search_widget(self):
        if self._fallback_viewer is not None and hasattr(self._fallback_viewer, "get_search_widget"):
            return self._fallback_viewer.get_search_widget()
        return None

    def set_search_state_callback(self, callback) -> None:
        self._search_state_callback = callback
        if self._fallback_viewer is not None and hasattr(
            self._fallback_viewer, "set_search_state_callback"
        ):
            self._fallback_viewer.set_search_state_callback(callback)

    def _build_notice(self) -> None:
        """Build the one-line notice/infobar shown above the content."""
        self._notice_label = Gtk.Label(label="")
        self._notice_label.add_css_class("caption")
        self._notice_label.add_css_class("dim-label")
        self._notice_label.set_xalign(0.0)
        self._notice_label.set_ellipsize(Pango.EllipsizeMode.END)
        self._notice_label.set_margin_start(12)
        self._notice_label.set_margin_end(12)
        self._notice_label.set_margin_top(2)
        self._notice_label.set_margin_bottom(2)
        self._notice_label.set_visible(False)
        self.append(self._notice_label)

    def _build_content(self) -> None:
        if HAS_WEBKIT and self._within_size_limit():
            try:
                web_view = self._create_web_view()
            except KeyboardInterrupt:
                raise
            except BaseException:
                logger.exception("Could not create the WebKit view")
                web_view = None

            if web_view is not None:
                self._web_view = web_view
                web_view.set_hexpand(True)
                web_view.set_vexpand(True)
                self.append(web_view)
                self._load_current()
                return

        # Fallback path: WebKit missing, unusable, or the file is too large.
        self._remote_toggle.set_visible(False)
        if HAS_WEBKIT:
            self._build_fallback(
                _("This HTML file is too large to preview; showing the source instead.")
            )
        else:
            self._build_fallback()

    def _within_size_limit(self) -> bool:
        try:
            return os.path.getsize(self.file_path) <= MAX_HTML_BYTES
        except OSError:
            return True

    def _build_fallback(self, notice: str | None = None) -> None:
        self._show_notice(notice or _("WebKit is not available; showing the source instead."))

        text_viewer_class = None
        try:
            from .text_viewer import TextViewer

            text_viewer_class = TextViewer
        except KeyboardInterrupt:
            raise
        except BaseException:
            try:
                from text_viewer import TextViewer

                text_viewer_class = TextViewer
            except KeyboardInterrupt:
                raise
            except BaseException:
                logger.exception("Could not import the text viewer fallback")

        if text_viewer_class is not None:
            try:
                self._fallback_viewer = text_viewer_class(self.file_path)
            except KeyboardInterrupt:
                raise
            except BaseException:
                logger.exception("Could not build the text viewer fallback")

        if self._fallback_viewer is not None:
            if self._search_state_callback is not None and hasattr(
                self._fallback_viewer, "set_search_state_callback"
            ):
                self._fallback_viewer.set_search_state_callback(
                    self._search_state_callback
                )
            self._fallback_viewer.set_hexpand(True)
            self._fallback_viewer.set_vexpand(True)
            self.append(self._fallback_viewer)
            return

        error_label = Gtk.Label(label=_("Could not show this file."))
        error_label.add_css_class("dim-label")
        error_label.set_vexpand(True)
        self.append(error_label)

    # ------------------------------------------------------------------
    # WebKit setup
    # ------------------------------------------------------------------

    def _create_web_context(self):
        """Create an ephemeral context, falling back to a cache under XDG cache."""
        new_ephemeral = getattr(WebKit.WebContext, "new_ephemeral", None)
        if callable(new_ephemeral):
            try:
                return new_ephemeral()
            except KeyboardInterrupt:
                raise
            except BaseException:
                logger.exception("Could not create an ephemeral WebKit context")

        try:
            context = WebKit.WebContext.get_default()
        except KeyboardInterrupt:
            raise
        except BaseException:
            logger.exception("Could not get the default WebKit context")
            return None

        try:
            manager = context.get_website_data_manager()
            cache_root = (
                Path(GLib.get_user_cache_dir()) / "space-previewer" / "webkit"
            )
            data_root = cache_root / "data"
            cache_root.mkdir(parents=True, exist_ok=True)
            data_root.mkdir(parents=True, exist_ok=True)
            manager.set_base_cache_directory(str(cache_root))
            manager.set_base_data_directory(str(data_root))
        except KeyboardInterrupt:
            raise
        except BaseException:
            logger.warning(
                "Could not configure the WebKit cache directory", exc_info=True
            )

        return context

    def _create_web_view(self):
        context = self._create_web_context()

        web_view = None
        if context is not None:
            new_with_context = getattr(WebKit.WebView, "new_with_context", None)
            if callable(new_with_context):
                try:
                    web_view = new_with_context(context)
                except KeyboardInterrupt:
                    raise
                except BaseException:
                    logger.exception("WebKit.WebView.new_with_context failed")

            if web_view is None:
                try:
                    web_view = WebKit.WebView(web_context=context)
                except KeyboardInterrupt:
                    raise
                except BaseException:
                    logger.exception("WebKit.WebView(web_context=...) failed")

        if web_view is None:
            web_view = WebKit.WebView()

        self._configure_settings(web_view)
        web_view.connect("decide-policy", self._on_decide_policy)
        return web_view

    def _configure_settings(self, web_view) -> None:
        try:
            settings = web_view.get_settings()
        except KeyboardInterrupt:
            raise
        except BaseException:
            logger.exception("Could not read WebKit settings")
            return

        for setter_name, value in (
            ("set_allow_file_access_from_file_urls", False),
            ("set_allow_universal_access_from_file_urls", False),
            ("set_javascript_can_open_windows_automatically", False),
            ("set_enable_developer_extras", False),
        ):
            setter = getattr(settings, setter_name, None)
            if not callable(setter):
                logger.debug("WebKit setting %s is unavailable", setter_name)
                continue
            try:
                setter(value)
            except KeyboardInterrupt:
                raise
            except BaseException:
                logger.warning(
                    "Could not apply WebKit setting %s", setter_name, exc_info=True
                )

    # ------------------------------------------------------------------
    # Loading and policy
    # ------------------------------------------------------------------

    def _file_uri(self) -> str:
        """Return an escaped URI for the previewed file."""
        if not self.file_path:
            return ""
        if "://" in self.file_path:
            return self.file_path
        try:
            return GLib.filename_to_uri(os.path.abspath(self.file_path), None)
        except KeyboardInterrupt:
            raise
        except BaseException:
            logger.exception("Could not build a URI for %s", self.file_path)
            return ""

    def _load_current(self) -> None:
        if self._web_view is None:
            return

        uri = self._file_uri()
        self._current_uri = uri
        if not uri:
            self._show_notice(_("Could not build a URI for this file."))
            return

        scheme = self._scheme_of(uri)

        if scheme in self._REMOTE_SCHEMES:
            if not self._remote_allowed:
                self._show_remote_blocked()
                return
            self._show_notice("")
            self._web_view.load_uri(uri)
            return

        if self._remote_allowed or scheme not in self._ALLOWED_SCHEMES:
            self._show_notice("")
            self._web_view.load_uri(uri)
            return

        # Local document, remote blocked: inject CSP and a base URI so relative
        # assets still resolve while http(s) subresources are refused.
        if not self._load_local_with_policy(uri):
            self._show_notice(_("Could not load this HTML file."))

    def _load_local_with_policy(self, uri: str) -> bool:
        path = Gio.File.new_for_uri(uri).get_path()
        if not path:
            return False

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                content = handle.read(MAX_HTML_BYTES + 1)
        except OSError:
            logger.exception("Could not read %s", path)
            return False

        if len(content) > MAX_HTML_BYTES:
            return False

        base_uri = GLib.filename_to_uri(os.path.dirname(path), None) + "/"
        document = self._inject_policy(content, base_uri)
        try:
            self._web_view.load_html(document, base_uri)
        except KeyboardInterrupt:
            raise
        except BaseException:
            logger.exception("Could not load the local HTML document")
            return False

        self._show_notice("")
        return True

    @staticmethod
    def _inject_policy(content: str, base_uri: str) -> str:
        meta = (
            '<meta http-equiv="Content-Security-Policy" content="'
            + LOCAL_POLICY
            + '">'
            + '<base href="'
            + html_module.escape(base_uri, quote=True)
            + '">'
        )

        head_open = re.search(r"<head\b[^>]*>", content, flags=re.IGNORECASE)
        if head_open:
            return content[: head_open.end()] + meta + content[head_open.end():]

        html_open = re.search(r"<html\b[^>]*>", content, flags=re.IGNORECASE)
        if html_open:
            return (
                content[: html_open.end()]
                + "<head>"
                + meta
                + "</head>"
                + content[html_open.end():]
            )

        return "<head>" + meta + "</head>" + content

    @staticmethod
    def _scheme_of(uri: str) -> str:
        try:
            return urllib.parse.urlparse(uri).scheme.lower()
        except (ValueError, TypeError):
            return ""

    def _on_decide_policy(self, _web_view, decision, decision_type) -> bool:
        """Apply the remote-content and external-link policy."""
        try:
            navigation_action = getattr(
                WebKit.PolicyDecisionType, "NAVIGATION_ACTION", None
            )
            new_window_action = getattr(
                WebKit.PolicyDecisionType, "NEW_WINDOW_ACTION", None
            )
            if decision_type not in (navigation_action, new_window_action):
                return False

            action = decision.get_navigation_action()
            if action is None:
                return False

            request = action.get_request()
            uri = request.get_uri() if request is not None else ""
            if not uri:
                return False

            scheme = self._scheme_of(uri)
            navigation_type = action.get_navigation_type()
            is_new_window = decision_type == new_window_action
            link_clicked = getattr(WebKit.NavigationType, "LINK_CLICKED", None)
            is_link = link_clicked is not None and navigation_type == link_clicked

            if scheme in self._REMOTE_SCHEMES:
                if is_new_window or is_link:
                    # Links are never followed inside the preview.
                    if not self._remote_allowed:
                        self._show_remote_blocked()
                    self._launch_external(uri)
                    decision.ignore()
                    return True

                if not self._remote_allowed:
                    self._show_remote_blocked()
                    decision.ignore()
                    return True

                # Explicitly enabled non-link navigation (redirect/meta refresh).
                return False

            if is_new_window:
                decision.ignore()
                return True

            if scheme in self._ALLOWED_SCHEMES or scheme == "":
                return False

            # Unknown or unsafe scheme: never navigate.
            decision.ignore()
            return True
        except KeyboardInterrupt:
            raise
        except BaseException:
            logger.exception("HTML navigation policy failed")
            try:
                decision.ignore()
            except KeyboardInterrupt:
                raise
            except BaseException:
                logger.debug("Could not deny the policy decision", exc_info=True)
            return True

    def _launch_external(self, uri: str) -> None:
        try:
            Gio.AppInfo.launch_default_for_uri(uri, None)
        except KeyboardInterrupt:
            raise
        except BaseException:
            logger.exception("Could not open %s in the default browser", uri)
            self._show_notice(
                _("Could not open this link in the default browser.")
            )

    # ------------------------------------------------------------------
    # User actions
    # ------------------------------------------------------------------

    def _on_open_clicked(self, _button) -> None:
        uri = self._file_uri()
        if uri:
            self._launch_external(uri)

    def _on_remote_toggled(self, button) -> None:
        self._remote_allowed = bool(button.get_active())

        if self._remote_allowed and self._remote_blocked:
            self._show_notice("")

        if self._web_view is None:
            return

        # Reload from policy: local documents load through CSP injection, and
        # opting in switches back to a normal URI load.
        try:
            self._load_current()
        except KeyboardInterrupt:
            raise
        except BaseException:
            logger.exception("Could not reload the WebKit view")

    # ------------------------------------------------------------------
    # Notice and lifecycle
    # ------------------------------------------------------------------

    def _show_notice(self, text: str, remote_blocked: bool = False) -> None:
        self._notice_label.set_text(text or "")
        self._notice_label.set_visible(bool(text))
        self._remote_blocked = remote_blocked

    def _show_remote_blocked(self) -> None:
        self._show_notice(_("Remote content blocked"), remote_blocked=True)

    def get_desired_size(self, screen_w: int, screen_h: int) -> tuple[int, int]:
        return (
            min(1100, int(screen_w * 0.85)),
            min(900, int(screen_h * 0.82)),
        )

    def teardown(self) -> None:
        """Stop loading, detach the WebView and clean up the text fallback."""
        web_view = self._web_view
        self._web_view = None
        self._current_uri = ""

        if web_view is not None:
            try:
                web_view.stop_loading()
            except KeyboardInterrupt:
                raise
            except BaseException:
                logger.exception("Could not stop the WebKit load")

            try:
                parent = web_view.get_parent()
                if parent is not None:
                    parent.remove(web_view)
            except KeyboardInterrupt:
                raise
            except BaseException:
                logger.exception("Could not detach the WebKit view")

        fallback = self._fallback_viewer
        self._fallback_viewer = None
        if fallback is not None:
            teardown_viewer(fallback)
