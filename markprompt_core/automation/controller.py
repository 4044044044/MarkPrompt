"""Handle remote commands on the Tk event-loop thread."""
import threading
import hashlib
from pathlib import Path

from markprompt_core.commands.arguments import split_chain, validate
from markprompt_core.commands.catalog import REGISTRY
from markprompt_core.automation.transport import BridgeServer, response
from markprompt_core.automation.snapshot import capture
from markprompt_core.storage.local import StorageError


class GuiControl:
    def __init__(self, app, directory=None, source=None):
        self.app = app
        self.server = BridgeServer(directory, source)
        self.thread = threading.get_ident()
        self.timer = None
        self.quit_timer = None
        self.executing = False
        self.quit_requested = False
        self.closed = False
        self.error = None

    def start(self):
        self._require_thread()
        if self.timer is not None:
            return True
        try:
            self.server.start()
            self.timer = self.app.after(20, self._pump)
        except (OSError, RuntimeError) as error:
            self.error = str(error)
            self.server.close()
            return False
        return True

    def _require_thread(self):
        if threading.get_ident() != self.thread:
            raise RuntimeError('GUI control must execute on the window thread')

    def _pump(self):
        self.timer = None
        if self.closed:
            return
        if not self.executing:
            self.server.drain(self.handle)
        if not self.closed:
            self.timer = self.app.after(20, self._pump)

    def close(self):
        self._require_thread()
        if self.closed:
            return
        self.closed = True
        if self.timer is not None:
            self.app.after_cancel(self.timer)
            self.timer = None
        if self.quit_timer is not None:
            self.app.after_cancel(self.quit_timer)
            self.quit_timer = None
        self.server.close()

    def defer_quit(self):
        if self.executing:
            self.quit_requested = True
            self.app.closed = True
            return True
        return False

    def _finish_quit(self):
        self.quit_timer = None
        if self.quit_requested and not self.closed:
            self.app._quit_app()

    def observe(self, full=False):
        self._require_thread()
        snapshot = capture(self.app, full=full)
        snapshot['connection'] = {'window_id': self.server.id, 'gui_control': True}
        snapshot['ready'] = (not snapshot['find']['in_progress'] and
                             (not snapshot['document'] or not snapshot['document']['active'] or
                              snapshot['context']['view'] == 'console' or
                              snapshot['surface']['document_render_complete']))
        return snapshot

    def pending(self):
        return self.app._snapshot_surface()['pending']

    def handle(self, method, params):
        self._require_thread()
        if self.closed:
            return response(False, 'window_closed')
        if self.executing:
            return response(False, 'busy')
        self.executing = True
        try:
            if method == 'snapshot':
                if not isinstance(params.get('full', False), bool):
                    return response(False, 'invalid_arguments', message='full must be boolean')
                return response(snapshot=self.observe(params.get('full', False)), gui_control=True)
            if method not in {'execute', 'respond'}:
                return response(False, 'unknown_method')
            return self._command(method, params)
        finally:
            self.executing = False
            if self.quit_requested and self.quit_timer is None:
                self.quit_timer = self.app.after_idle(self._finish_quit)

    def _validation(self, value):
        if '\n' in value:
            return None
        for segment in split_chain(value):
            if segment.startswith('/'):
                request = REGISTRY.parse(segment)
                if request:
                    error = validate(request)
                    if error:
                        return error
            elif self.app.states.active == 'search':
                request = REGISTRY.parse('/search ' + ('-i ' if self.app.search_fuzzy else '') + segment)
                error = validate(request)
                if error:
                    return error
        return None

    def _state_error(self, code, message, command=''):
        return response(False, code, message=message, command=command, status='error',
                        snapshot=self.observe(), gui_control=True, effects=[], effects_omitted=0)

    def _command(self, method, params):
        app, pending = self.app, self.pending()
        if method == 'respond':
            choice = params.get('choice')
            if not pending or not pending.get('id') or params.get('confirmation_id') != pending.get('id'):
                return self._state_error('stale_confirmation', 'The confirmation is no longer current')
            if choice not in pending['choices']:
                return self._state_error('invalid_arguments', 'Choose one of: '+', '.join(pending['choices']))
            command = choice
            action = (lambda: app._snapshot_dialog_answer(choice)) if pending['kind'] in {'unsaved_navigation', 'unsaved_exit'} else (lambda: app._handle_confirm(choice))
            name = 'respond'
        else:
            command = params.get('command')
            if not isinstance(command, str) or not command.strip():
                return self._state_error('invalid_arguments', 'command must be a non-empty string')
            if app.closed:
                return self._state_error('window_closed', 'The window is closing', command)
            expected_file, expected_sha = params.get('expect_file'), params.get('expect_sha256')
            if expected_file is not None and (not isinstance(expected_file, str) or app.current_file != Path(expected_file)):
                return self._state_error('stale_snapshot', 'The current document changed', command)
            if expected_sha is not None and (not isinstance(expected_sha, str) or app.current_file != app.buffer_path or
                    app.buffer_text is None or hashlib.sha256(app.buffer_text.encode('utf-8')).hexdigest() != expected_sha):
                return self._state_error('stale_snapshot', 'The in-memory document changed', command)
            if pending and not REGISTRY.inspection(command):
                return response(False, 'confirmation_required', command=command, status='needs_confirmation',
                                snapshot=self.observe(), gui_control=True, effects=[], effects_omitted=0)
            error = self._validation(command)
            if error:
                return self._state_error('invalid_arguments', error, command)
            request = REGISTRY.parse(command) if command.startswith('/') and '\n' not in command else None
            name = request.spec.name if request else app.states.active or 'open'
            def action():
                # Preserve the user's draft while recording the remote command normally.
                if not REGISTRY.inspection(command):
                    app._record_prompt(command if '\n' not in command else '[remote pasted %d lines]' % len(command.splitlines()))
                if '\n' in command:
                    app._append_content(command)
                    app._recovery_sync()
                else:
                    app._dispatch(command.strip())
        before = app.buffer_text
        cursor = app.presentation.cursor
        with app.presentation.capture() as emitted:
            try:
                action()
            except StorageError as error:
                app._report_storage_error(error)
            except Exception as error:
                app.presentation.error('internal_error', str(error))
        snapshot = self.observe()
        errors = list(emitted['errors'])
        benign = (snapshot['interaction']['pending'] or name in {'save', 'undo', 'redo', 'respond'} or
                  (name == 'search' and app.search_mode and app.search_term is None) or
                  (name == 'find' and app.find_mode and app.current_file is None))
        for notice in emitted['notices']:
            if notice.get('code'):
                continue
            if notice['level'] == 'error' or notice['level'] == 'warning' and not benign:
                errors.append({'code': 'command_failed', 'message': notice['message']})
        error = errors[0] if errors else None
        effects = app.presentation.result_since(cursor)
        data = dict(emitted['data'])
        data['changed'] = app.buffer_text != before
        # Convert action results to JSON-compatible values.
        return response(error is None, error['code'] if error else 'confirmation_required' if snapshot['interaction']['pending'] else 'ok',
                        message=error['message'] if error else '', command=command,
                        status='error' if error else 'needs_confirmation' if snapshot['interaction']['pending'] else 'ok',
                        data=data, notices=emitted['notices'], effects=effects.as_data(), effects_omitted=effects.omitted,
                        snapshot=snapshot, gui_control=True)
