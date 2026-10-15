# DEV LOGS

Local development logs, Markdown notes and Linux diagnostics for Omalauncher. English and Traditional Chinese; language selection and agent logging instructions are in the Settings tab; Refresh is at the top right.

## Features

- Browse logs by day; save them as one Markdown file per month with dated entries. Tap an entry to copy, edit or delete it. Filter by project: your agent tags each entry with its project.
- Browse your home directory as a grid of pixel folder and file icons (the default) or a list, search names and Markdown text, create/view/edit Markdown, and move deleted notes to recoverable local trash after confirmation.
- Collect local diagnostics, filter Errors / Warnings / All, expand a record and copy only that report. Keeps 500 collected records.
- Ask the launcher's default coding agent to explain an error and suggest a fix (read-only for Claude Code and Codex; in a terminal for others) and run the fix in a terminal.
- Copy a concise logging prompt for Codex or Claude. Your agent records meaningful changes, real verification results and unresolved problems; general replies are skipped.

DEV LOGS does not automatically capture conversations. It runs your local agent only when you tap Analyze or Fix, and sends it only the selected record. Agent logging requires a local agent that saves and follows the copied project instructions. The refresh time is a display update, not an automatically generated entry.

## What Set up writes

Tap **Set up** to install the programs embedded in `widget.owl`:

- `~/.local/bin/oma-devlogs`: the log and Markdown commands.
- `~/.local/bin/oma-devlogs-terminal`: optional terminal diagnostics entry point.
- `~/.local/share/oma-devlogs/system_errors.py`: local error collector.
- `~/.local/share/oma-devlogs/agent_help.py`: starts your agent for an analysis or a fix; results stay in `~/.local/share/oma-devlogs/agent/`.

Creates empty `~/oma-devlogs/notes`, `journal` and `logs/terminals` folders. Existing notes and log entries are preserved; replaced programs are backed up under `~/.local/share/oma-devlogs/install-backups`. Setup does not download a script, seed sample data, change agent rules, replace the system terminal, or touch any other folder or widget. Setup output is in `~/.cache/oma-devlogs/setup.log`.

Requires Python, bash, coreutils, less and micro, declared in the widget. **Update** installs new embedded helpers after a widget update.

Optional, not installed for you: `gum` for the terminal menu of `oma-devlogs open`, and `foot` for `oma-devlogs-terminal`.

## Data and diagnostics

Reads local widget/style errors, guest-shell stderr, existing terminal diagnostic logs and error contexts from the voice/dictation/pixel-console service logs. It does not read Android logcat, terminal screen contents or agent conversations. There is no background service: the widget looks for new diagnostics once a minute while its page is on screen, and writes to its database only when it finds some. Only the database is limited to 500 events, not the raw source logs.

Terminal logging is opt-in and needs `foot`: run `~/.local/bin/oma-devlogs-terminal` to start `/usr/bin/foot` with stderr and abnormal-exit logging. Other terminals are not automatically recorded. Collection times may differ from event times. Severity filters are based on diagnostic text and do not establish crash causes. Nothing is uploaded automatically; inspect copied reports before sharing.

Deleted Markdown is recoverable from `~/.local/share/oma-devlogs/trash/`, with original paths saved in matching JSON files.

Source, screenshots, tests and installation instructions: [DEV LOGS](https://github.com/WeeboWIZ/Omalauncher_Tools/tree/dev-logs/dev-logs).
