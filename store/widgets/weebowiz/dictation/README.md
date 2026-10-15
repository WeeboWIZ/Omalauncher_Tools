# Dictation (語音輸入)

Talk to Codex, Claude or any CLI instead of typing on the phone keyboard.

1. **Speak.** Tap the tile to open the dictation page in the browser and dictate; edit the text right there.
2. **Refine with Agent (optional).** The locally signed-in Claude Code (Haiku) or Codex CLI, whichever matches the current
   source with the other as fallback, turns rambling speech into a clear request, shown as a separate draft under your original so you can compare before anything is sent.
3. **Send.** Pick **Codex chat** or **Terminal / Claude** on the same page and send the original or the refined draft.
   Progress, success or failure shows next to the button; the tile shows the last result too.

Sending to a Codex chat uses Omalauncher's `codex queue`; a newer dictation replaces one still waiting instead of piling
up. Sending to a terminal types into the tmux session `oma-voice` and presses Enter. Pair it with **Terminal Voice** to
hear the reply. Chrome is recommended; the browser asks for the microphone.

## What Set up does

The tile shows a **Set up** button until its programs are installed. Tapping it:

- writes the voice and dictation programs held in `widget.owl` to `~/.local/share/oma-voice`, `~/.local/share/oma-speak` and `~/.local/bin` (`oma-voice`, `oma-send-dictation`, `oma-refine-dictation`, `speak`), readable by you only
- makes a Python environment in `~/.local/share/oma-voice/venv` and installs `edge-tts` from PyPI for online speech; without the network, speech stays offline (espeak-ng)
- stops an older voice service and dictation page so the new ones start

Nothing is downloaded and run apart from that pip package. The log is `~/.cache/oma-voice/setup.log`.
Terminal Voice and Dictation hold the same programs: setting up one sets up both. After an update, reopen the
dictation page from the tile so it gets the new access token.

## Privacy

Browser speech recognition may use the browser provider's online service. Refining sends the transcript to Claude or Codex and
never sends anything to the target by itself. The dictation page listens only on `127.0.0.1:18763` and checks a random
token before saving or sending text. Terminal mode reaches only the tmux session `oma-voice`.

Source, tests and the build script: https://github.com/WeeboWIZ/Omalauncher_Tools
