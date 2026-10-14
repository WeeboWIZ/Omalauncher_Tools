# Terminal Voice (終端播報)

Reads Codex replies or a tmux terminal aloud.

**Languages:** English (default), 中文, Español, Deutsch, Français, 日本語, 한국어. Pick one under **Details**.
A reply is read in its own language with a matching voice; a text too short to tell is read in the interface language.

- **Codex chat:** follows the latest local Codex conversation and can read a summary of each finished reply.
- **Terminal / Claude:** run `tmux new -A -s oma-voice`, start Claude, Codex or any CLI there, and tap **Play** to hear the pane.

## What Set up does

The tile shows a **Set up** button until its programs are installed. Tapping it:

- writes the voice and dictation programs held in `widget.owl` to `~/.local/share/oma-voice`, `~/.local/share/oma-speak` and `~/.local/bin` (`oma-voice`, `oma-send-dictation`, `speak`), readable by you only
- makes a Python environment in `~/.local/share/oma-voice/venv` and installs `edge-tts` from PyPI for online speech; without the network, speech stays offline (espeak-ng)
- stops an older voice service and dictation page so the new ones start

Nothing is downloaded and run apart from that pip package. The log is `~/.cache/oma-voice/setup.log`.
Terminal Voice and Dictation hold the same programs: setting up one sets up both.

## Background service

The tile starts a small voice service and asks for it every 30 s while it is on screen. The service writes its
state file only when something changes and looks for a missing Codex session or tmux pane every 15 s. It quits
after 10 minutes with the tile off screen and no Codex activity (never while speaking), and the tile starts it
again. **Idle pause** in the voice settings changes the time (1–1440 minutes) or turns the pause off, for tasks
that should be read aloud however long the screen has been off.

## Privacy

Online speech sends the text being read to Microsoft Edge TTS; choose **Voice: offline** to keep it local.
Browser speech recognition may use the browser provider's online service. The dictation page listens only on
`127.0.0.1:18763` and checks a random token before saving text. Terminal mode reads only the tmux session `oma-voice`.

Source, tests and the build script: https://github.com/WeeboWIZ/Omalauncher_Tools
