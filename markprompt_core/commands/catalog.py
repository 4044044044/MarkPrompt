"""Command definitions shared by routing, completion, and help."""
from dataclasses import dataclass
from markprompt_core.localization import LANGUAGES, tr


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
        return tr(language, 'command.' + self.name)


@dataclass(frozen=True)
class CommandRequest:
    spec: CommandSpec
    argument: str
    spelling: str


CATALOG = (
    CommandSpec('snapshot', 'other',
                usage='[--full] [file.json]',
                inspection=True,
                keywords=('--full',)),
    CommandSpec('open', 'folder',
                usage='[path|number|desktop|workspace|@bookmark]',
                keywords=('desktop', 'workspace', 'ws')),
    CommandSpec('new', 'folder',
                usage='<title>',
                requirement='workspace',
                navigation=True),
    CommandSpec('jot', 'folder',
                usage='<title>',
                requirement='workspace',
                navigation=True),
    CommandSpec('append', 'editing',
                usage='[text]',
                requirement='document',
                blocked_states=('search',),
                refusal='append_search_blocked'),
    CommandSpec('end', 'other'),
    CommandSpec('line', 'editing',
                usage='<number> [text] | delete <number>',
                requirement='document',
                keywords=('delete',),
                aliases=(Alias('linedel', prefix='delete'),)),
    CommandSpec('save', 'editing',
                requirement='document'),
    CommandSpec('preview', 'other',
                aliases=(Alias('show'),)),
    CommandSpec('source', 'other'),
    CommandSpec('view', 'other'),
    CommandSpec('title', 'editing',
                usage='<title>',
                requirement='document'),
    CommandSpec('saveas', 'editing',
                usage='<name>',
                requirement='document'),
    CommandSpec('ls', 'folder',
                usage='[folder]',
                navigation=True),
    CommandSpec('cd', 'folder',
                usage='<folder>',
                navigation=True),
    CommandSpec('up', 'folder',
                navigation=True),
    CommandSpec('tree', 'folder'),
    CommandSpec('back', 'folder',
                navigation=True),
    CommandSpec('home', 'folder',
                navigation=True),
    CommandSpec('reload', 'other'),
    CommandSpec('find', 'folder',
                usage='<text>',
                aliases=(Alias('grep'),)),
    CommandSpec('search', 'editing',
                usage='[-i] [text]',
                requirement='document',
                keywords=('-i',),
                aliases=(Alias('fsearch', prefix='-i'),)),
    CommandSpec('replace', 'editing',
                usage='<text>',
                requirement='document'),
    CommandSpec('delete', 'editing',
                requirement='document'),
    CommandSpec('recent', 'folder',
                usage='[name]'),
    CommandSpec('files', 'folder',
                usage='[name]'),
    CommandSpec('outline', 'other',
                usage='[number]',
                requirement='document'),
    CommandSpec('next', 'editing'),
    CommandSpec('prev', 'editing'),
    CommandSpec('animation', 'other',
                usage='[on|off]',
                keywords=('on', 'off')),
    CommandSpec('tasks', 'other',
                requirement='workspace'),
    CommandSpec('check', 'editing',
                usage='<number>',
                requirement='document'),
    CommandSpec('tag', 'editing',
                usage='[add tags|find tag]',
                keywords=('add', 'find')),
    CommandSpec('tags', 'other',
                requirement='workspace'),
    CommandSpec('archive', 'folder',
                requirement='document'),
    CommandSpec('trash', 'folder',
                requirement='document'),
    CommandSpec('restore', 'folder',
                usage='<name>',
                requirement='workspace',
                navigation=True),
    CommandSpec('import', 'folder',
                usage='<path.md>',
                requirement='workspace',
                navigation=True),
    CommandSpec('export', 'folder',
                usage='txt',
                requirement='document',
                keywords=('txt',)),
    CommandSpec('reveal', 'folder',
                requirement='document'),
    CommandSpec('bookmark', 'folder',
                usage='[add name [folder]|list|remove name]',
                requirement='workspace',
                keywords=('add', 'list', 'remove'),
                aliases=(Alias('bm'),)),
    CommandSpec('pwd', 'folder'),
    CommandSpec('status', 'other'),
    CommandSpec('lang', 'other',
                usage='[code]'),
    CommandSpec('theme', 'other',
                usage='[dark|light]',
                keywords=('dark', 'light')),
    CommandSpec('dark', 'other'),
    CommandSpec('light', 'other'),
    CommandSpec('clear', 'other'),
    CommandSpec('help', 'other',
                aliases=(Alias('?'),)),
    CommandSpec('quit', 'other'),
    CommandSpec('external', 'folder',
                usage='[file|links|link N [index]|open target]',
                requirement='document',
                keywords=('file', 'links', 'link', 'open'),
                aliases=(Alias('ext', adapter='legacy_external'),)),
    CommandSpec('workspace', 'folder',
                usage='<folder|here>',
                navigation=True,
                keywords=('here',),
                aliases=(Alias('ws'), Alias('setws', adapter='workspace_here'),)),
    CommandSpec('undo', 'editing',
                requirement='document'),
    CommandSpec('redo', 'editing',
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
        result = {spec.name: [(token, tr(language, 'keyword.' + spec.name + '.' + token))
                              for token in spec.keywords]
                  for spec in self.specs.values() if spec.keywords}
        result['lang'] = [(item.code, item.name) for item in LANGUAGES.languages()]
        return result



REGISTRY = CommandRegistry(CATALOG)

GUI_COMMANDS = frozenset({'preview', 'view', 'theme', 'dark', 'light', 'animation', 'clear', 'external', 'reveal'})
