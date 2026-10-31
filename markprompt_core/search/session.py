"""Track search terms, edit scopes, and background jobs."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from itertools import chain
from pathlib import Path
import re
import threading
from time import monotonic

from markprompt_core.documents.content import search_hits
from markprompt_core.search.index import WorkspaceSearch

SEARCH_SYNC_FILES = 24


@dataclass
class Query:
    term: str = None
    ignore_case: bool = False
    scope: str = 'note'
    line: int = None

    def reset(self):
        self.term, self.ignore_case, self.scope, self.line = None, False, 'note', None

    def begin(self, term, ignore_case=False):
        self.term, self.ignore_case, self.scope, self.line = term.strip() or None, ignore_case, 'note', None

    def hits(self, text):
        return search_hits(text, self.term, self.ignore_case)

    def replace(self, buffer, replacement):
        if not self.term:
            return None
        lines = buffer.text.splitlines(True)
        targets = ([self.line] if self.line and 1 <= self.line <= len(lines) else []) if self.scope == 'line' else range(1, len(lines) + 1)
        pattern = re.compile(re.escape(self.term), re.IGNORECASE if self.ignore_case else 0)
        count, dirty = 0, set(buffer.dirty_lines)
        for number in targets:
            raw = lines[number - 1]
            body = raw.rstrip('\r\n')
            changed, hits = pattern.subn(lambda _match: replacement, body)
            if hits:
                lines[number - 1] = changed + raw[len(body):]
                count += hits
                dirty.add(number)
        if count:
            buffer.mutate(''.join(lines), dirty)
        return count


@dataclass
class WorkspaceQuery:
    term: str = None
    hits: set = field(default_factory=set)
    rows: tuple = ()
    return_scroll: float = None

    def reset(self):
        self.term, self.hits, self.rows, self.return_scroll = None, set(), (), None


@dataclass(frozen=True)
class SearchUpdate:
    status: str
    future: object = None
    result: object = None
    error: Exception = None
    progress: tuple = (0, 0)


class SearchSession:
    """Track queries, the active job, and its worker lifecycle.

    Polling an older job returns stale even when its query text matches the new one.
    Workers return data; callers update the UI.
    """
    def __init__(self, documents):
        self.query = Query()
        self.workspace = WorkspaceQuery()
        self.index = WorkspaceSearch(documents)
        self.future = self.cancel_event = self.executor = None
        self.closed = False
        self.generation = 0
        self.job_kind, self.job_status, self.job_error = None, 'idle', None

    def cancel(self):
        if self.future is not None:
            self.job_status = 'cancelled'
        if self.cancel_event is not None:
            self.cancel_event.set()
        if self.future is not None:
            self.future.cancel()
        self.future = self.cancel_event = None
        self.workspace.return_scroll = None

    def close(self):
        self.cancel()
        self.closed = True
        if self.executor is not None:
            self.executor.shutdown(wait=False, cancel_futures=True)
            self.executor = None

    def _sample(self, root, cancel, suffixes, count):
        paths = iter(self.index.files(root, cancel, suffixes))
        first, started, size = [], monotonic(), 0
        while len(first) < count and monotonic() - started < .006:
            try:
                path = next(paths)
            except StopIteration:
                return first, paths, True
            first.append(path)
            try:
                size += path.stat().st_size
            except OSError:
                pass
            if size > 256 * 1024:
                break
        return first, paths, False

    def _start(self, root, suffixes, operation, background):
        if self.closed:
            raise RuntimeError('Search session is closed')
        self.cancel()
        self.generation += 1
        self.job_status, self.job_error = 'running', None
        cancel = threading.Event()
        first, paths, complete = self._sample(root, cancel, suffixes, SEARCH_SYNC_FILES if background else 0)
        values = chain(first, paths)
        if complete or not background:
            try:
                result = operation(values, cancel)
            except Exception as error:
                self.job_status, self.job_error = 'error', str(error)
                raise
            self.job_status = 'complete'
            return SearchUpdate('complete', result=result)
        if self.executor is None:
            self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='markprompt-search')
        self.cancel_event = cancel
        self.future = self.executor.submit(operation, values, cancel)
        return SearchUpdate('pending', future=self.future)

    def start_find(self, root, term, background=True):
        self.job_kind = 'find'
        root = Path(root).resolve()
        self.workspace.term, self.workspace.hits, self.workspace.rows = term, set(), ()
        return self._start(root, ('.md',), lambda paths, cancel: self.index.search(root, term.lower(), paths, cancel), background)

    def start_files(self, root, term, background=True):
        self.job_kind = 'files'
        root = Path(root).resolve()
        def collect(paths, cancel):
            matches = []
            for path in paths:
                if cancel.is_set():
                    return None
                if term.casefold() in path.relative_to(root).as_posix().casefold():
                    matches.append(path)
                if len(matches) == 200:
                    break
            return sorted(matches, key=lambda path: str(path).casefold())
        return self._start(root, ('.md', '.txt'), collect, background)

    def poll(self, future):
        if future is not self.future or future is None:
            return SearchUpdate('stale')
        if not future.done():
            return SearchUpdate('pending', future=future, progress=self.index.progress)
        cancelled = self.cancel_event is not None and self.cancel_event.is_set()
        self.future = self.cancel_event = None
        if cancelled:
            return SearchUpdate('stale')
        try:
            result = future.result()
            self.job_status = 'complete'
            return SearchUpdate('complete', result=result)
        except Exception as error:
            self.job_status, self.job_error = 'error', str(error)
            return SearchUpdate('error', error=error)


def field_alias(owner, name):
    """Expose search-record fields through the application adapter."""
    def get(app):
        target = app.search
        for part in owner:
            target = getattr(target, part)
        return getattr(target, name)
    def set_value(app, value):
        target = app.search
        for part in owner:
            target = getattr(target, part)
        setattr(target, name, value)
    return property(get, set_value)


class SearchAdapter:
    search_term = field_alias(('query',), 'term')
    search_fuzzy = field_alias(('query',), 'ignore_case')
    search_scope = field_alias(('query',), 'scope')
    search_scope_line = field_alias(('query',), 'line')
    find_term = field_alias(('workspace',), 'term')
    find_file_hits = field_alias(('workspace',), 'hits')
    _find_rows = field_alias(('workspace',), 'rows')
    _find_return_scroll = field_alias(('workspace',), 'return_scroll')
    _find_future = field_alias((), 'future')
    _find_cancel = field_alias((), 'cancel_event')
    _search_executor = field_alias((), 'executor')
    _search_index = field_alias((), 'index')
