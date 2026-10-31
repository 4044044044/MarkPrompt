"""Editable text with manual saving and compressed undo history."""
import sys
import zlib

UNDO_LIMIT = 100
UNDO_MEMORY_LIMIT = 16 * 1024 * 1024

class BufferModel:
    """Keep an editable note, its saved baseline, and undo history in memory.

    Dirty line numbers are 1-based. Reader and writer callbacks handle disk access.
    """

    def __init__(self):
        self.path = None
        self.text = None
        self.dirty = False
        self.dirty_lines = set()
        # Keep the last saved text so undo after /save can become dirty again.
        self._saved_text = None
        # Snapshots contain the path, text, and dirty line numbers.
        # New edits invalidate redo; switching notes clears both stacks.
        self._undo = []
        self._redo = []

    @property
    def is_loaded(self):
        return self.path is not None and self.text is not None

    def _snapshot(self):
        text = self.text
        if text is not None and len(text) >= 4096:
            text = zlib.compress(text.encode("utf-8"), 1)
        return (self.path, text, frozenset(self.dirty_lines))

    def _restore(self, snapshot):
        self.path, self.text, lines = snapshot
        if isinstance(self.text, bytes):
            self.text = zlib.decompress(self.text).decode("utf-8")
        self.dirty_lines = set(lines)
        # Compare restored text with disk, not with the old snapshot flag.
        self.dirty = self.text != self._saved_text

    def _push_undo(self):
        """Save the current copy before an edit and clear redo history."""
        self._undo.append(self._snapshot())
        if len(self._undo) > UNDO_LIMIT:
            self._undo.pop(0)
        self._redo.clear()
        self._trim_history()

    def _trim_history(self):
        def size(snapshot):
            value = snapshot[1]
            return sys.getsizeof(value) + sys.getsizeof(snapshot[2]) + len(snapshot[2]) * 32 + 128
        total = sum(size(s) for s in self._undo + self._redo)
        while total > UNDO_MEMORY_LIMIT and (self._undo or self._redo):
            stack = self._undo if self._undo else self._redo
            total -= size(stack.pop(0))

    def undo(self):
        """Restore the previous copy in memory; return whether a snapshot was available."""
        if not self._undo:
            return False
        self._redo.append(self._snapshot())
        self._restore(self._undo.pop())
        self._trim_history()
        return True

    def redo(self):
        """Restore the next copy in memory; return whether a snapshot was available."""
        if not self._redo:
            return False
        self._undo.append(self._snapshot())
        self._restore(self._redo.pop())
        self._trim_history()
        return True

    def clear(self):
        self.path = None
        self.text = None
        self.dirty = False
        self.dirty_lines = set()
        self._saved_text = None
        self._undo.clear()
        self._redo.clear()

    def set(self, path, text, dirty_lines=None, dirty=True):
        # Undo history belongs to one note; never carry it into the next.
        if path != self.path:
            self._undo.clear()
            self._redo.clear()
        self.path = path
        self.text = text
        self.dirty_lines = set(dirty_lines or ())
        self.dirty = dirty
        # A clean load establishes the disk baseline; an incoming draft may not have one.
        self._saved_text = None if dirty else text

    def is_same_note(self, path):
        return self.path == path and self.text is not None

    def read(self, path, reader):
        """Read the current note from memory, or use the supplied disk reader for another path."""
        if self.is_same_note(path):
            return self.text
        return reader(path)

    def load_from_disk(self, path, reader):
        """Load a clean copy. A failed read leaves the existing buffer untouched."""
        content = reader(path)
        if content is None:
            return None
        self.set(path, content, dirty_lines=None, dirty=False)
        return content

    def append(self, text):
        """Append text and mark its physical source lines dirty; return whether it changed."""
        if self.text is None or not text:
            return False
        self._push_undo()
        content = self.text
        separator = "" if not content or content.endswith("\n") else "\n"
        new_text = content + separator + text.rstrip("\r\n") + "\n"
        base = len(content.splitlines())
        total = len(new_text.splitlines())
        self.dirty_lines = set(self.dirty_lines) | set(range(base + 1, total + 1))
        self.text = new_text
        self.dirty = True
        return True

    def replace_line(self, number, replacement):
        """Replace a 1-based source line, preserving its line ending and recording undo."""
        if self.text is None:
            return False
        lines = self.text.splitlines(True)
        if not 1 <= number <= len(lines):
            return False
        self._push_undo()
        index = number - 1
        ending = "\n" if lines[index].endswith(("\n", "\r")) else ""
        lines[index] = replacement + ending
        self.text = "".join(lines)
        self.dirty_lines = set(self.dirty_lines) | {number}
        self.dirty = True
        return True

    def delete_line(self, number):
        """Delete a 1-based source line and mark shifted lines dirty.

        Keep existing dirty marks above it. Invalid line numbers leave the buffer
        unchanged.
        """
        if self.text is None:
            return False
        lines = self.text.splitlines(True)
        if not 1 <= number <= len(lines):
            return False
        self._push_undo()
        del lines[number - 1]
        self.text = "".join(lines)
        total = len(lines)
        self.dirty_lines = set(self.dirty_lines) | set(range(number, total + 1))
        self.dirty = True
        return True

    def mutate(self, new_text, dirty_lines):
        """Replace the text and dirty-line set as one undoable edit."""
        if self.text is None:
            return False
        self._push_undo()
        self.text = new_text
        self.dirty_lines = set(dirty_lines)
        self.dirty = True
        return True

    def flush(self, writer):
        """Write a dirty copy through writer(path, text); clear dirty state only on success."""
        if self.path is None or self.text is None:
            return True
        if not self.dirty:
            return True
        if writer(self.path, self.text):
            self.dirty = False
            self.dirty_lines = set()
            self._saved_text = self.text  # The disk now matches this copy.
            return True
        return False
