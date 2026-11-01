# 🤖 MarkPrompt CLI

🌐 **English** | [简体中文](cli.zh-CN.md)

> Run these commands from the repository root.

Version: `2026.11.01-i18n1` · JSON protocol version: `1`

Run independently without creating a window or loading Tk, Pillow, or tkinterdnd2. The CLI and GUI share the command catalog, actions, document sessions, search, state, and storage.

> 📌 `exec`, `run`, and `shell` create independent sessions. To read or control a running window, use `gui`; see [Window control](window-control.md).

## 🚀 Quick check

Run from the project root:

```powershell
py -B -m markprompt_cli --help
py -B -m markprompt_cli commands --json
py -B -m markprompt_cli exec --workspace "examples" --file "hello.md" -c "/search -i notes" --json
py -B -m markprompt_cli run --workspace "examples" --script "examples/workflow.json" --json
```

These queries and the read-only workflow leave the example files unchanged. You can also use `py markprompt_cli.py ...`; use the entry file's full path when calling it from another directory.

## 🧩 Ways to run

| Entry | Purpose |
| --- | --- |
| `exec -c "command" [-c "command"]` | Execute several commands in one process and session |
| `run --script file` | Execute a UTF-8 text or JSON workflow; `-` reads standard input |
| `shell` | Keep a session open, reading and responding line by line until EOF or `/quit` |
| `commands --json` | Query primary commands, aliases, arguments, and `cli_supported` capability flags |

Separate processes do not share the current file, search state, or drafts. Keep related steps in one `exec`, `run`, or `shell` session.

### Common options

| Option | Meaning |
| --- | --- |
| `--workspace path` | Select a workspace explicitly; the program directory does not become the workspace automatically |
| `--file path` | Open a file before executing commands; resolve a relative path against the selected workspace, or the process working directory if none is selected |
| `--json` | Output one JSON report for `exec` / `run`, or JSON Lines for `shell` |
| `--include-text` | Include document text in every state snapshot; use as needed for large files |
| `--allow-dirty` | Allow a check that edits only in memory; the final report still returns the draft |
| `--config path` | Load and save preferences, including language, in this settings file; without it, CLI preferences last only for the current process and do not change GUI settings |

Place options after the entry, for example `exec --workspace ... --json`. The top-level `--version` option goes before the entry. `--workspace` does not restore GUI workspace state, search history, or recovery snapshots. The CLI does not write to the GUI recovery slots automatically.

### 🌐 Choose and remember a language

Unconfigured sessions use English. `/lang` lists the discovered languages; this release includes `en` (English) and `zh` (Simplified Chinese). `/lang code` switches language. With an explicit configuration, the next CLI session restores that preference:

```powershell
py -B -m markprompt_cli exec --config settings.json -c "/lang zh" --json
py -B -m markprompt_cli exec --config settings.json -c "/help"
```

The GUI also saves its language preference in its settings file. Missing translations and an unavailable saved language fall back to English. Switching language preserves the current draft, search scope, navigation, and pending confirmation. Command names and keywords stay in English; machine JSON field names, status values, and error codes stay stable. Human descriptions and messages use the selected language. See [Localization](localization.md) to contribute a language.

## 📝 Edit and save

```powershell
py -B -m markprompt_cli exec --workspace "C:\Notes" --file "demo.md" -c "/search -i keyword" -c "/line 12 replacement" -c "/save" --json
```

This example changes the selected file. In search mode, it replaces only the hits on line 12; saving preserves SEARCH. Appends also require `/save` to reach disk. If a draft remains on exit, the default exit code is `4` and the report includes its text; an unsaved edit is not reported as a completed save.

```json
[
  "/open demo.md",
  "/append",
  "First line\nSecond line",
  "/end",
  "/save"
]
```

A JSON workflow must be an array of strings and can contain multiline text. Text workflows read one input per line and skip blank lines and comments starting with `#`; use JSON to append such content. Set `run --script-format json` or `lines` to choose a format explicitly; the default detects it. Script paths are relative to the process working directory, not the workspace. Execution stops at the first error by default. `run --continue-on-error` continues but still reports a failing final result.

## ✅ Confirmations stay in the terminal

| Situation | Response and answer |
| --- | --- |
| Overwrite an existing file | `status: needs_confirmation`; submit `y` or `n` as the next input |
| Leave an unsaved document or quit | Submit `save`, `discard`, or `cancel` as the next input |

For example, `-c "/new existing" -c "y"` explicitly confirms an overwrite. Without an answer, the CLI returns exit code `3` instead of waiting for a dialog. A confirmation request may be accepted while its action remains incomplete. AI clients must check `status` and `state.pending`, in addition to an individual result's `ok` field.

## 📦 JSON and exit codes

The main fields in an `exec` / `run` report are:

```json
{
  "schema_version": 1,
  "version": "2026.11.01-i18n1",
  "ok": true,
  "code": "ok",
  "exit_code": 0,
  "results": [],
  "state": {},
  "gui_control": false
}
```

- `results`: each input's status, error code, data, messages, and resulting state.
- `state.document`: current file, saved fingerprint, and dirty lines; `/source` returns source text in `data.text`.
- `state.business`: modes ordered from parent to child; pending confirmations live separately in `state.pending`.
- `state.search`: keyword, case rule, and whole-document or line scope; `data.hits` contains line numbers, start and end positions, and original line text.
- Hit line numbers start at `1`; `start` starts at `0` and `end` is exclusive. Coordinates count Unicode characters.
- FIND returns `data.results`; `matching_lines` counts matching lines, rather than string occurrences.
- File lists use `data.files`, outlines use `data.headings`, tasks use `data.tasks`, and tag counts use `data.tags`.

| Exit code | Meaning |
| --- | --- |
| `0` | Success, with no pending confirmation or unallowed draft |
| `1` | Command / I/O failure, or a GUI-only command |
| `2` | Invalid arguments or workflow format |
| `3` | Confirmation required or invalid confirmation answer |
| `4` | Unsaved changes remain |
| `5` | Disk save conflict |
| `70` | Internal execution error |
| `130` | User interruption |

Errors remain parseable JSON; logs do not mix into stdout. Normal interruptions and caught execution errors also return the current draft. A process killed by the operating system may be unable to produce output. Each shell response has `event: command`, followed at the end by `event: session_end`; parse the output line by line. The final shell exit code reflects the last result and current draft / confirmation state.

## 🧱 Display requests and effects

Individual results include `effects` and `effects_omitted`. They record messages, errors, and display / navigation / positioning / refresh requests, up to 200 entries. For example, `document_view_requested` requests a file view; it does not prove that the file opened. Check `ok`, the error code, and `state`. These fields extend protocol version 1 while retaining existing fields. For asynchronous GUI work, use the final result or snapshot to confirm completion.

## 📸 AI semantic snapshots

```powershell
py -B -m markprompt_cli exec --workspace "examples" --file "hello.md" -c "/snapshot" --json
py -B -m markprompt_cli run --workspace "examples" --script "examples/workflow.json" --json
```

`results[].data.snapshot` contains the current session's structured state. `/snapshot state.json` exports a file and returns its actual path in `data.snapshot_path`. Text is limited to 65,536 characters by default; `--full` includes all document text. Viewport, selection, modes, search, and directory data have separate fields and explicit truncation information.

Snapshots read memory, preserve drafts and pending confirmations, and do not reread disk as a substitute. An existing draft or confirmation still affects the final exit code. An independent CLI snapshot describes its own session. `gui snapshot` reads a real window's selection and viewport directly. See [AI snapshots](snapshots.md).

## 🖥️ CLI and GUI capabilities

Independent mode supports **45 primary commands**; use `commands --json` for the current list. Preview, view switching, themes, animation, clearing the display, opening external apps, and revealing folders are GUI-only. They return `gui_required` instead of reporting an invented UI action.

The CLI can verify files, text, search, editing, saving, navigation, and business state. Actual drops, fonts, layout, and image pixels require GUI verification.

Start the GUI with Python as usual; each newly started window provides a local connection. `gui exec` runs commands in that window, including UI commands. For explicit confirmations, waiting, request results, and preconditions, see [Window control](window-control.md). GUI-only restrictions still apply to independent `exec` sessions.

## 🌐 CLI language

Place the global `--language CODE` option before the mode:

```powershell
py -B -m markprompt_cli --language zh commands
py -B -m markprompt_cli --language zh exec --config settings.json -c "/status"
```

Without this option, `exec`, `run`, and `shell` restore the language from an explicit `--config`; otherwise they start in English. An explicit language override is saved when `--config` is supplied. During a session, `/lang code` changes the language. `--json` keeps its protocol field names and error codes in either language.
