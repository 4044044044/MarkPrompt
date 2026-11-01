# 🤖 MarkPrompt CLI

🌐 [English](cli.md) | **简体中文**

> 以下命令从仓库根目录执行。

版本：`2026.11.01-i18n1` · JSON 协议版本：`1`

独立运行，不创建窗口、不加载 Tk／Pillow／tkinterdnd2。与 GUI 共用命令目录、命令动作、文档会话、搜索、状态及存储。

> 📌 本文的 exec／run／shell 属于独立会话。读取和控制运行中的窗口请使用 `gui` 入口，见 [运行中窗口控制](window-control.zh-CN.md)。

## 🚀 快速验收

在项目根目录运行：

```powershell
py -B -m markprompt_cli --help
py -B -m markprompt_cli commands --json
py -B -m markprompt_cli exec --workspace "examples" --file "hello.md" -c "/search -i notes" --json
py -B -m markprompt_cli run --workspace "examples" --script "examples/workflow.json" --json
```

上述查询与只读工作流不修改示例文件。
也可以执行 `py markprompt_cli.py ...`；从其他目录调用时使用入口文件的完整路径。

## 🧩 三种执行方式

| 入口 | 用途 |
| --- | --- |
| `exec -c "命令" [-c "命令"]` | 在一个进程／会话中执行多条命令 |
| `run --script 文件` | 执行 UTF-8 文本或 JSON 工作流；`-` 表示标准输入 |
| `shell` | 保持会话，逐行输入并响应，直到 EOF 或 `/quit` |
| `commands --json` | 查询主命令、别名、参数及 `cli_supported` 能力标记 |

不同进程不共享当前文件、搜索状态或草稿。连续工作应放在同一次 exec、run 或 shell 中。

### 共同参数

| 参数 | 含义 |
| --- | --- |
| `--workspace 路径` | 显式选择工作区；不自动把程序目录当工作区 |
| `--file 路径` | 执行前打开文件；相对路径以指定工作区为基准，未指定则以进程当前目录为准 |
| `--json` | exec／run 输出一个 JSON 报告；shell 输出 JSON Lines |
| `--include-text` | 每个状态快照都包含正文；大文档建议只在需要时使用 |
| `--allow-dirty` | 允许仅在内存中修改的验收；退出仍返回草稿内容 |
| `--config 路径` | 显式指定设置文件，读取并保存语言等偏好；未指定时只在当前 CLI 进程保留，不改 GUI 配置 |

参数放在入口后，例如 `exec --workspace ... --json`。只有运行级 `--version` 放在入口前。
`--workspace` 不会自动恢复 GUI 的工作区、搜索历史或恢复快照。CLI 也不自动写入 GUI 的恢复槽。

### 🌐 选择并记住语言

没有配置时默认使用英语。`/lang` 列出自动发现的语言，本版本包含 `en`（英语）和 `zh`（简体中文）；`/lang code` 切换语言。传入配置文件即可在下一次 CLI 会话恢复偏好：

```powershell
py -B -m markprompt_cli exec --config settings.json -c "/lang zh" --json
py -B -m markprompt_cli exec --config settings.json -c "/help"
```

GUI 也会在设置文件中保存语言。缺失译文或不可用的已保存语言回退英语；切换保留草稿、搜索范围、导航和待确认事项。命令名、关键词、JSON 字段、状态值与错误代码保持稳定，人类可读描述和提示使用所选语言。贡献方法见 [语言扩展](localization.zh-CN.md)。

## 📝 编辑与保存

```powershell
py -B -m markprompt_cli exec --workspace "C:\Notes" --file "demo.md" -c "/search -i keyword" -c "/line 12 replacement" -c "/save" --json
```

此示例会修改指定文件：搜索态下只替换第 12 行的命中，保存后仍保留 SEARCH。
普通追加需 `/save` 才写盘。退出仍有草稿时，默认退出码为 `4`，并返回正文；不会把未保存操作当作成功。

```json
[
  "/open demo.md",
  "/append",
  "第一行\n第二行",
  "/end",
  "/save"
]
```

JSON 工作流必须是字符串数组，适合多行正文。文本工作流一行一条输入，空行和 `#` 开头的注释行跳过；需要追加这类正文时使用 JSON。
`run --script-format json` 或 `lines` 可指定格式；默认自动识别。脚本文件路径相对于进程当前目录，不是工作区目录。
默认遇到错误停止；`run --continue-on-error` 可继续，但最终仍返回失败。

## ✅ 确认不会弹窗

| 场景 | 响应与回答 |
| --- | --- |
| 覆盖已有文件 | `status: needs_confirmation`，下一条输入 `y` 或 `n` |
| 离开未保存文档／退出 | 下一条输入 `save`、`discard` 或 `cancel` |

例如 `-c "/new existing" -c "y"` 明确确认覆盖。
未提供回答时直接返回退出码 `3`，不会阻塞等待窗口。确认请求本身可以被接受，但动作仍未完成；AI 应检查 `status` 和 `state.pending`，不能只看单条结果的 `ok`。

## 📦 JSON 与退出码

exec／run 报告主要字段：

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

- `results`：每条输入的状态、错误代码、数据、提示及执行后的状态。
- `state.document`：当前文件、保存指纹、脏行；`/source` 在 `data.text` 返回原文。
- `state.business`：父状态到子状态的顺序；确认提示独立放在 `state.pending`。
- `state.search`：搜索词、大小写规则、全文／行范围；`data.hits` 返回行号、起止位置和原行文本。
- 命中行号从 `1` 开始；`start` 从 `0` 开始，`end` 不包含结束位置，均按 Unicode 字符计。
- FIND 数据在 `data.results`，`matching_lines` 表示命中行数；不是字符串出现次数。
- 文件列表在 `data.files`；大纲在 `data.headings`；任务在 `data.tasks`；标签统计在 `data.tags`。

| 退出码 | 含义 |
| --- | --- |
| `0` | 成功，且不存在未处理确认或未允许的草稿 |
| `1` | 命令／I/O 失败，或该命令仅适用于 GUI |
| `2` | 参数或工作流格式错误 |
| `3` | 需要确认／确认回答无效 |
| `4` | 尚有未保存修改 |
| `5` | 磁盘保存冲突 |
| `70` | 内部执行错误 |
| `130` | 用户中断 |

JSON 错误保持可解析，不向 stdout 混入日志。正常中断和已捕获的执行错误也返回当前草稿；不承诺进程被系统强杀时还能输出。
shell 的每条响应为 `event: command`，最后为 `event: session_end`；读取输出时按行解析。其最终错误码以最后一条结果及当前草稿／确认状态为准。

## 🧱 命令展示请求

单条结果增加 `effects` 和 `effects_omitted`：记录提示、错误、显示／导航／定位／刷新请求，最多 200 项。
例如 `document_view_requested` 表示请求显示某文件，不能只凭此断言已经打开；仍需检查 `ok`、错误代码和 `state`。
这些是协议版本 1 的新增字段，既有字段保留。异步 GUI 完成状态以最终结果／快照为准。

## 📸 AI 语义快照

```powershell
py -B -m markprompt_cli exec --workspace "examples" --file "hello.md" -c "/snapshot" --json
py -B -m markprompt_cli run --workspace "examples" --script "examples/workflow.json" --json
```

`results[].data.snapshot` 返回当前会话的结构化现场；`/snapshot state.json` 可导出文件，实际路径在 `data.snapshot_path`。
默认正文最多 65,536 个字符，`--full` 可包含完整正文。视口、选区、状态、搜索和目录都单独标记，截取有显式信息。
不重读磁盘代替内存、不修改草稿或确认；已有草稿／确认仍会影响最终退出码。
独立 CLI 的快照属于自己的会话；`gui snapshot` 可直接读取真实窗口的选区与视口。详见 [AI数据快照](snapshots.zh-CN.md)。

## 🖥️ CLI 与 GUI 的边界

独立模式有 **45 个可用主命令**，完整清单以 `commands --json` 为准。
预览、视图切换、主题、动画、清屏、外部程序打开和文件管理器展示标记为 GUI 专属，返回 `gui_required`，不会伪造界面操作成功。
CLI 可以验证文件、正文、搜索、编辑、保存、导航和业务状态；真实拖拽、字体、排版和图片像素仍由 GUI 验收。

GUI 的 Python 启动方式保持不变，重启后自动提供本机连接。`gui exec` 在窗口中执行包括界面功能在内的命令；显式确认、等待、请求结果和前置条件见 [运行中窗口控制](window-control.zh-CN.md)。独立 exec 的 GUI 专属限制仍保留。

## 🌐 CLI 语言

全局 `--language CODE` 放在子命令前：

```powershell
py -B -m markprompt_cli --language zh commands
py -B -m markprompt_cli --language zh exec --config settings.json -c "/status"
```

省略此选项时，`exec`、`run` 和 `shell` 从显式指定的 `--config` 恢复语言，否则使用英文。指定语言并提供 `--config` 时会保存选择。会话中可用 `/lang code` 切换语言；`--json` 的协议字段和错误码保持一致。
