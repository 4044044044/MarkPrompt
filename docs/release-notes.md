# 🗓️ Release notes

🌐 **English** | [简体中文](release-notes.zh-CN.md)

> `2026.11.01-i18n1` · English first, with room for more languages.

## 🌐 Language and preferences

- English is the default for unconfigured GUI and CLI sessions. English and Simplified Chinese remain the two included languages.
- `/lang [code]` lists or switches discovered languages. The GUI remembers the choice; independent CLI sessions remember it with `--config`.
- Language resources live in independent Python modules. Missing messages fall back to English, and translations are checked for compatible placeholders.
- Help, completion descriptions, status, errors, confirmations, and human-readable CLI messages use the selected language. Switching preserves drafts, search state, navigation, and pending confirmations.

## 📖 Documentation

The default README and public guides are English. Chinese versions are linked beside them. Existing `README.en.md` links lead to a compatibility page pointing to the default README. The [localization guide](localization.md) explains language modules, discovery, fallback, validation, and executable packaging.

Command names, aliases, keywords, machine JSON keys, protocol values, and error codes remain stable. Existing screenshots, demos, sample artwork, and the small example-note Easter egg are retained.

## 🔨 Build

GUI and CLI executable builds must include `markprompt_core.localization` and its discovered locale modules. The [build commands](../README.md#build) collect these Python submodules without adding a runtime dependency. Windows is the acceptance target for this release; other platforms require their own verification.
