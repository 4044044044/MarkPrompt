"""Show storage results and manage window recovery notices."""
from markprompt_core.storage.local import StorageError


class StorageMixin:
    def _report_storage_error(self, error):
        warning = error.code in {'disk_changed', 'drop_unknown', 'path_outside_workspace', 'path_too_long', 'workspace_needed'}
        tag, prefix = ('warning', '[!] ') if warning else ('error', '[ERR] ')
        detail = '' if warning else str(error.path or error.detail or '')
        self.presentation.notice(prefix + self._t(error.code) + detail, tag, code=error.code)

    def _validate_path(self, path):
        try:
            return self.storage.paths.validate(path, self.workspace, self.storage.paths.platform_limit)
        except StorageError as error:
            self._report_storage_error(error)
            return None

    def _resolve_path(self, value):
        try:
            return self.storage.paths.browsing(value, self.current_dir, self.workspace,
                                              self.storage.paths.platform_limit)
        except StorageError as error:
            self._report_storage_error(error)
            return None

    def _read_disk(self, path):
        try:
            document = self.document.read_disk(path)
            return document.text
        except StorageError as error:
            self._report_storage_error(error)
            return None

    def _read_drop_text(self, path):
        try:
            if path.suffix.lower() not in {'.md', '.txt'}:
                self._drop_notice('drop_unknown')
                return None
            document = self.document.read_disk(path)
            return document.text
        except StorageError as error:
            self._drop_notice('drop_unknown' if error.code == 'drop_unknown' else 'drop_failed',
                              '' if error.code == 'drop_unknown' else str(error))
            return None

    def _write_file(self, path, content):
        try:
            self.document.write(path, content)
            return True
        except StorageError as error:
            self._report_storage_error(error)
            return False

    def _command_error(self, code, message):
        self._append_notice('[!] ' + message, 'warning')

    def _load_config(self):
        try:
            return self.storage.preferences.load(self.config_path)
        except StorageError:
            return {}

    def _save_config(self, data):
        try:
            self.storage.preferences.save(self.config_path, data)
            return True
        except StorageError:
            return False

    def _bookmarks(self):
        try:
            return self.storage.bookmarks.load(self.workspace)
        except StorageError:
            return {}

    def _save_bookmarks(self, bookmarks):
        try:
            self.storage.bookmarks.save(self.workspace, bookmarks)
        except StorageError as error:
            self._append_notice('[ERR] ' + self._t('save_bookmarks_failed') + str(error), 'error')

    def _recovery_file(self):
        try:
            return self.storage.recovery.path(self.workspace, self.config_path)
        except StorageError:
            return None

    def _recovery_sync(self):
        try:
            if self.buffer_dirty and self.current_file is not None and self.buffer_text is not None:
                self.storage.recovery.save(self.workspace, self.config_path, self.current_file,
                                           self.buffer_text, self.dirty_lines or ())
            else:
                self.storage.recovery.clear(self.workspace, self.config_path)
        except StorageError:
            pass  # Recovery is best effort; explicit saves report their failures.

    def _recovery_clear(self):
        try:
            self.storage.recovery.clear(self.workspace, self.config_path)
        except StorageError:
            pass

    def _recovery_load(self):
        try:
            return self.storage.recovery.load(self.workspace, self.config_path)
        except StorageError:
            return None
