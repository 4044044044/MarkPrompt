"""Language discovery, message validation, and shared English fallback."""
from dataclasses import dataclass
from importlib import import_module
import pkgutil
import re
from types import MappingProxyType

DEFAULT_LANGUAGE = 'en'
_PLACEHOLDER = re.compile(r'%(?:\([^)]+\))?[#0 +\-]*(?:\d+|\*)?(?:\.(?:\d+|\*))?[hlL]?[diouxXeEfFgGcrsa%]')


def _signature(text):
    tokens = []
    offset = 0
    while '%' in text[offset:]:
        start = text.index('%', offset)
        match = _PLACEHOLDER.match(text, start)
        if match is None:
            raise ValueError('Invalid format placeholder')
        if match.group() != '%%':
            tokens.append(match.group())
        offset = match.end()
    return tuple(tokens)


@dataclass(frozen=True)
class Language:
    code: str
    name: str
    messages: object


class LanguageRegistry:
    """Store validated translations; missing messages use the English baseline."""

    def __init__(self):
        self._languages = {}

    def register(self, code, name, messages):
        if not isinstance(code, str) or not re.fullmatch(r'[a-z][a-z0-9_-]*', code):
            raise ValueError('Invalid language code')
        if code in self._languages:
            raise ValueError('Duplicate language: ' + code)
        if not isinstance(name, str) or not name.strip() or not isinstance(messages, dict):
            raise ValueError('A language needs a name and message dictionary')
        if code != DEFAULT_LANGUAGE and DEFAULT_LANGUAGE not in self._languages:
            raise ValueError('Register English before translations')
        baseline = self._languages.get(DEFAULT_LANGUAGE)
        for key, value in messages.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ValueError('Message keys and values must be strings')
            _signature(value)
            if baseline and (key not in baseline.messages or _signature(value) != _signature(baseline.messages[key])):
                raise ValueError('Unknown key or mismatched placeholders: ' + code + '/' + key)
        self._languages[code] = Language(code, name, MappingProxyType(dict(messages)))

    def normalize(self, code):
        return code if isinstance(code, str) and code in self._languages else DEFAULT_LANGUAGE

    def codes(self):
        return tuple(self._languages)

    def languages(self):
        return tuple(self._languages.values())

    def text(self, language, key):
        current = self._languages[self.normalize(language)]
        return current.messages.get(key, self._languages[DEFAULT_LANGUAGE].messages.get(key, key))


def discover():
    from . import locales
    registry = LanguageRegistry()
    names = sorted(info.name for info in pkgutil.iter_modules(locales.__path__) if not info.name.startswith('_'))
    names.remove(DEFAULT_LANGUAGE)
    for name in [DEFAULT_LANGUAGE] + names:
        module = import_module(locales.__name__ + '.' + name)
        registry.register(module.CODE, module.NAME, module.MESSAGES)
    return registry


LANGUAGES = discover()


def tr(language, key):
    return LANGUAGES.text(language, key)
