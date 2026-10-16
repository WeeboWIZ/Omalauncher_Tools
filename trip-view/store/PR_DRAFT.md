Add Trip View: pixel animations with Codex and Claude

Trip View adds five animated pixel worlds with palettes, speed controls, pixel pets, optional clock and sound, and wallpaper capture. The full-screen generation panel lets users select Codex or Claude and request a new animation with one prompt. Selection persists; the selected CLI uses its configured default model. Each agent button shows whether that CLI is installed and signed in; when it is not, the panel shows the one terminal command to fix it, with a copy button. Generation streams real progress from Claude (line by line) and step events from Codex, can be cancelled, stops an agent that goes silent for four minutes, and hands over to the other agent when one is signed out or out of quota. Agents run without tools and without saving a session.

The store edition includes English only. Language → Custom provides a prompt to add any other language, including Traditional Chinese, using the English pack as its template.

First use is a visible Set up action. The widget embeds its Python runtime, shader scenes, sprite data and MIT license as reviewable text. It writes these locally, checks all built-in shaders and generates sounds; it does not fetch or execute downloaded scripts. Runtime dependencies are declared in requires. Either agent CLI must be installed and signed in separately; built-in scenes do not need an agent.

Deleting a generated scene names it and asks for confirmation; built-in scenes cannot be deleted. Updates preserve generated scenes, custom language packs and settings. Replaced program files are backed up. The installer refuses linked developer installations and never writes another widget file.

Validation:
- 17 automated tests passed, including isolated clean install, repeat install, custom-data preservation, linked-directory protection, agent persistence, streaming CLI invocation through fake Claude and Codex CLIs, error explanations, stall detection and shader validation.
- Store OWL compiled and passed the current store review checker.
- First-use tile/full-screen views and English generation controls rendered with owl-check and were visually inspected. Ready-state rendering uses local built-in scenes with an English-only UI fixture; installation itself was exercised in isolated temporary homes.
- The widget is below 256 KiB and the preview is below 300 KiB. The setup command is below 120 KiB to stay within Linux's argument length limit.
- One live generation each with Claude Code and Codex went through the streaming path and passed the shader check; cancel, sign-in errors and fallback between agents were exercised with fake CLIs.

Review checker warnings:
- “uses eval”: the embedded AGSL validator rejects the shader token `eval` using a regular expression. It does not execute Python or shell eval.

The store folder contains only widget.owl, README.md and preview.png. This is prepared locally; no PR has been opened.
