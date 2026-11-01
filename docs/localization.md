# 🌐 Localization and language contributions

🌐 **English** | [简体中文](localization.zh-CN.md)

> One language module, one message dictionary, shared English fallback.

Version: `2026.11.01-i18n1`

MarkPrompt ships English (`en`) and Simplified Chinese (`zh`). New sessions without a saved preference start in English. Run `/lang` to list the languages discovered by your installed build, `/lang zh` for Chinese, or `/lang en` for English. Completion and language validation use the same registry as the list.

## 💾 Remember a preference

The GUI saves the selected language in its normal settings file. Independent CLI sessions use an explicit `--config` file to restore and save preferences:

```powershell
py -B -m markprompt_cli exec --config settings.json -c "/lang zh" --json
py -B -m markprompt_cli shell --config settings.json
```

Without `--config`, independent CLI language changes last only for that process and leave GUI settings alone. An unavailable saved language falls back to English. Loading that fallback preserves unrelated settings.

Switching language preserves unsaved text, search matches and scope, navigation, command input, and pending confirmations. It refreshes human-facing help, command descriptions, completion descriptions, status, and messages. Command names, aliases, keywords such as `save` / `discard` / `cancel`, machine JSON keys, protocol values, and error codes remain stable. Use the same commands and automation in either language.

## 🧩 Language module format

Resources live in `markprompt_core/localization/locales/<code>.py`. Each ordinary UTF-8 Python module exports three values:

| Export | Meaning |
| --- | --- |
| `CODE` | Unique language code, such as `en` or `zh` |
| `NAME` | Human-readable language name for `/lang` and completion |
| `MESSAGES` | Dictionary mapping stable message keys to translated strings |

Start from the keys in `en.py`. This illustrative partial module shows the shape; `xx` is an example code, not a language included in the release:

```python
CODE = "xx"
NAME = "Example language"
MESSAGES = {
    "ui.home": "Welcome to MarkPrompt.",
    "command.save": "Save current note to disk",
    "keyword.open.desktop": "Open the Desktop folder",
}
```

Replace the example text with your translation and choose a real, unique code. Match the filename to `CODE`; use a lowercase code beginning with a letter and containing only letters, digits, `_`, or `-`. Use an importable module filename. Keep locale modules declarative: constants and strings, without application startup or external dependencies. They are imported as Python code and must be reviewed as source contributions.

### Message keys

- `ui.*`: interface text, headings, status, notifications, and confirmations.
- `command.<name>`: descriptions of registered primary commands, for example `command.save`.
- `keyword.<command>.<token>`: descriptions of stable command keywords, for example `keyword.open.desktop`.
- Other existing English baseline keys, such as `argument.*`, cover shared argument errors. Translate those keys in place too.

Translate descriptions without changing their keys, command tokens, filenames in examples, or protocol values. Alias help uses its registered command's description. Language candidates come from language metadata, so a new locale does not require adding an EN/ZH branch to the command catalog.

## 🔎 Discovery and fallback

The localization package uses standard-library `pkgutil` discovery and `importlib` imports to load the modules in `locales`. English is the baseline and is registered first. Adding a valid module registers a language; restart the app or CLI process after changing installed modules.

A language may translate only part of the baseline. A missing key uses its English text, keeping help and messages available while a contribution is in progress. An unknown saved language also selects English. This fallback does not make malformed translations valid: duplicate codes, invalid metadata, non-string messages, unknown message keys, and incompatible placeholders must be fixed before the module can be accepted.

### Preserve placeholders

Keep the English message's placeholders, order, and types. Existing messages use percent formatting. For example, `ui.exit_line` contains `%s` followed by `%d`; its translation must retain those placeholders in that order. Do not replace `%d` with `%s`, add or remove an argument, or turn a placeholder into prose. Retain escaped literal percent signs as `%%` where formatting requires them.

## ✅ Validate a contribution

Run from the source root:

```powershell
py -B -m markprompt_core.localization --check
```

The check imports and validates discovered modules, reports message counts and English fallbacks for each language, and exits with failure for invalid resources. Missing translations are allowed and are reported as fallbacks; invalid placeholders are rejected.

Then open the GUI, select the language, and inspect `/help`, command and keyword completion, `/status`, a search, and a confirmation. Confirm that the language survives a restart and that switching preserves an unsaved draft and search scope. Check an independent CLI session with `--config`, including human-readable output and stable JSON keys. For a partial translation, check a missing message and confirm that its English fallback appears.

## 📦 Package the modules

Source distributions include the localization package as normal Python source, without a separate language data directory or new runtime dependency. A freezer must include dynamically discovered submodules in both GUI and CLI builds:

```powershell
# Add to each PyInstaller command in the README:
--collect-submodules markprompt_core.localization
```

The [README build examples](../README.md#build) include this option. Rebuild executables after adding a language; a module added beside an existing one-file executable is not part of that bundled build. Check `/lang`, help, messages, and fallback again in the frozen GUI and CLI. This release ships only the English and Chinese modules.
