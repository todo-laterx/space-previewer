# Security Policy

## Supported versions

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |

## Reporting a vulnerability

Do not open a public issue for a vulnerability. Report it privately so a fix can be prepared
before details are public.

- Preferred: use the repository's private vulnerability reporting form (the Security tab).
- If private reporting is unavailable, contact the maintainer through the contact details on
  the repository profile.

Please include the affected version (see `VERSION`), the viewer and file type involved, the
exact steps to reproduce, a minimal file or command that triggers the issue, and the observed
impact. State clearly whether the input came from an untrusted source.

## Threat model

Space Previewer opens files that the user did not necessarily create. Every previewed file is
treated as untrusted input. The relevant threats are:

- A malformed document that crashes the daemon or exhausts memory.
- A parser bug that leads to arbitrary code execution.
- Path traversal through archive or Office entries.
- Unexpected network requests that leak file content or usage information.

### Untrusted files and input caps

All parsers are expected to enforce the limits below. The limits are part of the contract and
must be stated in code as well as in this file.

| Input | Limit |
| --- | --- |
| Text | 5 MB read, highlight only the first 1 MB |
| Markdown | 2 MB |
| Office (zip inside docx/xlsx/pptx) | 20 MB per entry, 100 MB total, 2000 entries, reject DOCTYPE |
| Archive | 5000 entries, 200 MB uncompressed, reject encrypted entries |
| PDF | 100 pages by default |
| Image | 50 MP before scaling |
| HTML | remote blocked, file access from file URLs disabled |

Office viewers use the standard-library `zipfile` and `ElementTree` modules. Archive listings
do not extract files to disk.

### Network access

No network request is made without an explicit user action. The application does not contain
telemetry, analytics, crash reporting, or update checks.

Mermaid diagrams render locally. The remote mermaid.ink renderer is opt-in through
`SPACE_PREVIEWER_ALLOW_NETWORK=1` and is never contacted by default; when enabled, the
diagram source is sent to mermaid.ink to produce an image.

### HTML preview

Remote content is blocked by default. When an HTML document is previewed, HTTP and HTTPS
requests are not loaded automatically, `file://` pages cannot read unrelated local files, and
links open in the user's default browser instead of inside the preview.

### Plugins

Plugins run in-process with the full permissions of the user. There is no sandbox. A plugin
can read, modify, or delete anything the user can, and it can make network requests on its
own. Only install plugins from sources you trust. Setting `SPACE_PREVIEWER_PLUGINS=0`
disables plugin loading.

### Out of scope

- Problems caused by a plugin or a modified build that the user installed deliberately.
- Clients other than the Nautilus previewer service impersonating or misusing the D-Bus
  interface with the user's own session permissions.
- Denial of service from files larger than the limits above when a reader deliberately
  bypasses those limits.

## Dependencies

Runtime parsing and rendering comes from GTK4, Libadwaita, Poppler, GdkPixbuf, GStreamer,
Pygments, markdown-it-py, and, where installed, WebKitGTK. Security fixes for those
components are delivered by the distribution's package updates.
