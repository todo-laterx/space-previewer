import logging
import os

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio

from utils.formatters import format_size
from utils.i18n import _

logger = logging.getLogger(__name__)


def _format_duration(duration_us: int) -> str:
    """Format a GStreamer duration in microseconds as mm:ss (or h:mm:ss)."""
    if duration_us is None or duration_us <= 0:
        return _("Unknown")
    total_seconds = int(duration_us // 1_000_000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


class MediaViewer(Gtk.Box):
    def __init__(self, file_path: str, is_audio: bool = False):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.file_path = file_path
        self.is_audio = is_audio

        self._status_callback = None
        self._stream = None
        self._stream_handlers: list[int] = []
        self._duration_us = 0
        try:
            self._file_size = os.path.getsize(file_path)
        except OSError:
            self._file_size = None

        self.center_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.center_box.set_hexpand(True)
        self.center_box.set_vexpand(True)
        self.center_box.set_halign(Gtk.Align.CENTER)
        self.center_box.set_valign(Gtk.Align.CENTER)
        self.append(self.center_box)

        file = Gio.File.new_for_path(os.path.abspath(file_path))
        self.video = Gtk.Video.new_for_file(file)
        self.video.set_autoplay(True)
        self.video.set_hexpand(True)
        self.video.set_vexpand(True)

        if is_audio:
            # Audio icon badge
            icon = Gtk.Image.new_from_icon_name("audio-x-generic")
            icon.set_pixel_size(96)
            icon.set_margin_top(32)
            self.center_box.append(icon)

            lbl_name = Gtk.Label(label=os.path.basename(file_path))
            lbl_name.add_css_class("title-3")
            self.center_box.append(lbl_name)

            self.video.set_size_request(-1, 48)
            self.center_box.append(self.video)
        else:
            self.center_box.append(self.video)

        # Bottom info bar
        self.info_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        self.info_bar.set_margin_start(16)
        self.info_bar.set_margin_end(16)
        self.info_bar.set_margin_top(8)
        self.info_bar.set_margin_bottom(8)

        self.lbl_info = Gtk.Label(label=self._size_text())
        self.lbl_info.add_css_class("dim-label")
        self.info_bar.append(self.lbl_info)

        self.append(self.info_bar)

        self._attach_stream()

    # ------------------------------------------------------------- playback

    def _get_stream(self):
        try:
            getter = getattr(self.video, "get_media_stream", None)
            if callable(getter):
                return getter()
        except Exception:
            logger.debug("Could not read the media stream", exc_info=True)
        return None

    def _attach_stream(self) -> None:
        if self._stream is not None:
            return
        stream = self._get_stream()
        if stream is None:
            return
        self._stream = stream
        for signal_name in ("notify::playing", "notify::duration", "notify::prepared"):
            try:
                handler_id = stream.connect(signal_name, self._on_stream_notify)
                self._stream_handlers.append(handler_id)
            except Exception:
                logger.debug(
                    "Could not connect %s on media stream", signal_name, exc_info=True
                )
        self._refresh_duration()

    def _refresh_duration(self) -> None:
        stream = self._stream
        if stream is None:
            return
        try:
            duration = stream.get_duration()
            self._duration_us = max(0, int(duration or 0))
        except Exception:
            logger.debug("Could not read media duration", exc_info=True)

    def _on_stream_notify(self, _stream, pspec) -> None:
        if pspec is not None and pspec.name == "duration":
            self._refresh_duration()
        self._notify_status_changed()

    def toggle_playback(self) -> None:
        """Toggle the media stream between playing and paused."""
        if self._stream is None:
            self._attach_stream()
        stream = self._stream
        if stream is None:
            return
        try:
            if stream.get_playing():
                stream.pause()
            else:
                stream.play()
        except Exception:
            logger.exception("Could not toggle media playback")
            return
        self._notify_status_changed()

    # ------------------------------------------------------------- contract

    def set_status_callback(self, callback) -> None:
        self._status_callback = callback

    def _notify_status_changed(self) -> None:
        callback = self._status_callback
        if callable(callback):
            try:
                callback()
            except Exception:
                logger.exception("Media status callback failed")

    def _size_text(self) -> str:
        if self._file_size is None:
            return _("Unknown")
        return format_size(self._file_size)

    def get_status_items(self) -> list[tuple[str, str]]:
        return [
            (_("Duration"), _format_duration(self._duration_us)),
            (_("Size"), self._size_text()),
        ]

    def get_desired_size(self, screen_w: int, screen_h: int) -> tuple[int, int]:
        if self.is_audio:
            return (min(720, int(screen_w * 0.70)), min(460, int(screen_h * 0.60)))
        return (
            min(1100, int(screen_w * 0.85)),
            min(780, int(screen_h * 0.82)),
        )

    def teardown(self) -> None:
        """Pause and release the GStreamer stream owned by this viewer."""
        stream = self._stream
        if stream is None:
            stream = self._get_stream()
            self._stream = stream

        if stream is not None:
            for handler_id in self._stream_handlers:
                try:
                    stream.disconnect(handler_id)
                except Exception:
                    logger.debug("Could not disconnect media handler", exc_info=True)
            try:
                stream.pause()
            except Exception:
                logger.debug("Could not pause media stream", exc_info=True)

        self._stream_handlers.clear()
        self._stream = None
        self._duration_us = 0
        self._status_callback = None

        try:
            self.video.set_media_stream(None)
        except Exception:
            logger.debug("Could not clear the media stream", exc_info=True)
