# 🌐 语言扩展与翻译贡献

🌐 [English](localization.md) | **简体中文**

> 一个语言模块、一份消息字典，共用英语回退。

版本：`2026.11.01-i18n1`

MarkPrompt 随附英语（`en`）和简体中文（`zh`）。没有保存过偏好时，新会话默认使用英语。`/lang` 列出当前版本自动发现的语言，`/lang zh` 切换中文，`/lang en` 切换英语。语言列表、补全与参数校验来自同一个注册表。

## 💾 保存语言偏好

GUI 会在正常设置文件中记住语言。独立 CLI 使用显式的 `--config` 文件读取和保存偏好：

```powershell
py -B -m markprompt_cli exec --config settings.json -c "/lang zh" --json
py -B -m markprompt_cli shell --config settings.json
```

没有 `--config` 时，独立 CLI 的语言切换只在当前进程生效，不改 GUI 设置。已保存的语言不可用时回退英语，其他设置保持原样。

切换语言会保留未保存正文、搜索命中与范围、导航、命令输入和待确认事项，同时刷新帮助、命令描述、关键词补全描述、状态与提示。命令名、别名、`save` / `discard` / `cancel` 等关键词、JSON 字段、协议值和错误代码保持稳定，同一套命令与自动化可以继续使用。

## 🧩 语言模块格式

资源位于 `markprompt_core/localization/locales/<code>.py`。每个普通 UTF-8 Python 模块导出：

| 导出值 | 含义 |
| --- | --- |
| `CODE` | 唯一语言代码，如 `en`、`zh` |
| `NAME` | `/lang` 与补全显示的语言名称 |
| `MESSAGES` | 稳定消息键到译文字符串的字典 |

以 `en.py` 中的键为准。以下只是部分翻译的格式示例；`xx` 不是本版本实际随附的语言：

```python
CODE = "xx"
NAME = "Example language"
MESSAGES = {
    "ui.home": "Welcome to MarkPrompt.",
    "command.save": "Save current note to disk",
    "keyword.open.desktop": "Open the Desktop folder",
}
```

把示例文字换成译文，并选择真实、唯一的语言代码。文件名与 `CODE` 对应；代码以小写字母开头，只含小写字母、数字、`_` 或 `-`，文件名也应能作为 Python 模块导入。语言模块只声明常量与字符串，不启动应用或添加外部依赖。这些文件会作为 Python 代码导入，需要按源码贡献审阅。

### 消息键

- `ui.*`：界面文字、标题、状态、通知和确认。
- `command.<name>`：已注册主命令的描述，如 `command.save`。
- `keyword.<command>.<token>`：稳定命令关键词的描述，如 `keyword.open.desktop`。
- 英语基准中已有的其他键，如共享参数错误使用的 `argument.*`，也按原键翻译。

只翻译描述，不修改键、命令词、示例文件名或协议值。别名帮助使用对应主命令的描述。语言候选来自语言元数据，新增模块无需在命令目录再写一份中英判断。

## 🔎 自动发现与回退

本地化包通过标准库 `pkgutil` 发现 `locales` 下的模块，再由 `importlib` 导入。英语先注册，作为基准。添加有效模块就是注册步骤；修改已安装的模块后需重启应用或 CLI 进程。

语言可以只翻译一部分。缺失的键显示英语基准文字，翻译尚未完成时仍能使用帮助和提示。不可用的已保存语言也回退英语。回退不代表接受格式错误的翻译：重复代码、无效元数据、非字符串消息、未知消息键以及不兼容占位符都需要修正。

### 保留占位符

保留英语消息中的占位符、顺序与类型。现有消息使用百分号格式。例如 `ui.exit_line` 依次包含 `%s` 和 `%d`，译文也必须按同样顺序保留。不要把 `%d` 改成 `%s`，不要增删参数或把占位符翻译成普通文字。需要转义的字面百分号仍使用 `%%`。

## ✅ 验证贡献

在源码根目录执行：

```powershell
py -B -m markprompt_core.localization --check
```

检查会导入并校验自动发现的模块，列出各语言消息数量与英语回退数量。允许缺少译文，并统计回退；资源格式错误或占位符不匹配时检查失败。

接着在 GUI 中切换语言，检查 `/help`、命令与关键词补全、`/status`、搜索和确认。重启后应恢复选择；切换时应保留未保存草稿与搜索范围。再用 `--config` 检查独立 CLI 的人类可读输出和稳定 JSON 字段。部分翻译应额外验证缺失消息确实显示英语回退。

## 📦 打包语言模块

源码包把本地化包作为普通 Python 源码随附，不需要额外语言数据目录或运行时依赖。冻结打包时，GUI 与 CLI 都要收集动态发现的子模块：

```powershell
# 在 README 的两个 PyInstaller 命令中加入：
--collect-submodules markprompt_core.localization
```

[README 打包示例](../README.zh-CN.md#build) 已包含此选项。新增语言后重新构建可执行文件；放在现有单文件程序旁的模块不会自动进入其内部。对冻结版 GUI 和 CLI 再检查 `/lang`、帮助、消息与回退。本版本只随附英语与中文模块。
