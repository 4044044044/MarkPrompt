# 🪟 运行中窗口连接与控制

🌐 [English](window-control.md) | **简体中文**

> 以下命令从仓库根目录执行。

版本：`2026.11.01-i18n1` · 本机通信协议：`1`

CLI 可以读取和操作运行中的 MarkPrompt 窗口，包括尚未保存的正文。先启动仓库根目录的 `markprompt.py`，再运行下方命令。

示例中的 `WINDOW_ID`、`CONFIRMATION_ID` 和 `TEXT_SHA256` 需要替换为实际值。

## 🚀 连接

在项目目录执行：

```powershell
py -B -m markprompt_cli gui windows --json
py -B -m markprompt_cli gui snapshot --json
py -B -m markprompt_cli gui snapshot --window WINDOW_ID --full --json
```

只有一个可连接窗口时可以省略 `--window`；有多个时必须明确选择，不按最近窗口猜测。
`windows` 返回 ID、进程号、版本及源码路径，可分辨测试副本和正式项目。
`snapshot` 直接返回窗口内存现场，不重新打开文件、不生成导出文件，也不替用户回答确认。
正文截取规则沿用 [AI数据快照](snapshots.zh-CN.md)；`--full` 包含完整原文。

## ⌨️ 执行命令

```powershell
py -B -m markprompt_cli gui exec --window WINDOW_ID -c "/search keyword" --json
py -B -m markprompt_cli gui exec --window WINDOW_ID -c "/line 12 replacement" -c "/save" --json
```

执行同一套已注册命令和状态规则，可以使用主题、视图等 GUI 命令。
没有系统 Shell、任意 Python、反序列化执行或任意控件操作入口。
远程执行保留用户正在输入的命令草稿；编辑／导航仍按正常功能刷新正文和视图。

`exec` 返回每次操作的 `results`、`effects` 和完成后的 `snapshot`，以及 `request_id`、`window_id`。
`snapshot.source.kind` 为 `gui`；`connection.gui_control` 为 true。
事件中的显示请求不是成功证明，仍要检查 `ok`、错误码与最终状态。

GUI 中的草稿会留在窗口里，CLI 进程退出不会丢弃它，也不会自动保存。
因此 GUI `exec /append` 可以退出成功并报告 dirty；独立无窗口 CLI 的未保存退出规则保持原样。

## ✅ 明确回答确认

离开未保存文档或覆盖文件时，返回退出码 `3`，并在 `snapshot.interaction.pending` 中提供：

```json
{
  "id": "本次确认编号",
  "kind": "unsaved_navigation",
  "choices": ["save", "discard", "cancel"]
}
```

```powershell
py -B -m markprompt_cli gui respond --window WINDOW_ID --confirmation CONFIRMATION_ID cancel --json
```

- 未保存导航／退出：`save`、`discard`、`cancel`。
- 覆盖确认：`y`、`n`。
- 编号过期返回 `stale_confirmation`；不会误答后来出现的另一个确认。
- 等待确认时普通命令被阻止，只读快照仍可获取。
- `save` 遇到磁盘冲突返回 `disk_changed`，保留当前文档和草稿，不继续导航。

GUI 本来的键盘／鼠标回答方式保持不变。

## ⏳ 后台任务与超时

`exec` 默认等待后台搜索及文档渲染完成，再继续下一条 `-c`。
`--no-wait` 可立即返回；随后使用：

```powershell
py -B -m markprompt_cli gui wait --window WINDOW_ID --timeout 20 --json
```

默认超时 10 秒，可设置 0.1–60 秒。等待期间遇到确认会立即返回；不会自动选择保存或放弃。
搜索任务状态、错误与代数在 `snapshot.find.job` 中。期间换了另一个任务会返回 `state_changed`，AI 应重新观察。

请求在 GUI 队列中超时且尚未开始时会取消，标记 `executed: false`，不会稍后偷偷执行。
已经开始的请求可能继续完成；连接中断或 `request_pending` 都不能直接推断操作失败。

## 🔎 查询结果，避免重复写入

```powershell
py -B -m markprompt_cli gui exec --window WINDOW_ID --request-id action-001 -c "/append text" --json
py -B -m markprompt_cli gui result --window WINDOW_ID action-001 --json
```

缓存保留期间，同一请求编号与同一参数不会重复执行；同编号换参数会拒绝。
缓存只保留最近 128 个请求及有界结果正文，不是永久操作日志。结果可能已被淘汰或窗口已关闭。
`request_not_found`／`result_unavailable` 表示无法从缓存确认，**不要自动重发写操作**；先读取当前快照和文件状态。
缓存结果的快照属于当时完成时刻，获取最新现场请重新 `snapshot`。

## 📍 防止基于旧正文修改

AI 可以用刚取得的 `document.text_sha256` 和绝对文件路径作为单条命令前置条件：

```powershell
py -B -m markprompt_cli gui exec --window WINDOW_ID --expect-file "C:\Notes\note.md" --expect-sha256 TEXT_SHA256 -c "/line 12 replacement" --json
```

窗口切换文件或内存内容已变化时返回 `stale_snapshot`，不执行修改。
这些参数和手工 `--request-id` 仅用于单条 `-c`。保存时仍由存储服务执行独立的磁盘版本冲突检查。

## 📦 退出码

| 退出码 | 含义 |
| --- | --- |
| `0` | 本次读取／操作成功；窗口草稿仍可能未保存 |
| `1` | 命令、业务、旧快照／旧确认或搜索失败 |
| `2` | 参数错误 |
| `3` | 需要明确回答确认 |
| `5` | 保存冲突 |
| `6` | 无法连接、没有可用窗口或多窗口未明确选择 |
| `7` | 请求／等待超时，或暂时无法确认操作结果 |

## 🔌 运行方式与边界

每个正常启动的窗口自动监听随机的 `127.0.0.1` 端口，并生成独立随机凭据。
Windows 描述文件位于 `%LOCALAPPDATA%\MarkPrompt\runtime\WINDOW_ID.json`；CLI 的窗口列表不输出凭据。
只接受本机连接；网络线程负责鉴权、收发和排队，所有 Tk、快照及命令处理都在窗口主线程。
关闭时删除本窗口描述文件；强退遗留文件在发现时被忽略。`--runtime-dir` 仅用于隔离测试或自定义部署。
此机制面向同一用户下的本机工具，不是远程网络服务，也不隔离已经控制同一用户账户的程序。

程序化构造可传 `MarkPromptApp(enable_bridge=False)` 关闭连接，或用 `bridge_directory=` 指定隔离目录。
普通 GUI 功能不因通信启动失败而停止，界面会提示实际连接错误。
