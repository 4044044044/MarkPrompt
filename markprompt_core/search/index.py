"""Cache note text and scan workspaces with cancellation support."""
import sys
import threading
from collections import OrderedDict
from markprompt_core.storage.local import LocalDocuments, LocalFiles, StorageError

SEARCH_CACHE_LIMIT = 32 * 1024 * 1024
SEARCH_CACHE_FILES = 4096

class WorkspaceSearch:
    """Scan notes with a bounded text cache and cancellation support."""

    def __init__(self, documents=None):
        self.documents = documents if documents is not None else LocalDocuments()
        self.cache = OrderedDict()
        self.cache_bytes = 0
        self.lock = threading.RLock()
        self.progress = (0, 0)

    @staticmethod
    def files(workspace, cancel=None, suffixes=(".md",)):
        return LocalFiles.scan(workspace, cancel, suffixes)

    def read(self, path):
        info = path.stat()
        signature = (info.st_mtime_ns, info.st_ctime_ns, info.st_size)
        with self.lock:
            cached = self.cache.get(path)
            if cached and cached[0] == signature:
                self.cache.move_to_end(path)
                return cached[1]
        document = self.documents.read(path)
        text = document.text
        lowered = text.lower()
        cost = sys.getsizeof(lowered)
        with self.lock:
            previous = self.cache.pop(path, None)
            if previous:
                self.cache_bytes -= previous[2]
            if cost <= SEARCH_CACHE_LIMIT:
                self.cache[path] = (signature, lowered, cost)
                self.cache_bytes += cost
            while self.cache_bytes > SEARCH_CACHE_LIMIT or len(self.cache) > SEARCH_CACHE_FILES:
                _path, old = self.cache.popitem(last=False)
                self.cache_bytes -= old[2]
        return lowered

    def search(self, workspace, needle, paths, cancel):
        rows, hits, scanned, skipped = [], set(), 0, 0
        self.progress = (0, 0)
        for path in paths:
            if cancel.is_set():
                return None
            try:
                text = self.read(path)
            except (OSError, StorageError):
                skipped += 1
                continue
            count = sum(1 for line in text.splitlines() if needle in line)
            scanned += 1
            if count:
                hits.add(path)
                rows.append((path.relative_to(workspace).as_posix(), count))
            self.progress = (scanned, len(hits))
        rows.sort(key=lambda item: item[0].casefold())
        return rows, hits, skipped
