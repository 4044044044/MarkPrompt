"""Validate command arguments before changing application state."""
import re


def validate(request):
    name, value = request.spec.name, request.argument
    required = {'workspace', 'cd', 'new', 'jot', 'line', 'title', 'saveas', 'find', 'check', 'restore', 'import'}
    if name in required and not value:
        return 'Required argument: /%s %s' % (name, request.spec.usage)
    if name == 'line':
        first, _, rest = value.partition(' ')
        if first == 'delete':
            if not re.fullmatch(r'[0-9]+', rest.strip()):
                return 'Usage: /line delete <number>'
        elif not re.fullmatch(r'[0-9]+', first):
            return 'Usage: /line <number> [text]'
    if name in {'check', 'outline'} and value and not re.fullmatch(r'[0-9]+', value):
        return 'Expected a number: /' + name
    if name == 'export' and value.lower() != 'txt':
        return 'Usage: /export txt'
    if name == 'animation' and value not in {'', 'on', 'off'}:
        return 'Usage: /animation [on|off]'
    if name == 'theme' and value not in {'', 'dark', 'light'}:
        return 'Usage: /theme [dark|light]'
    if name == 'lang' and value not in {'', 'en', 'zh'}:
        return 'Usage: /lang [en|zh]'
    if name == 'search':
        if value.startswith('-- '):
            value = value[3:]
        elif value == '-i' or value.startswith('-i '):
            value = value[2:].strip()
        elif value == '--ignore-case' or value.startswith('--ignore-case '):
            value = value[len('--ignore-case'):].strip()
        elif value.startswith('-'):
            return 'Usage: /search [-i] [text]'
        if len(value.split()) >= 2:
            return 'Search expects one keyword; replacement uses /replace'
    return None


def split_chain(value):
    if not value.startswith('/'):
        return [value]
    pattern = re.compile(r'(?:^|\s)/(replace|delete|end)(?=\s|$)')
    segments, last = [], 0
    for match in pattern.finditer(value):
        slash = value.index('/', match.start())
        if slash > last:
            segments.append(value[last:slash].strip())
        last = slash
    segments.append(value[last:].strip())
    return [part for part in segments if part]
