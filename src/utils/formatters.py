import datetime
import locale

from utils.i18n import _


def _format_number(value: float, digits: int) -> str:
    pattern = f"%.{digits}f"
    try:
        return locale.format_string(pattern, value, grouping=True)
    except (ValueError, TypeError):
        return pattern % value


def format_size(size_bytes: int) -> str:
    """Format bytes into a locale-aware human-readable size."""
    if size_bytes < 1024:
        return f"{size_bytes} {_('B')}"
    if size_bytes < 1024 * 1024:
        value, unit = size_bytes / 1024, _("KB")
    elif size_bytes < 1024 * 1024 * 1024:
        value, unit = size_bytes / (1024 * 1024), _("MB")
    else:
        value, unit = size_bytes / (1024 * 1024 * 1024), _("GB")
    return f"{_format_number(value, 1)} {unit}"


def format_date(timestamp: float) -> str:
    """Format a timestamp using a translatable date pattern."""
    dt = datetime.datetime.fromtimestamp(timestamp)
    return dt.strftime(_("%Y-%m-%d %H:%M"))
