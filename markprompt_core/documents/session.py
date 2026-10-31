"""Manage the current note, its editing copy, and its disk version."""
from markprompt_core.documents.buffer import BufferModel
from markprompt_core.storage.local import StorageError
from pathlib import Path


class DocumentSession:
    def __init__(self, repository):
        self.repository = repository
        self.buffer = BufferModel()
        self.last_read = None
        self.version = None
        self.active_path = None

    def activate(self, path):
        self.active_path = Path(path) if path is not None else None

    def close(self, discard=False):
        self.active_path = None
        if discard:
            self.buffer.clear()
            self.version = self.last_read = None

    def prepare(self, path, loaded_text=None):
        """Prepare a document view without committing the navigation.

        Failed reads preserve the current copy. Reloaded clean text must not replace an
        unsaved draft of the same note.
        """
        path = Path(path)
        if self.buffer.is_same_note(path) and self.buffer.dirty:
            return self.buffer.text, False
        switching_dirty = self.buffer.path is not None and self.buffer.dirty
        content = self.read_disk(path).text if loaded_text is None else loaded_text
        self.set(path, content, dirty=False)
        return content, switching_dirty and loaded_text is None

    def read_disk(self, path):
        document = self.repository.read(path)
        self.last_read = (document.path, document.version)
        return document

    def set(self, path, text, dirty_lines=None, dirty=True):
        previous = self.buffer.path
        self.buffer.set(path, text, dirty_lines, dirty)
        if not dirty or previous != path:
            self.version = self.last_read[1] if self.last_read and self.last_read[0] == path else None

    def accept(self, document):
        self.last_read = (document.path, document.version)
        if self.buffer.path == document.path:
            self.version = document.version

    def write(self, path, content):
        expected = self.version if self.buffer.path == path else None
        document = (self.repository.save(path, content, expected) if expected is not None
                    else self.repository.overwrite(path, content))
        self.accept(document)
        return document

    def flush(self):
        return self.buffer.flush(lambda path, text: bool(self.write(path, text)))


class DocumentAdapter:
    """Expose document-session properties to the window and headless adapter."""
    @property
    def current_file(self):
        return self.document.active_path

    @current_file.setter
    def current_file(self, value):
        if value is None:
            self.document.close()
        else:
            self.document.activate(value)

    def _prepare_document(self, path, loaded_text=None):
        try:
            return self.document.prepare(path, loaded_text)
        except StorageError as error:
            self._report_storage_error(error)
            return None

    @property
    def buffer(self):
        return self.document.buffer

    @property
    def buffer_text(self):
        return self.buffer.text

    @buffer_text.setter
    def buffer_text(self, value):
        self.buffer.text = value

    @property
    def buffer_path(self):
        return self.buffer.path

    @buffer_path.setter
    def buffer_path(self, value):
        self.buffer.path = value

    @property
    def buffer_dirty(self):
        return self.buffer.dirty

    @buffer_dirty.setter
    def buffer_dirty(self, value):
        self.buffer.dirty = value

    @property
    def dirty_lines(self):
        return self.buffer.dirty_lines

    @dirty_lines.setter
    def dirty_lines(self, value):
        self.buffer.dirty_lines = value

    @property
    def _last_disk_read(self):
        return self.document.last_read

    @_last_disk_read.setter
    def _last_disk_read(self, value):
        self.document.last_read = value

    @property
    def _buffer_disk_version(self):
        return self.document.version

    @_buffer_disk_version.setter
    def _buffer_disk_version(self, value):
        self.document.version = value

    def _read_file(self, path):
        return self.buffer.read(path, self._read_disk)

    def _set_buffer(self, path, text, dirty_lines=None, dirty=True):
        self.document.set(path, text, dirty_lines, dirty)

    def _load_buffer_from_disk(self, path):
        content = self._read_disk(path)
        if content is not None:
            self._set_buffer(path, content, dirty=False)
        return content

    def _ensure_buffer_for_current(self):
        if self.buffer.is_same_note(self.current_file):
            return True
        return self._load_buffer_from_disk(self.current_file) is not None

    def _require_note(self, allow_text=False):
        if self.current_file and self.current_file.is_file():
            if self.current_file.suffix.lower() == '.txt' and not allow_text:
                self._drop_notice('text_readonly')
                return False
            return True
        self.presentation.error('no_note', self._t('no_note'))
        return False

    def _flush_buffer(self):
        try:
            return self.document.flush()
        except StorageError as error:
            self._report_storage_error(error)
            return False
