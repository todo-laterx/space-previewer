"""Formatting for copying a line range out of a preview into a chat.

The payload is intentionally not translated: it is read by a chat agent or a
person pasting it into a conversation, not by the preview UI itself.
"""

from __future__ import annotations

import os

# Markdown fence language for common extensions. Unknown extensions get a
# plain fence so the block still pastes cleanly.
QUOTE_LANGUAGE_BY_EXT = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "jsx",
    ".mjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".json": "json",
    ".jsonc": "json",
    ".html": "html",
    ".htm": "html",
    ".xhtml": "html",
    ".css": "css",
    ".scss": "scss",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".fish": "fish",
    ".sql": "sql",
    ".md": "markdown",
    ".markdown": "markdown",
    ".mmd": "mermaid",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".xml": "xml",
    ".rs": "rust",
    ".go": "go",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".java": "java",
    ".kt": "kotlin",
    ".rb": "ruby",
    ".php": "php",
    ".lua": "lua",
    ".swift": "swift",
    ".cs": "csharp",
    ".vue": "vue",
    ".svelte": "svelte",
    ".txt": "",
}


def quote_language_for_path(file_path: str) -> str:
    """Return the Markdown fence language for a path, or ``""``."""
    return QUOTE_LANGUAGE_BY_EXT.get(os.path.splitext(file_path)[1].lower(), "")


def format_line_quote(
    file_path: str, first_line: int, last_line: int, text: str
) -> str:
    """Build a paste-ready quote: path, line range and a fenced code block.

    ``first_line`` and ``last_line`` are 1-based and inclusive.
    """
    if first_line == last_line:
        header = f"{file_path}:{first_line}"
    else:
        header = f"{file_path}:{first_line}-{last_line}"

    body = text if text.endswith("\n") else text + "\n"
    language = quote_language_for_path(file_path)
    return f"{header}\n\n```{language}\n{body}```\n"
