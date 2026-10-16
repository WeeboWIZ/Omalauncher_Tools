Add Trip View: pixel animations with Codex and Claude

Trip View adds seven animated pixel worlds with palettes, speed controls, pixel pets, optional clock and sound, and wallpaper capture. The full-screen generation panel lets users select Codex or Claude and request a new animation with one prompt. Selection persists; the selected CLI uses its configured default model.

The store edition includes English only. Language → Custom provides a prompt to add any other language, including Traditional Chinese, using the English pack as its template.

First use is a visible Set up action. The widget embeds its Python runtime, shader scenes, sprite data and MIT license as reviewable text. It writes these locally, checks all built-in shaders and generates sounds; it does not fetch or execute downloaded scripts. Runtime dependencies are declared in requires. Either agent CLI must be installed and signed in separately; built-in scenes do not need an agent.

Updates preserve generated scenes, custom language packs and settings. Replaced program files are backed up. The installer refuses linked developer installations and never writes another widget file.

Validation:
- 15 automated tests passed, including isolated clean install, repeat install, custom-data preservation, linked-directory protection, agent persistence, CLI invocation and shader validation.
- Store OWL compiled and passed the current store review checker.
- First-use tile/full-screen views and English generation controls rendered with owl-check and were visually inspected. Ready-state rendering uses local built-in scenes with an English-only UI fixture; installation itself was exercised in isolated temporary homes.
- The widget is below 256 KiB and the preview is below 300 KiB. The setup command is below 120 KiB to stay within Linux's argument length limit.
- No live paid agent request was made during validation; provider dispatch and missing-CLI errors were tested with mocks.

Review checker warnings:
- “uses eval”: the embedded AGSL validator rejects the shader token `eval` using a regular expression. It does not execute Python or shell eval.
- “writes raw disks or destroys data”: the star scene uses `dd` as a local floating-point distance variable. The setup command does not run the disk-writing `dd` command, mkfs or shred.

The store folder contains only widget.owl, README.md and preview.png. This is prepared locally; no PR has been opened.
