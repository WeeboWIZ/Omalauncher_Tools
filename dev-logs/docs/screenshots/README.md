# DEV LOGS store screenshots

Fixed English sample data, drawn by the Omalauncher renderer using the current theme. The tile is shown at its supported 3×4 size; detail views are 1080×2400. Screenshots contain no private log entries, real project names or captured diagnostics.

- [`dev-logs.png`](dev-logs.png): home tile; also used as the store's `preview.png`.
- [`logs.png`](logs.png): log entries browsed by day and filtered by project, stored as one Markdown file per month.
- [`files.png`](files.png): project folders and files in the default icon view.
- [`errors.png`](errors.png): Errors / Warnings / All filters, single-report copying and agent analysis.
- [`settings.png`](settings.png): English on the left, Traditional Chinese on the right, and the agent logging prompt.

Each PNG is below 300,000 bytes. [`manifest.json`](manifest.json) records sizes, dimensions and SHA-256 values. These are examples for review, not bundled log entries.

Regenerate from the repository root on an Omalauncher device with Pillow installed:

```sh
python dev-logs/tools/screenshots.py
```

Demo widgets have no live sources or executable action handlers. They are removed after capture. This script does not change the active DEV LOGS widget, user language, log entries or terminal diagnostics setting, and does not upload images.
