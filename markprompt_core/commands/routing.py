"""Route input through confirmation, active modes, and command lookup."""


class CommandRouter:
    def __init__(self, registry):
        self.registry = registry

    def dispatch(self, app, value):
        cursor = app.presentation.cursor
        self._dispatch(app, value)
        return app.presentation.result_since(cursor)

    def _dispatch(self, app, value):
        observation = self.registry.inspection(value)
        if observation:
            getattr(app, '_command_' + observation.spec.name)(observation.argument)
            return
        if app.confirm_mode:
            app._handle_confirm(value.strip())
            return
        if not value.startswith('/'):
            if app.states.active == 'append':
                app._append_content(value)
            elif app.states.active == 'open':
                app._try_open_file(value)
            elif app.states.active == 'search':
                app._run_search(value.strip(), app.search_fuzzy)
            elif app.states.active == 'find':
                app._command_find(value.strip())
            else:
                path = app._resolve_path(value)
                if path:
                    app._visit_path(path)
            return
        request = self.registry.parse(value)
        if request is None:
            app.presentation.error('unknown_command', app._t('unknown') + ' ' + value.split()[0] + ' · /help')
            return
        spec, argument = request.spec, request.argument
        if any(app.states.has(kind) for kind in spec.blocked_states):
            app.presentation.error(spec.refusal, app._t(spec.refusal))
            return
        if spec.requirement == 'document' and not app._require_note():
            return
        if spec.requirement == 'workspace' and app._needs_workspace():
            return
        if spec.navigation:
            if not app._confirm_navigation(lambda: self.dispatch(app, value)):
                return
        # Keep the current state until navigation or mode entry succeeds.
        handler = getattr(app, '_command_' + spec.name)
        handler(argument)
