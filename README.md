# weread-canvas-exporter

Experimental CLI for exporting visible WeRead web reader content through
Playwright-driven Canvas text capture.

It only captures content that the logged-in user can read in the WeRead web
reader. It does not bypass login, purchase, membership, or platform limits.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .[dev]
.\.venv\Scripts\python.exe -m playwright install chromium
```

## Commands

```powershell
weread-export export <reader-url-or-book-id>
weread-export resume <book-id>
weread-export inspect <book-id>
weread-export clean-locks
```

Useful options:

- `--profile <path>`: Playwright persistent profile, default `data/browser-profile`.
- `--output <path>`: output root, default `output`.
- `--headless`: run Chromium without a visible window.
- `--max-pages <n>`: limit page capture for debugging.
- `--overwrite`: remove old output for the target book before exporting.

## Output

Each book writes to `output/<book-id>/`:

- `manifest.json`: book metadata, catalog, status, and checkpoint summary.
- `pages/*.json`: page-level capture checkpoints.
- `chapters/*.md`: reconstructed chapter Markdown.
- `<title>.md`: merged book Markdown, written only after a complete export.

## Notes

The first run may require scanning the WeRead QR code in the Playwright
Chromium window. Login state is kept in the configured profile path.

