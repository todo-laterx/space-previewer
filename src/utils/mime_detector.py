import os
import mimetypes

# Initialize mimetypes database
mimetypes.init()

# Custom mappings for modern file extensions
CUSTOM_MIME = {
    ".ts": "text/typescript",
    ".tsx": "text/typescript-jsx",
    ".js": "application/javascript",
    ".mjs": "application/javascript",
    ".cjs": "application/javascript",
    ".jsx": "text/jsx",
    ".vue": "text/vue",
    ".svelte": "text/svelte",
    ".rs": "text/rust",
    ".go": "text/go",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".mdown": "text/markdown",
    ".mkd": "text/markdown",
    ".mdx": "text/markdown",
    ".mmd": "text/vnd.mermaid",
    ".mermaid": "text/vnd.mermaid",
    ".yaml": "text/yaml",
    ".yml": "text/yaml",
    ".json": "application/json",
    ".jsonc": "application/json",
    ".toml": "text/toml",
    ".ini": "text/plain",
    ".conf": "text/plain",
    ".cfg": "text/plain",
    ".env": "text/plain",
    ".log": "text/plain",
    ".sql": "text/sql",
    ".sh": "application/x-sh",
    ".bash": "application/x-sh",
    ".zsh": "application/x-sh",
    ".fish": "application/x-sh",
    ".py": "text/x-python",
    ".rb": "text/x-ruby",
    ".php": "text/x-php",
    ".java": "text/x-java",
    ".kt": "text/x-kotlin",
    ".swift": "text/x-swift",
    ".c": "text/x-c",
    ".h": "text/x-c",
    ".cpp": "text/x-c++",
    ".hpp": "text/x-c++",
    ".cs": "text/x-csharp",
    ".lua": "text/x-lua",
    ".css": "text/css",
    ".scss": "text/x-scss",
    ".less": "text/x-less",
    ".html": "text/html",
    ".htm": "text/html",
    ".xml": "application/xml",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".svg": "image/svg+xml",
    ".heic": "image/heic",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}

def detect_mime_type(file_path: str) -> str:
    """Detect MIME type from file path."""
    if os.path.isdir(file_path):
        return "inode/directory"

    ext = os.path.splitext(file_path)[1].lower()
    if ext in CUSTOM_MIME:
        return CUSTOM_MIME[ext]

    mime, _ = mimetypes.guess_type(file_path)
    if mime:
        return mime

    # Fallback to checking binary vs text
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(1024)
            if b"\0" in chunk:
                return "application/octet-stream"
            return "text/plain"
    except Exception:
        return "application/octet-stream"
