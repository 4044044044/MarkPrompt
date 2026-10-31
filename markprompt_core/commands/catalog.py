"""Command definitions shared by routing, completion, and help."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Alias:
    name: str
    prefix: str = ''
    adapter: str = ''

    def argument(self, value):
        if self.adapter == 'workspace_here' and not value:
            return 'here'
        if self.adapter == 'legacy_external':
            return 'links' if not value else ('link ' if value.split()[0].isdigit() else 'open ') + value
        return self.prefix + (' ' + value if value else '') if self.prefix else value


@dataclass(frozen=True)
class CommandSpec:
    name: str
    description_en: str
    description_zh: str
    category: str
    usage: str = ''
    requirement: str = 'any'
    navigation: bool = False
    keywords: tuple = ()
    aliases: tuple = ()
    blocked_states: tuple = ()
    refusal: str = ''
    inspection: bool = False

    def description(self, language):
        return self.description_zh if language == 'zh' else self.description_en


@dataclass(frozen=True)
class CommandRequest:
    spec: CommandSpec
    argument: str
    spelling: str


CATALOG = (
    CommandSpec('snapshot',
                'Observe session data for AI; optionally export JSON',
                '供 AI 读取的会话数据快照，可导出 JSON',
                'other', usage='[--full] [file.json]', inspection=True,
                keywords=(('--full', 'Include complete document text', '包含完整正文'),)),
    CommandSpec('open',
                'Open file, number, or bookmark',
                '打开文件、编号或书签',
                'folder',
                usage='[path|number|desktop|workspace|@bookmark]',
                keywords=(('desktop', 'Open the Desktop folder', '打开桌面文件夹'),
 ('workspace', 'Open the workspace root', '打开工作区根目录'),
 ('ws', 'Workspace shortcut', '工作区简写'))),
    CommandSpec('new',
                'Create a new Markdown note',
                '创建新 Markdown 笔记',
                'folder',
                usage='<title>',
                requirement='workspace',
                navigation=True),
    CommandSpec('jot',
                'Create a note and start quick-capture (append) mode',
                '新建便签并立刻进入速记（追加）模式',
                'folder',
                usage='<title>',
                requirement='workspace',
                navigation=True),
    CommandSpec('append',
                'Append once with text; no text enters capture mode',
                '带内容追加一次；无参数进入连续追加',
                'editing',
                usage='[text]',
                requirement='document',
                blocked_states=('search',),
                refusal='append_search_blocked'),
    CommandSpec('end',
                'End append mode',
                '退出追加模式',
                'other'),
    CommandSpec('line',
                'Jump to or replace a line by number',
                '按行号定位或替换该行',
                'editing',
                usage='<number> [text] | delete <number>',
                requirement='document',
                keywords=(('delete', 'Delete a line or its search hits', '删除整行或搜索命中'),),
                aliases=(Alias('linedel', prefix='delete'),)),
    CommandSpec('save',
                'Save current note to disk',
                '保存当前笔记到磁盘',
                'editing',
                requirement='document'),
    CommandSpec('preview',
                'Re-render current note',
                '重新渲染当前笔记',
                'other',
                aliases=(Alias('show'),)),
    CommandSpec('source',
                'Source view (raw text + line numbers)',
                '源码视图（原文+行号）',
                'other'),
    CommandSpec('view',
                'Toggle preview <-> source',
                '预览 ↔ 源码 一键切换',
                'other'),
    CommandSpec('title',
                "Change the note's # title (not the filename)",
                '修改笔记的 # 标题（不改文件名）',
                'editing',
                usage='<title>',
                requirement='document'),
    CommandSpec('saveas',
                'Save current note as a new file',
                '将当前笔记另存为新文件',
                'editing',
                usage='<name>',
                requirement='document'),
    CommandSpec('ls',
                'List directory contents',
                '列出目录内容',
                'folder',
                usage='[folder]',
                navigation=True),
    CommandSpec('cd',
                'Change directory',
                '切换目录',
                'folder',
                usage='<folder>',
                navigation=True),
    CommandSpec('up',
                'Go to parent directory',
                '返回上级目录',
                'folder',
                navigation=True),
    CommandSpec('tree',
                'Show two-level directory tree',
                '显示两层目录树',
                'folder'),
    CommandSpec('back',
                'Return to previous view',
                '返回上一视图',
                'folder',
                navigation=True),
    CommandSpec('home',
                'Return to home screen',
                '回到首页',
                'folder',
                navigation=True),
    CommandSpec('reload',
                'Refresh current file or directory',
                '刷新当前文件或目录',
                'other'),
    CommandSpec('find',
                'Search all workspace notes (case-insensitive), enter FIND>',
                '在工作区搜索全部笔记（不区分大小写），进入 FIND>',
                'folder',
                usage='<text>',
                aliases=(Alias('grep'),)),
    CommandSpec('search',
                'Search this note; -i ignores letter case',
                '搜索当前文档；-i 忽略大小写',
                'editing',
                usage='[-i] [text]',
                requirement='document',
                keywords=(('-i', 'Ignore letter case', '忽略大小写'),),
                aliases=(Alias('fsearch', prefix='-i'),)),
    CommandSpec('replace',
                'Replace all hits in current scope (after /search)',
                '替换当前作用域内全部命中（需先 /search）',
                'editing',
                usage='<text>',
                requirement='document'),
    CommandSpec('delete',
                'Delete all hits in current scope (after /search)',
                '删除当前作用域内全部命中（需先 /search）',
                'editing',
                requirement='document'),
    CommandSpec('recent',
                'Show recently opened files',
                '显示最近打开的文件',
                'folder',
                usage='[name]'),
    CommandSpec('files',
                'Filter filenames; enter a result number to open',
                '按文件名过滤，输入结果编号打开',
                'folder',
                usage='[name]'),
    CommandSpec('outline',
                'List headings or jump with /outline N',
                '列出标题，用 /outline 编号跳转',
                'other',
                usage='[number]',
                requirement='document'),
    CommandSpec('next',
                'Next search hit (F3)',
                '下一个搜索命中 (F3)',
                'editing'),
    CommandSpec('prev',
                'Previous search hit (Shift+F3)',
                '上一个搜索命中 (Shift+F3)',
                'editing'),
    CommandSpec('animation',
                'Enable or disable animation (on/off)',
                '开关动画 (on/off)',
                'other',
                usage='[on|off]',
                keywords=(('on', 'Enable animation', '开启动画'), ('off', 'Show content immediately', '立即显示内容'))),
    CommandSpec('tasks',
                'List all open tasks',
                '列出所有未完成任务',
                'other',
                requirement='workspace'),
    CommandSpec('check',
                'Toggle task completion',
                '切换任务完成状态',
                'editing',
                usage='<number>',
                requirement='document'),
    CommandSpec('tag',
                'Add or find tags',
                '添加或查找标签',
                'editing',
                usage='[add tags|find tag]',
                keywords=(('add', 'Add note tags', '添加标签'), ('find', 'Find notes by tag', '按标签查找'))),
    CommandSpec('tags',
                'List all tags with counts',
                '列出所有标签及计数',
                'other',
                requirement='workspace'),
    CommandSpec('archive',
                'Archive current note',
                '归档当前笔记',
                'folder',
                requirement='document'),
    CommandSpec('trash',
                'Move current note to trash',
                '将当前笔记移入回收站',
                'folder',
                requirement='document'),
    CommandSpec('restore',
                'Restore note from trash',
                '从回收站恢复笔记',
                'folder',
                usage='<name>',
                requirement='workspace',
                navigation=True),
    CommandSpec('import',
                'Import a Markdown file',
                '导入 Markdown 文件',
                'folder',
                usage='<path.md>',
                requirement='workspace',
                navigation=True),
    CommandSpec('export',
                'Export current note as txt',
                '导出当前笔记为纯文本',
                'folder',
                usage='txt',
                requirement='document',
                keywords=(('txt', 'Export plain text', '导出纯文本'),)),
    CommandSpec('reveal',
                'Open folder in file explorer',
                '在资源管理器中打开目录',
                'folder',
                requirement='document'),
    CommandSpec('bookmark',
                'Manage directory bookmarks',
                '管理目录书签',
                'folder',
                usage='[add name [folder]|list|remove name]',
                requirement='workspace',
                keywords=(('add', 'Add a bookmark', '添加书签'),
 ('list', 'List bookmarks', '列出书签'),
 ('remove', 'Remove a bookmark', '移除书签')),
                aliases=(Alias('bm'),)),
    CommandSpec('pwd',
                'Show current directory',
                '显示当前目录',
                'folder'),
    CommandSpec('status',
                'Show full status',
                '显示完整状态',
                'other'),
    CommandSpec('lang',
                'Switch language (en/zh)',
                '切换语言 (en/zh)',
                'other',
                usage='[en|zh]',
                keywords=(('en', 'English', '英文'), ('zh', 'Chinese', '中文'))),
    CommandSpec('theme',
                'Switch color theme (dark/light)',
                '切换配色主题 (dark/light)',
                'other',
                usage='[dark|light]',
                keywords=(('dark', 'Black terminal theme', '黑色终端主题'), ('light', 'Warm paper theme', '暖色纸感主题'))),
    CommandSpec('dark',
                'Use the dark theme',
                '使用暗色主题',
                'other'),
    CommandSpec('light',
                'Use the light theme',
                '使用浅色主题',
                'other'),
    CommandSpec('clear',
                'Clear screen',
                '清屏',
                'other'),
    CommandSpec('help',
                'Show command help',
                '显示命令帮助',
                'other',
                aliases=(Alias('?'),)),
    CommandSpec('quit',
                'Exit MarkPrompt',
                '退出 MarkPrompt',
                'other'),
    CommandSpec('external',
                'Open current file or document links externally',
                '外部打开当前文件、链接或路径',
                'folder',
                usage='[file|links|link N [index]|open target]',
                requirement='document',
                keywords=(('file', 'Open current file externally', '外部打开当前文件'),
 ('links', 'List document links', '列出文内链接'),
 ('link', 'Open a link by line', '按行号打开链接'),
 ('open', 'Open a target externally', '外部打开指定目标')),
                aliases=(Alias('ext', adapter='legacy_external'),)),
    CommandSpec('workspace',
                'Set workspace folder or use here',
                '设置工作区，here 采用当前目录',
                'folder',
                usage='<folder|here>',
                navigation=True,
                keywords=(('here', 'Use the current directory', '采用当前浏览目录'),),
                aliases=(Alias('ws'), Alias('setws', adapter='workspace_here'),)),
    CommandSpec('undo',
                'Undo the last edit',
                '撤销上一步编辑',
                'editing',
                requirement='document'),
    CommandSpec('redo',
                'Redo an edit',
                '重做上一步编辑',
                'editing',
                requirement='document'),
 )


class CommandRegistry:
    def __init__(self, catalog):
        self.specs = {}
        self.aliases = {}
        for spec in catalog:
            if spec.name in self.specs:
                raise ValueError('Duplicate command: ' + spec.name)
            self.specs[spec.name] = spec
            for alias in spec.aliases:
                if alias.name in self.aliases:
                    raise ValueError('Duplicate alias: ' + alias.name)
                self.aliases[alias.name] = (spec, alias)
        if set(self.specs) & set(self.aliases):
            raise ValueError('An alias shadows a primary command')

    def names(self):
        return sorted(set(self.specs) | set(self.aliases))

    def parse(self, value):
        spelling, _, argument = value[1:].partition(' ')
        spelling, argument = spelling.lower(), argument.strip()
        if spelling in self.aliases:
            spec, alias = self.aliases[spelling]
            return CommandRequest(spec, alias.argument(argument), spelling)
        spec = self.specs.get(spelling)
        return CommandRequest(spec, argument, spelling) if spec else None

    def descriptions(self, language):
        result = {name: spec.description(language) for name, spec in self.specs.items()}
        result.update({name: spec.description(language) for name, (spec, alias) in self.aliases.items()})
        return result

    def inspection(self, value):
        if '\n' in value or not value.startswith('/'):
            return None
        request = self.parse(value)
        return request if request and request.spec.inspection else None

    def keywords(self, language):
        index = 2 if language == 'zh' else 1
        return {spec.name: [(row[0], row[index]) for row in spec.keywords]
                for spec in self.specs.values() if spec.keywords}


REGISTRY = CommandRegistry(CATALOG)

GUI_COMMANDS = frozenset({'preview', 'view', 'theme', 'dark', 'light', 'animation', 'clear', 'external', 'reveal'})
