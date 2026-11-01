"""Run shared command actions in a headless session."""
from dataclasses import asdict
from pathlib import Path

from markprompt_core.commands.actions import CommandActions
from markprompt_core.commands.arguments import validate, split_chain
from markprompt_core.commands.catalog import REGISTRY, GUI_COMMANDS
from markprompt_core.documents.content import ContentMixin, search_hits
from markprompt_core.documents.session import DocumentAdapter, DocumentSession
from markprompt_core.search.session import SearchAdapter, SearchSession
from markprompt_core.application.navigation import NavigationMemory
from markprompt_core.localization import LANGUAGES, tr
from markprompt_core.commands.routing import CommandRouter
from markprompt_core.application.states import BusinessStates
from markprompt_core.storage.local import StorageError, StorageServices
from markprompt_core.ui.storage_adapter import StorageMixin
from markprompt_core.application.workflows import WorkflowMixin
from markprompt_core.commands.presentation import bind_presentation

GUI_ONLY = GUI_COMMANDS
ROUTER = CommandRouter(REGISTRY)


def capabilities(language='en'):
    keywords = REGISTRY.keywords(language)
    return [{'name': spec.name, 'description': spec.description(language), 'usage': spec.usage,
             'category': spec.category, 'cli_supported': spec.name not in GUI_ONLY,
             'aliases': [alias.name for alias in spec.aliases],
             'keywords': [row[0] for row in keywords.get(spec.name, ())]}
            for spec in sorted(REGISTRY.specs.values(), key=lambda spec: spec.name)]


class Session(SearchAdapter, DocumentAdapter, ContentMixin, StorageMixin, WorkflowMixin, CommandActions):
    background_search = False
    snapshot_export_default = False

    def __init__(self, workspace=None, config_path=None, storage=None):
        self.storage = storage if storage is not None else StorageServices()
        self.document = DocumentSession(self.storage.documents)
        self.search = SearchSession(self.storage.documents)
        self.presentation = bind_presentation(self)
        self.states = BusinessStates()
        self.navigation = NavigationMemory()
        self.workspace = self.current_dir = self.current_file = None
        self.config_path = Path(config_path).resolve() if config_path is not None else None
        self._preferences = {}
        self.language = LANGUAGES.normalize(self._load_config().get('language'))
        self.view_mode = 'console'
        self.listed_items, self.recent_files = {}, []
        self.console_history, self.console_rows, self.console_title = [], [], ''
        self._find_after = None
        self._last_position_line = 1
        self._navigation_bypass = False
        self._navigation_tail = []
        self._drop_open_pending = False
        self._pending_navigation = None
        self.closed = False
        self._notices, self._data, self._errors = [], {}, []
        self._active_command = ''
        if workspace is not None:
            root = Path(workspace).expanduser().resolve(strict=True)
            self.storage.files.list_directory(root)
            self.workspace = self.current_dir = root

    def _t(self, key):
        return tr(self.language, 'ui.' + key)

    def _command_data(self, **data):
        self._data.update(data)

    def _command_error(self, code, message):
        self._errors.append({'code': code, 'message': str(message)})
        self._notices.append({'level': 'error', 'message': str(message)})

    def _report_storage_error(self, error):
        self.presentation.error(error.code, str(error))

    def _append_notice(self, message, tag):
        self._notices.append({'level': tag, 'message': message})
        if tag not in {'warning', 'error'}:
            return
        benign = (self.confirm_mode or self._active_command in {'save', 'undo', 'redo'} or
                  (self._active_command == 'search' and self.search_mode and self.search_term is None) or
                  (self._active_command == 'find' and self.find_mode and self.current_file is None))
        if tag == 'error' or not benign:
            self._errors.append({'code': 'command_failed', 'message': message})

    def _drop_notice(self, key, detail=''):
        self._command_error(key, self._t(key) + (' ' + detail if detail else ''))

    def _needs_workspace(self):
        if self.workspace is not None:
            return False
        self._command_error('workspace_needed', self._t('workspace_needed'))
        return True

    def _load_config(self):
        return super()._load_config() if self.config_path is not None else dict(self._preferences)

    def _save_config(self, data):
        if self.config_path is not None:
            try:
                self.storage.preferences.save(self.config_path, data)
                return True
            except StorageError as error:
                self._report_storage_error(error)
                return False
        self._preferences = dict(data)
        return True

    def _persist_workspace(self, path):
        config = self._load_config()
        config.update(version=1, workspace=str(path))
        self._save_config(config)

    def _command_lang(self, argument):
        if argument and not self._set_language(argument):
            return
        self._command_data(language=self.language, languages=[{'code': item.code, 'name': item.name} for item in LANGUAGES.languages()])

    def _recovery_sync(self):
        # Keep CLI drafts separate from the GUI's recovery file.
        return None

    def _recovery_clear(self):
        return None

    def _present_prompt(self):
        return None  # The output adapter derives the prompt from states.top.

    def _clear_search_highlights(self):
        return None  # Headless search results use source offsets.

    def _apply_search_highlights(self):
        return len(search_hits(self.buffer_text, self.search_term, self.search_fuzzy))

    def _set_header(self, text):
        self.console_title = text

    def _show_console(self, title, rows):
        self.view_mode, self.console_title = 'console', title
        self.console_rows = [row[0] if isinstance(row, tuple) else row for row in rows]
        self._command_data(rows=list(self.console_rows))
        self.console_history.extend((str(row), None) for row in self.console_rows)

    def _show_directory(self, path, change_directory=True):
        if not self._confirm_navigation(lambda: self._show_directory(path, change_directory)):
            return False
        try:
            items = self.storage.files.list_directory(path)
        except StorageError as error:
            self._report_storage_error(error)
            return False
        if self.current_file is not None:
            self._clear_mode_stack()
            self.navigation.clear()
        if change_directory:
            self.current_dir = Path(path)
        self.current_file = None
        self.listed_items = dict(enumerate(items, 1))
        self._show_console('DIR ' + str(path), [str(item.name) for item in items])
        return True

    def _display_document(self, path, source=False, scroll_to=None, loaded_text=None):
        path = Path(path)
        if path.suffix.lower() not in {'.md', '.txt'} or not path.is_file():
            self._command_error('not_found', str(path))
            return
        if not self._confirm_navigation(lambda: self._display_document(path, source, scroll_to), target=path):
            return
        different_note = self.current_file != path
        prepared = self._prepare_document(path, loaded_text)
        if prepared is None:
            return
        content, _discarded = prepared
        if different_note:
            self._clear_mode_stack()
            self._last_position_line = 1
        self.current_file, self.current_dir = path, path.parent
        self.view_mode = 'source' if source or path.suffix.lower() == '.txt' else 'read'
        self.recent_files = ([path] + [item for item in self.recent_files if item != path])[:12]
        if scroll_to is not None:
            self._scroll_to_line(scroll_to)

    def _show_markdown(self, path, scroll_to=None, loaded_text=None):
        self._display_document(path, False, scroll_to, loaded_text)

    def _show_source(self, path, scroll_to=None, loaded_text=None):
        self._display_document(path, True, scroll_to, loaded_text)

    def _show_welcome(self, reset=False):
        if not self._confirm_navigation(self._show_welcome):
            return
        self.current_file = None
        self.view_mode, self.console_title = 'console', 'HOME'

    def _workspace_files(self):
        return list(self.storage.files.scan(self.workspace))

    def _scroll_to_line(self, number):
        self._last_position_line = number

    def _navigation_position(self):
        return 0.0, str(self._last_position_line)

    def _present_search_return(self, point):
        self.view_mode, self.console_title = 'console', 'FIND ' + point.term
        self.console_rows = [str(row[0]) for row in point.history]
        self._last_position_line = int(point.top_index)

    def _restore_search_scroll(self, value):
        return None

    def _confirm_navigation(self, action, target=None, defer=False):
        if (not self.buffer_dirty or self._navigation_bypass or
                (target is not None and Path(target) == self.buffer_path)):
            return True
        if self._pending_navigation is None:
            self._pending_navigation = action
        return False

    def _answer_navigation(self, value):
        if value not in {'save', 'discard', 'cancel'}:
            self._command_error('confirmation_required', self._t('confirm_reply'))
            return
        if value == 'cancel':
            self._pending_navigation = None
            self._navigation_tail = []
            return
        if value == 'save' and not self._flush_buffer():
            return
        action, self._pending_navigation = self._pending_navigation, None
        self._navigation_bypass = True
        previous = self.buffer_path
        try:
            action()
        finally:
            self._navigation_bypass = False
        if self.current_file is None and self.buffer_path == previous:
            self.document.close(discard=True)
        if self.closed and value == 'discard':
            self.document.close(discard=True)
            self.current_file = None

    def _on_close(self):
        if self._confirm_navigation(self._quit_app):
            self._quit_app()

    def _quit_app(self):
        self.closed = True
        self.search.close()

    @property
    def pending(self):
        if self._pending_navigation:
            return {'kind': 'unsaved_navigation', 'choices': ['save', 'discard', 'cancel']}
        if self.confirm_mode:
            return {'kind': 'overwrite', 'choices': ['y', 'n'],
                    'target': self.states.confirmation.payload.get('target')}
        return None

    def snapshot(self, include_text=False):
        document = None
        if self.current_file is not None:
            document = {'path': str(self.current_file), 'dirty': self.buffer_dirty,
                        'dirty_lines': sorted(self.dirty_lines),
                        'version': self._buffer_disk_version.hex() if self._buffer_disk_version else None,
                        'lines': len((self.buffer_text or '').splitlines())}
            if include_text:
                document['text'] = self.buffer_text
        return {'language': self.language, 'workspace': str(self.workspace) if self.workspace else None,
                'directory': str(self.current_dir) if self.current_dir else None,
                'document': document, 'business': [frame.kind for frame in self.states.frames],
                'prompt': ('CONFIRM' if self._pending_navigation else
                           self.states.top.kind.upper() if self.states.top else 'MARK') + '>',
                'search': {'term': self.search_term, 'ignore_case': self.search_fuzzy,
                           'scope': self.search_scope, 'line': self.search_scope_line},
                'find': {'term': self.find_term, 'matching_files': len(self.find_file_hits)},
                'position_line': self._last_position_line, 'pending': self.pending, 'closed': self.closed}

    def _snapshot_surface(self):
        return {'kind': 'cli', 'pending': self.pending, 'position_line': self._last_position_line,
                'viewport': {'available': False, 'reason': 'headless_session'}, 'selection': None,
                'input': None, 'console': {'title': self.console_title,
                'rows': list(self.console_rows[:200]), 'total': len(self.console_rows),
                'truncated': len(self.console_rows) > 200}}

    def _dispatch(self, value):
        language_request = REGISTRY.parse(value) if value.startswith('/') else None
        if language_request and language_request.spec.name == 'lang' and len(split_chain(value)) == 1:
            self._active_command = 'lang'
            ROUTER.dispatch(self, value)
            return
        if REGISTRY.inspection(value):
            self._active_command = 'snapshot'
            ROUTER.dispatch(self, value)
            return
        if self._pending_navigation:
            self._answer_navigation(value)
            return
        if '\n' in value:
            if self.confirm_mode:
                self._handle_confirm(value)
            else:
                self._append_content(value)
            return
        segments = split_chain(value)
        for index, segment in enumerate(segments):
            request = REGISTRY.parse(segment) if segment.startswith('/') and not self.confirm_mode else None
            if not segment.startswith('/') and not self.confirm_mode:
                self._active_command = {'search': 'search', 'find': 'find', 'append': 'append',
                                        'open': 'open'}.get(self.states.active, 'open')
                if self.states.active == 'search':
                    syntax = REGISTRY.parse('/search ' + ('-i ' if self.search_fuzzy else '') + segment)
                    error = validate(syntax, self.language)
                    if error:
                        self._command_error('invalid_arguments', error)
                        break
            if request:
                self._active_command = request.spec.name
                if request.spec.name in GUI_ONLY:
                    self._command_error('gui_required', self._t('gui_required') + request.spec.name)
                    break
                error = validate(request, self.language)
                if error:
                    self._command_error('invalid_arguments', error)
                    break
            ROUTER.dispatch(self, segment)
            if self.pending:
                self._navigation_tail = segments[index + 1:]
                break
            if self._errors or self.closed:
                break

    def execute(self, value, include_text=False):
        self._notices, self._errors, self._data = [], [], {}
        self._active_command = ''
        effect_cursor = self.presentation.cursor
        before = self.buffer_text
        try:
            if self.closed and not REGISTRY.inspection(value):
                self._command_error('session_closed', self._t('session_closed'))
            elif value.strip():
                was_pending = self.pending
                self._dispatch(value.strip() if '\n' not in value else value)
                if was_pending and not self.pending and value.strip().lower() in {'n', 'cancel'}:
                    self._errors = [error for error in self._errors if error['code'] != 'command_failed']
                if was_pending and not self.pending and not self._errors:
                    tail, self._navigation_tail = self._navigation_tail, []
                    for item in tail:
                        self._dispatch(item)
                        if self._errors or self.pending:
                            break
        except StorageError as error:
            self._report_storage_error(error)
        except (OSError, ValueError) as error:
            self._command_error('command_failed', str(error))
        if self._active_command == 'source' and self.current_file:
            self._data.update(path=str(self.current_file), text=self.buffer_text)
        if self._active_command in {'search', 'line', 'replace', 'delete', 'next', 'prev'}:
            self._data['hits'] = [asdict(hit) for hit in search_hits(self.buffer_text, self.search_term, self.search_fuzzy)]
        if self._active_command in {'open', 'ls', 'cd', 'up', 'workspace', 'back', 'files', 'recent'}:
            self._data['files'] = [{'number': n, 'path': str(path), 'name': path.name,
                                   'type': 'directory' if path.is_dir() else 'file',
                                   'match': path in self.find_file_hits}
                                  for n, path in self.listed_items.items()]
        self._data['changed'] = self.buffer_text != before
        self._data.setdefault('rows', [])
        error = self._errors[0] if self._errors else None
        effects = self.presentation.result_since(effect_cursor)
        return {'command': value, 'ok': error is None,
                'status': 'error' if error else 'needs_confirmation' if self.pending else 'ok',
                'code': error['code'] if error else 'confirmation_required' if self.pending else 'ok',
                'message': error['message'] if error else '', 'data': self._data,
                'notices': list(self._notices), 'effects': effects.as_data(), 'effects_omitted': effects.omitted,
                'state': self.snapshot(include_text)}


