"""Apply mode changes to the window and command prompt."""
from markprompt_core.application.states import ModeFrame, StateError
from uuid import uuid4

PROMPTS = {
    'confirm': ('CONFIRM>', 'error'), 'search': ('SEARCH>', 'command'),
    'append': ('APPEND>', 'string'), 'open': ('OPEN>', 'success'),
    'find': ('FIND>', 'command'),
}


class WorkflowMixin:
    @property
    def mode_stack(self):
        return self.states.frames

    @property
    def append_mode(self):
        return self.states.has('append')

    @property
    def open_mode(self):
        return self.states.has('open')

    @property
    def search_mode(self):
        return self.states.has('search')

    @property
    def find_mode(self):
        return self.states.has('find')

    @property
    def confirm_mode(self):
        return self.states.has('confirm')

    def _has_mode(self, kind):
        return self.states.has(kind)

    def _top_mode(self):
        return self.states.top

    def _push_mode(self, kind, **payload):
        self.states.push(kind, **payload)

    def _pop_mode(self):
        return self.states.pop()

    def _remove_mode(self, kind):
        self.states.remove(kind)

    def _exit_frame(self, frame):
        if frame.kind == 'search':
            self.search.query.reset()
            self.presentation.clear_highlights()
        elif frame.kind == 'find':
            self._cancel_find()
            self.search.workspace.reset()

    def _pop_top_mode(self):
        frame = self.states.pop()
        if frame:
            self._exit_frame(frame)
            if frame.kind == 'find' and self.current_file is None and self.current_dir:
                self.presentation.directory(self.current_dir, False)
        self._refresh_prompt()
        return frame

    def _clear_mode_stack(self):
        self._cancel_find()
        for frame in reversed(self.states.frames):
            self._exit_frame(frame)
        self.states.clear()
        self._refresh_prompt()

    def _refresh_prompt(self):
        self.presentation.prompt()

    def _set_append_mode(self, enabled):
        if enabled:
            try:
                self.states.push('append')
            except StateError:
                self.presentation.notice('[!] ' + self._t('append_search_blocked'), 'warning')
                return False
        else:
            self.states.remove('append')
        self._refresh_prompt()
        return True

    def _set_open_mode(self, enabled):
        if enabled:
            if self.states.active == 'append' and self.open_mode:
                self.states.pop()
            elif self.states.active not in (None, 'find', 'open'):
                self._clear_mode_stack()
            self.states.push('open')
        else:
            self.states.remove('open')
        self._refresh_prompt()

    def _set_search_mode(self, enabled):
        if enabled:
            if self.states.active != 'search':
                self._clear_mode_stack()
                self.states.push('search')
        elif self.search_mode:
            self.states.remove('search')
            self._exit_frame(ModeFrame('search'))
        self._refresh_prompt()

    def _set_line_scope(self, number):
        self.search_scope, self.search_scope_line = 'line', number

    def _set_confirm_mode(self, on_yes, on_no=None):
        self.states.push('confirm', on_yes=on_yes, on_no=on_no, id=uuid4().hex)
        self._refresh_prompt()

    def _clear_confirm_mode(self):
        self.states.remove('confirm')
        self._refresh_prompt()

    def _ask_overwrite(self, target, on_yes):
        self._set_confirm_mode(on_yes)
        self.states.confirmation.payload['target'] = str(target)
        self.presentation.notice('[!] ' + self._t('exists_overwrite') % target.name, 'warning')

    def _handle_confirm(self, value):
        choice = value.lower()
        if choice not in ('y', 'n'):
            self.presentation.error('confirmation_required', self._t('confirm_retry'))
            return
        frame = self.states.confirmation
        action = frame.payload.get('on_yes' if choice == 'y' else 'on_no')
        self._clear_confirm_mode()
        if action:
            action()
        elif choice == 'n':
            self.presentation.notice('[!] ' + self._t('confirm_cancelled'), 'warning')
