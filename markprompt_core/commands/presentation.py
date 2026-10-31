"""Deliver command results to the window or headless adapter."""
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Effect:
    sequence: int
    kind: str
    payload: dict


@dataclass(frozen=True)
class CommandResult:
    effects: tuple
    omitted: int = 0

    def as_data(self):
        return [{'kind': effect.kind, 'payload': dict(effect.payload)} for effect in self.effects]


@dataclass(frozen=True)
class PresentationPorts:
    notice: Callable
    error: Callable
    data: Callable
    document: Callable
    source: Callable
    console: Callable
    directory: Callable
    home: Callable
    prompt: Callable
    header: Callable
    scroll: Callable
    position: Callable
    search_return: Callable
    restore_scroll: Callable
    highlights: Callable
    clear_highlights: Callable
    apply_theme: Callable
    clear: Callable
    close: Callable
    later: Callable
    cancel_later: Callable
    history: Callable
    view: Callable
    theme: Callable
    line: Callable
    confirm: Callable
    overwrite: Callable

    def __post_init__(self):
        for field in fields(self):
            if not callable(getattr(self, field.name)):
                raise TypeError('Presentation callback must be callable: ' + field.name)


def unavailable(*args, **kwargs):
    raise RuntimeError('This presentation operation requires the native UI')


def bind_presentation(app, gui=False):
    """Bind presentation callbacks for the GUI or headless adapter."""
    ports = PresentationPorts(
        notice=app._append_notice, error=app._command_error, data=app._command_data,
        document=app._show_markdown, source=app._show_source, console=app._show_console,
        directory=app._show_directory, home=app._show_welcome, prompt=app._present_prompt,
        header=app._set_header, scroll=app._scroll_to_line, position=app._navigation_position,
        search_return=app._present_search_return, restore_scroll=app._restore_search_scroll,
        highlights=app._apply_search_highlights, clear_highlights=app._clear_search_highlights,
        apply_theme=app._apply_theme if gui else unavailable,
        clear=app._present_clear if gui else unavailable, close=app._on_close,
        later=app.after if gui else unavailable,
        cancel_later=app._cancel_scheduled if gui else unavailable,
        history=lambda: tuple(app.console_history), view=lambda: app.view_mode,
        theme=lambda: app.theme_name if gui else None, line=lambda: app._last_position_line,
        confirm=app._confirm_navigation, overwrite=app._ask_overwrite)
    return Presentation(ports)


class Presentation:
    """Record effects and deliver them to the bound adapter.

    An effect records a request. Check command errors and resulting state to confirm it
    succeeded.
    """
    LIMIT = 200

    def __init__(self, ports):
        self.ports = ports
        self.cursor = 0
        self._effects = deque(maxlen=self.LIMIT)
        self._captures = []

    @contextmanager
    def capture(self):
        result = {'data': {}, 'notices': [], 'errors': []}
        self._captures.append(result)
        try:
            yield result
        finally:
            self._captures = [item for item in self._captures if item is not result]

    def _record(self, kind, **payload):
        self.cursor += 1
        self._effects.append(Effect(self.cursor, kind, payload))
        for result in self._captures:
            if kind == 'notice':
                result['notices'].append(dict(payload))
                if payload.get('code'):
                    result['errors'].append({'code': payload['code'], 'message': payload['message']})
            elif kind == 'error':
                result['errors'].append(dict(payload))

    def result_since(self, cursor):
        effects = tuple(effect for effect in self._effects if effect.sequence > cursor)
        return CommandResult(effects, max(0, self.cursor - cursor - len(effects)))

    def notice(self, message, level, code=None):
        self._record('notice', message=str(message)[:1000], level=level, **({'code': code} if code else {}))
        return self.ports.notice(message, level)

    def error(self, code, message):
        self._record('error', code=code, message=str(message)[:1000])
        return self.ports.error(code, message)

    def data(self, **data):
        self._record('data', keys=sorted(data))
        for result in self._captures:
            result['data'].update(data)
        return self.ports.data(**data)

    def document(self, path, scroll_to=None, loaded_text=None):
        self._record('document_view_requested', path=str(path), view='read', line=scroll_to)
        return self.ports.document(path, scroll_to=scroll_to, loaded_text=loaded_text)

    def source(self, path, scroll_to=None, loaded_text=None):
        self._record('document_view_requested', path=str(path), view='source', line=scroll_to)
        return self.ports.source(path, scroll_to=scroll_to, loaded_text=loaded_text)

    def console(self, title, rows):
        self._record('console_requested', title=str(title)[:1000])
        return self.ports.console(title, rows)

    def directory(self, path, change_directory=True):
        self._record('directory_requested', path=str(path), change_directory=change_directory)
        return self.ports.directory(path, change_directory)

    def home(self, reset=False):
        self._record('home_requested', reset=reset)
        return self.ports.home(reset)

    def prompt(self):
        self._record('prompt_refresh_requested')
        return self.ports.prompt()

    def header(self, text):
        self._record('header_requested', text=str(text)[:1000])
        return self.ports.header(text)

    def scroll(self, line):
        self._record('scroll_requested', line=line)
        return self.ports.scroll(line)

    def position(self):
        return self.ports.position()

    def search_return(self, point):
        self._record('search_return_requested', term=point.term)
        return self.ports.search_return(point)

    def restore_scroll(self, fraction):
        self._record('scroll_restore_requested', fraction=fraction)
        return self.ports.restore_scroll(fraction)

    def highlights(self):
        self._record('highlights_refresh_requested')
        return self.ports.highlights()

    def clear_highlights(self):
        self._record('highlights_clear_requested')
        return self.ports.clear_highlights()

    def apply_theme(self, name):
        self._record('theme_requested', name=name)
        return self.ports.apply_theme(name)

    def clear(self):
        self._record('clear_requested')
        return self.ports.clear()

    def close(self):
        self._record('close_requested')
        return self.ports.close()

    def confirm(self, action, target=None, defer=False):
        return self.ports.confirm(action, target=target, defer=defer)

    def overwrite(self, target, on_yes):
        self._record('overwrite_confirmation_requested', target=str(Path(target)))
        return self.ports.overwrite(target, on_yes)

    @property
    def view(self):
        return self.ports.view()

    @property
    def theme(self):
        return self.ports.theme()

    @property
    def line(self):
        return self.ports.line()

    def history(self):
        return self.ports.history()

    def later(self, delay, callback):
        return self.ports.later(delay, callback)

    def cancel_later(self, token):
        return self.ports.cancel_later(token)
