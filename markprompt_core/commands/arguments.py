"""Validate command arguments before changing application state."""
import re
from markprompt_core.localization import LANGUAGES, tr


def validate(request, language="en"):
    def usage(value):
        return tr(language, "argument.usage") % value
    name, value = request.spec.name, request.argument
    required = {'workspace', 'cd', 'new', 'jot', 'line', 'title', 'saveas', 'find', 'check', 'restore', 'import'}
    if name in required and not value:
        return tr(language, "argument.required") % (name, request.spec.usage)
    if name == 'line':
        first, _, rest = value.partition(' ')
        if first == 'delete':
            if not re.fullmatch(r'[0-9]+', rest.strip()):
                return usage('/line delete <number>')
        elif not re.fullmatch(r'[0-9]+', first):
            return usage('/line <number> [text]')
    if name in {'check', 'outline'} and value and not re.fullmatch(r'[0-9]+', value):
        return tr(language, "argument.number") % name
    if name == 'export' and value.lower() != 'txt':
        return usage('/export txt')
    if name == 'animation' and value not in {'', 'on', 'off'}:
        return usage('/animation [on|off]')
    if name == 'theme' and value not in {'', 'dark', 'light'}:
        return usage('/theme [dark|light]')
    if name == 'lang' and value and value not in LANGUAGES.codes():
        return usage('/lang [' + '|'.join(LANGUAGES.codes()) + ']')
    if name == 'search':
        if value.startswith('-- '):
            value = value[3:]
        elif value == '-i' or value.startswith('-i '):
            value = value[2:].strip()
        elif value == '--ignore-case' or value.startswith('--ignore-case '):
            value = value[len('--ignore-case'):].strip()
        elif value.startswith('-'):
            return usage('/search [-i] [text]')
        if len(value.split()) >= 2:
            return tr(language, "argument.search_one")
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
