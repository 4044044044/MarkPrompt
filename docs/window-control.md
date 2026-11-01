# 🪟 Connect to and control a running window

🌐 **English** | [简体中文](window-control.zh-CN.md)

> Run these commands from the repository root.

Version: `2026.11.01-i18n1` · Local communication protocol: `1`

The CLI can read and operate a running MarkPrompt window, including its unsaved text. Start `markprompt.py` from the repository root, then run the commands below. Replace `WINDOW_ID`, `CONFIRMATION_ID`, and `TEXT_SHA256` with actual values.

## 🚀 Connect

Run from the project directory:

```powershell
py -B -m markprompt_cli gui windows --json
py -B -m markprompt_cli gui snapshot --json
py -B -m markprompt_cli gui snapshot --window WINDOW_ID --full --json
```

With one available window, `--window` is optional. With several, select one explicitly. `windows` returns IDs, process IDs, versions, and source paths so you can distinguish test copies from the main app. `snapshot` reads the window's current memory without reopening files, exporting a file, or answering confirmations. Text truncation follows [AI snapshots](snapshots.md); `--full` includes all source text.

## ⌨️ Execute commands

```powershell
py -B -m markprompt_cli gui exec --window WINDOW_ID -c "/search keyword" --json
py -B -m markprompt_cli gui exec --window WINDOW_ID -c "/line 12 replacement" -c "/save" --json
```

This uses the same registered commands and state rules, including GUI commands for themes and views. The connection exposes no system shell, arbitrary Python execution, deserialization execution, or unrestricted widget operations. Remote commands preserve the command draft the user is currently typing; edits and navigation refresh the document and view through the normal app behavior.

`exec` returns each operation's `results`, `effects`, and completed `snapshot`, plus `request_id` and `window_id`. `snapshot.source.kind` is `gui`, and `connection.gui_control` is true. Display requests in the effects are not proof of success; check `ok`, error codes, and final state.

GUI drafts stay in the window when the CLI process exits and are not saved automatically. A GUI `exec /append` may therefore exit successfully while reporting dirty state. The independent headless CLI retains its normal unsaved-exit rules.

`/lang zh` and `/lang en` change the window's language and save its preference. Switching language preserves the document, search, navigation, command draft, and pending confirmation. JSON field names, machine status values, confirmation choices, and error codes remain stable. See [Localization](localization.md).

## ✅ Answer confirmations explicitly

Leaving an unsaved document or overwriting a file returns exit code `3`, with a pending confirmation in `snapshot.interaction.pending`:

```json
{
  "id": "CURRENT_CONFIRMATION_ID",
  "kind": "unsaved_navigation",
  "choices": ["save", "discard", "cancel"]
}
```

```powershell
py -B -m markprompt_cli gui respond --window WINDOW_ID --confirmation CONFIRMATION_ID cancel --json
```

- Unsaved navigation / quit: `save`, `discard`, `cancel`.
- Overwrite: `y`, `n`.
- An expired ID returns `stale_confirmation` and cannot answer a newer confirmation.
- While confirmation is pending, normal commands are blocked; read-only snapshots remain available.
- If `save` encounters a disk conflict, it returns `disk_changed`, preserves the current document and draft, and stops navigation.

The GUI's keyboard and mouse answers remain available.

## ⏳ Background work and timeouts

By default, `exec` waits for background search and document rendering before continuing to the next `-c`. Use `--no-wait` to return immediately, then wait with:

```powershell
py -B -m markprompt_cli gui wait --window WINDOW_ID --timeout 20 --json
```

The default timeout is 10 seconds; accepted values are 0.1–60 seconds. A pending confirmation returns immediately without choosing save or discard. Search job status, errors, and generation appear in `snapshot.find.job`. If another job replaces it while waiting, the result is `state_changed`; AI clients should observe again.

A request that times out in the GUI queue before starting is canceled with `executed: false`, preventing later execution. Requests that have started may still finish. A disconnected connection or `request_pending` alone does not establish that an operation failed.

## 🔎 Query results before repeating a write

```powershell
py -B -m markprompt_cli gui exec --window WINDOW_ID --request-id action-001 -c "/append text" --json
py -B -m markprompt_cli gui result --window WINDOW_ID action-001 --json
```

While a result remains cached, the same request ID with the same arguments is not executed twice. Reusing the ID with different arguments is rejected. The cache holds the most recent 128 requests with bounded result text; it is not a permanent operation log. A result may be evicted or its window may close.

`request_not_found` / `result_unavailable` means that the cache cannot confirm the result. **Do not automatically repeat a write**; read the current snapshot and file state first. A cached snapshot reflects the moment that request completed; call `snapshot` again for the current state.

## 📍 Guard edits against stale text

Use the current `document.text_sha256` and absolute file path as preconditions for a single command:

```powershell
py -B -m markprompt_cli gui exec --window WINDOW_ID --expect-file "C:\Notes\note.md" --expect-sha256 TEXT_SHA256 -c "/line 12 replacement" --json
```

If the window has switched files or its in-memory text has changed, the request returns `stale_snapshot` without executing the edit. Preconditions and manually supplied `--request-id` values require exactly one `-c`. The storage service still performs an independent disk-version conflict check on save.

## 📦 Exit codes

| Exit code | Meaning |
| --- | --- |
| `0` | This read / operation succeeded; the window may still contain unsaved changes |
| `1` | Command, business state, stale snapshot / confirmation, or search failure |
| `2` | Invalid arguments |
| `3` | An explicit confirmation answer is required |
| `5` | Save conflict |
| `6` | Connection unavailable, no windows, or multiple windows without a selection |
| `7` | Request / wait timeout, or an outcome that cannot yet be confirmed |

## 🔌 Runtime and boundaries

Each normally started window listens on a random `127.0.0.1` port with its own random credentials. On Windows its descriptor is `%LOCALAPPDATA%\MarkPrompt\runtime\WINDOW_ID.json`. The CLI window list omits credentials.

Only local connections are accepted. The network thread authenticates, transfers, and queues requests; all Tk, snapshot, and command handling runs on the window's main thread. Closing a window removes its descriptor. Discovery ignores stale files left by forced termination. `--runtime-dir` supports isolated testing or custom deployment. This mechanism serves local tools running as the same user; it is not a remote network service and does not isolate programs that already control that user account.

Programmatic construction can disable the connection with `MarkPromptApp(enable_bridge=False)` or choose an isolated directory with `bridge_directory=`. Normal GUI features continue if the communication service fails to start, and the UI reports the connection error.
