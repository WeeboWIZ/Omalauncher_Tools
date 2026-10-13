# Dictation (語音輸入)

Dictate in the browser, then send the text to the Codex chat or tmux terminal that Terminal Voice is following.
Interface in English (default), 中文, Español, Deutsch, Français, 日本語 and 한국어; the page has a list for the language you
speak. Chrome is recommended; the browser asks for the microphone.

Sending to a Codex chat uses Omalauncher's `codex queue`; sending to a terminal types into the tmux session `oma-voice`.

## What Set up does

The tile shows a **Set up** button until its programs are installed. Tapping it:

- writes the voice and dictation programs held in `widget.owl` to `~/.local/share/oma-voice`, `~/.local/share/oma-speak` and `~/.local/bin` (`oma-voice`, `oma-send-dictation`, `speak`), readable by you only
- makes a Python environment in `~/.local/share/oma-voice/venv` and installs `edge-tts` from PyPI for online speech; without the network, speech stays offline (espeak-ng)
- stops an older voice service and dictation page so the new ones start

Nothing is downloaded and run apart from that pip package. The log is `~/.cache/oma-voice/setup.log`.
Terminal Voice and Dictation hold the same programs: setting up one sets up both.

## Privacy

Online speech sends the text being read to Microsoft Edge TTS; choose **Voice: offline** to keep it local.
Browser speech recognition may use the browser provider's online service. The dictation page listens only on
`127.0.0.1:18763` and checks a random token before saving text. Terminal mode reads only the tmux session `oma-voice`.

Source, tests and the build script: https://github.com/WeeboWIZ/Omalauncher_Tools
