Add weebowiz/trip-view: animated pixel scenes, and new ones your agent paints

## Summary
- **Scenes:** five hand-made pixel animations (Neon Ramen, Kaiju Tokyo, Void Space, Acid Forest, Zion Hub), five palettes each, a pixel pet, optional pixel clock and 8-bit sounds. Any size from 2×2 to a full page.
- **Full-screen page:** the scene fills the screen; cards with previews, palettes and speed. **Hide** leaves only the scene; a tap brings the controls back.
- **Agent:** describe a mood in one sentence and Codex or Claude writes a new scene. Each button shows whether that CLI is installed and signed in, and its model; if not, the one terminal command to fix it, with a copy button. Progress is live (Claude line by line, Codex by step), can be cancelled, and a silent agent is stopped after four minutes; if one agent is signed out or out of quota, the other takes over.
- **Manage:** a small link under a generated scene's name opens **Edit** (the agent changes only what you describe; the old version is kept) and **Delete** (names the scene and asks to confirm).
- **Wallpaper:** freeze any moment as the launcher background; every one is kept in `~/Pictures/pixbg`.
- English only; **Language → Custom** gives a prompt that adds any language.

## Notes for review
- **Set up** writes the Python program, scenes and English pack held in `widget.owl` to `~/.local/share/pixbg`, and `pixbg`/`tripview` to `~/.local/bin`. Nothing is downloaded. Updates keep generated scenes and settings; replaced files are backed up first.
- Every shader, built-in or generated, passes an offline check before it reaches the phone: glslangValidator, AGSL rules and a per-pixel GPU budget. A generated scene that fails goes back to the agent, at most three times.
- Agents run without tools (`claude --tools ""`, `codex -s read-only`), without saving a session, in their own temp folder, with the user's own account. `claude` and `codex` are optional and not in `requires`; built-in scenes need neither.
- **Set wallpaper** changes only the `background` line of the launcher's `style.toml`.
- Review note "uses eval": the AGSL checker rejects the shader token `eval` with a regular expression; nothing is evaluated.
- `widget.owl` is 161 KB; the setup command is 114 KB, under Linux's argument limit; `preview.png` is 47 KB.

## Validation
- `owl.jar review` passes. 19 unit tests cover setup in temporary homes, streaming with fake Claude and Codex CLIs, error messages, stall detection, scene editing and the shader check.
- One live generation each with Claude Code and Codex passed the check and appeared on the phone.
- On the phone: the agent buttons with models, the fix-command panel, manage / edit / delete-confirm, hide mode, and the tile.
