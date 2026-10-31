"""Read and write local notes, preferences, and recovery data."""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Protocol
import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import unicodedata
from urllib.parse import unquote

MAX_TEXT_BYTES = 8 * 1024 * 1024
MAX_JSON_BYTES = MAX_TEXT_BYTES * 4


class StorageError(Exception):
    def __init__(self, code, path=None, detail=''):
        self.code = code
        self.path = Path(path) if path is not None else None
        self.detail = detail
        super().__init__(detail or str(self.path or code))


class SaveConflict(StorageError):
    def __init__(self, path):
        super().__init__('disk_changed', path)


def io_error(error, path, operation):
    code = 'permission_denied' if isinstance(error, PermissionError) else operation
    return StorageError(code, path, str(error))


def decode_text(data):
    """Decode BOM, UTF-8, or GB18030 text and reject binary or control data."""
    if data.startswith((b'MZ', b'\x7fELF', b'PK\x03\x04', b'\x89PNG', b'\xff\xd8\xff',
                        b'GIF87a', b'GIF89a', b'%PDF-', b'\x1f\x8b', b'\xd0\xcf\x11\xe0')):
        raise ValueError('binary')
    if data.startswith((b'\xff\xfe\x00\x00', b'\x00\x00\xfe\xff')):
        encodings = ('utf-32',)
    elif data.startswith((b'\xff\xfe', b'\xfe\xff')):
        encodings = ('utf-16',)
    else:
        encodings = ('utf-8-sig', 'gb18030')
    for encoding in encodings:
        try:
            text = data.decode(encoding)
        except UnicodeError:
            continue
        if any(unicodedata.category(char) == 'Cc' and char not in '\t\r\n\f' for char in text):
            raise ValueError('binary')
        return text.replace('\r\n', '\n').replace('\r', '\n')
    raise ValueError('encoding')


def atomic_write_text(path, content):
    """Write beside the destination, then replace it; failures preserve the old file."""
    path, temporary = Path(path), None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n',
                                         dir=path.parent, prefix='.markprompt-',
                                         suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                os.chmod(temporary, 0o600)
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


@dataclass(frozen=True)
class Document:
    path: Path
    text: str
    version: bytes


class DocumentRepository(Protocol):
    def read(self, path: Path, limit: int = MAX_TEXT_BYTES) -> Document: ...
    def save(self, path: Path, text: str, expected_version: Optional[bytes]) -> Document: ...
    def overwrite(self, path: Path, text: str) -> Document: ...


class LocalDocuments:
    def __init__(self, max_bytes=MAX_TEXT_BYTES):
        self._lock = threading.RLock()
        self.max_bytes = max_bytes

    def read(self, path, limit=None):
        path = Path(path)
        limit = self.max_bytes if limit is None else limit
        try:
            with path.open('rb') as stream:
                data = stream.read(limit + 1)
        except OSError as error:
            raise io_error(error, path, 'read_failed') from error
        if len(data) > limit:
            raise StorageError('drop_unknown', path, 'large text file')
        try:
            text = decode_text(data)
        except (ValueError, UnicodeError) as error:
            raise StorageError('drop_unknown', path, str(error)) from error
        return Document(path, text, hashlib.sha256(data).digest())

    def _write(self, path, text):
        path = Path(path)
        try:
            atomic_write_text(path, text)
        except OSError as error:
            raise io_error(error, path, 'write_failed') from error
        except UnicodeError as error:
            raise StorageError('write_failed', path, str(error)) from error
        return Document(path, text, hashlib.sha256(text.encode('utf-8')).digest())

    def save(self, path, text, expected_version):
        """Create when expected_version is None; otherwise compare it with the bytes on disk.

        The lock covers this repository instance only. Another process can still write
        between the version check and replacement.
        """
        path = Path(path)
        with self._lock:
            if expected_version is None:
                if path.exists():
                    raise SaveConflict(path)
            else:
                try:
                    current = self.read(path).version
                except StorageError as error:
                    raise SaveConflict(path) from error
                if current != expected_version:
                    raise SaveConflict(path)
            return self._write(path, text)

    def overwrite(self, path, text):
        """Write unconditionally after the application has confirmed replacement."""
        with self._lock:
            return self._write(path, text)


class PathPolicy:
    platform_limit = 260 if os.name == 'nt' else None

    def validate(self, path, workspace=None, max_length=None):
        path = Path(path)
        try:
            resolved = path.resolve(strict=True)
            if workspace is not None and not resolved.is_relative_to(Path(workspace).resolve()):
                raise StorageError('path_outside_workspace', path)
        except (OSError, ValueError) as error:
            raise StorageError('invalid_path', path, str(error)) from error
        if max_length is not None and len(str(resolved)) > max_length:
            raise StorageError('path_too_long', resolved)
        return resolved

    def browsing(self, value, current_directory, workspace=None, max_length=None):
        path = Path(value.strip().strip('"'))
        if not path.is_absolute():
            if current_directory is None:
                raise StorageError('workspace_needed')
            path = Path(current_directory) / path
        return self.validate(path, workspace, max_length)

    def external_file(self, value, workspace=None, max_length=None):
        path = Path(value.strip().strip('"'))
        if not path.is_absolute():
            if workspace is None:
                raise StorageError('workspace_needed')
            path = Path(workspace) / path
        return self.validate(path, workspace, max_length)

    def image(self, value, note):
        raw = unquote(value)
        if raw.startswith(('//', '\\\\')) or (re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', raw)
                and not re.match(r'^[a-zA-Z]:[\\/]', raw)):
            raise StorageError('drop_unknown', detail='local files only')
        path = Path(raw)
        if not path.is_absolute():
            path = Path(note).parent / path
        return self.validate(path)


class LocalFiles:
    EXCLUDED = frozenset({'.markprompt', '.git', '__pycache__', 'node_modules', '.venv', 'venv'})

    def __init__(self):
        self._lock = threading.RLock()

    def list_directory(self, path):
        path = Path(path)
        try:
            if not path.is_dir():
                raise StorageError('not_directory', path)
            return sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        except OSError as error:
            raise io_error(error, path, 'read_failed') from error

    @staticmethod
    def scan(workspace, cancel=None, suffixes=('.md',)):
        root = Path(workspace).resolve()
        for folder, directories, names in os.walk(root, followlinks=False):
            if cancel is not None and cancel.is_set():
                return
            directories[:] = [name for name in directories if name not in LocalFiles.EXCLUDED]
            for name in names:
                if cancel is not None and cancel.is_set():
                    return
                path = Path(folder)/name
                if path.suffix.lower() in suffixes and not path.is_symlink():
                    yield path

    def unique(self, path):
        path = Path(path)
        if not path.exists():
            return path
        stamp = datetime.now().strftime('-%Y%m%d-%H%M%S')
        candidate, number = path.with_name(path.stem + stamp + path.suffix), 1
        while candidate.exists():
            candidate = path.with_name(path.stem + stamp + '-%d' % number + path.suffix)
            number += 1
        return candidate

    def create_unique(self, target, writer):
        with self._lock:
            return writer(self.unique(target))

    def area(self, workspace, name):
        if name not in {'archive', 'trash', 'recovery', 'snapshots'}:
            raise StorageError('invalid_path', detail='Unknown storage area')
        if workspace is None:
            raise StorageError('workspace_needed')
        root = Path(workspace).resolve()
        path = root/'.markprompt'/name
        try:
            if not path.resolve().is_relative_to(root):
                raise StorageError('path_outside_workspace', path)
            path.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise io_error(error, path, 'write_failed') from error
        return path

    def import_note(self, source, workspace):
        source = Path(source)
        if not source.is_file() or source.suffix.lower() != '.md':
            raise StorageError('not_found', source)
        if workspace is None:
            raise StorageError('workspace_needed')
        if not Path(workspace).is_dir():
            raise StorageError('not_directory', workspace)
        with self._lock:
            target = self.unique(Path(workspace)/source.name)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.markprompt-',
                                                 suffix='.tmp', delete=False) as stream:
                    temporary = Path(stream.name)
                shutil.copy2(str(source), str(temporary))
                os.replace(temporary, target)
                temporary = None
            except OSError as error:
                raise io_error(error, target, 'import_failed') from error
            finally:
                if temporary is not None:
                    try:
                        os.chmod(temporary, 0o600)
                        temporary.unlink(missing_ok=True)
                    except OSError:
                        pass
            return target

    def move_to(self, source, workspace, area):
        source = Path(source)
        with self._lock:
            target = self.unique(self.area(workspace, area)/source.name)
            try:
                shutil.move(str(source), str(target))
            except OSError as error:
                raise io_error(error, source, 'move_failed') from error
            return target

    def restore(self, workspace, name):
        trash = self.area(workspace, 'trash').resolve()
        source = (trash/name).resolve()
        if not source.is_relative_to(trash):
            raise StorageError('path_outside_workspace', source)
        if not source.is_file():
            raise StorageError('not_found', source)
        with self._lock:
            target = self.unique(Path(workspace)/source.name)
            try:
                shutil.move(str(source), str(target))
            except OSError as error:
                raise io_error(error, source, 'restore_failed') from error
            return target


class JsonFiles:
    def read(self, path, limit=MAX_JSON_BYTES):
        path = Path(path)
        try:
            with path.open('rb') as stream:
                data = stream.read(limit + 1)
        except FileNotFoundError:
            return None
        except OSError as error:
            raise io_error(error, path, 'read_failed') from error
        if len(data) > limit:
            raise StorageError('invalid_data', path, 'JSON file is too large')
        try:
            return json.loads(data.decode('utf-8'))
        except (UnicodeError, ValueError) as error:
            raise StorageError('invalid_data', path, str(error)) from error

    def write(self, path, value):
        path = Path(path)
        try:
            content = json.dumps(value, ensure_ascii=False, indent=2)
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(path, content)
        except OSError as error:
            raise io_error(error, path, 'write_failed') from error
        except (TypeError, ValueError) as error:
            raise StorageError('invalid_data', path, str(error)) from error

    def delete(self, path):
        try:
            Path(path).unlink(missing_ok=True)
        except OSError as error:
            raise io_error(error, path, 'write_failed') from error


class Preferences:
    def __init__(self, json_files):
        self.json = json_files

    def load(self, path):
        value = self.json.read(path)
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise StorageError('invalid_data', path, 'Expected a JSON object')
        return value

    def save(self, path, values):
        if not isinstance(values, dict):
            raise StorageError('invalid_data', path)
        self.json.write(path, values)


class Bookmarks:
    def __init__(self, json_files):
        self.preferences = Preferences(json_files)

    @staticmethod
    def path(workspace):
        if workspace is None:
            raise StorageError('workspace_needed')
        root = Path(workspace).resolve()
        path = root/'.markprompt'/'bookmarks.json'
        if not path.resolve().is_relative_to(root):
            raise StorageError('path_outside_workspace', path)
        return path

    def load(self, workspace):
        values = self.preferences.load(self.path(workspace))
        return {str(name).lower(): str(value) for name, value in values.items()}

    def save(self, workspace, values):
        self.preferences.save(self.path(workspace), values)


class Recovery:
    def __init__(self, json_files):
        self.json = json_files

    @staticmethod
    def path(workspace, config_path):
        if workspace is None:
            return Path(config_path).parent/'.markprompt-recovery'/'snapshot.json'
        root = Path(workspace).resolve()
        path = root/'.markprompt'/'recovery'/'snapshot.json'
        if not path.resolve().is_relative_to(root):
            raise StorageError('path_outside_workspace', path)
        return path

    @staticmethod
    def validate(data, path):
        if (not isinstance(data, dict) or not isinstance(data.get('path'), str) or
                not isinstance(data.get('text'), str) or '\0' in data['path'] or
                not Path(data['path']).is_absolute() or
                not isinstance(data.get('dirty_lines', []), list) or
                any(type(n) is not int or n < 1 for n in data.get('dirty_lines', []))):
            raise StorageError('invalid_data', path, 'Invalid recovery snapshot')
        return data

    def load(self, workspace, config_path):
        path = self.path(workspace, config_path)
        data = self.json.read(path)
        return None if data is None else self.validate(data, path)

    def save(self, workspace, config_path, note, text, dirty_lines):
        path = self.path(workspace, config_path)
        data = {'path': str(note), 'text': text, 'dirty_lines': list(dirty_lines),
                'ts': datetime.now().isoformat(timespec='seconds')}
        self.validate(data, path)
        data['dirty_lines'].sort()
        self.json.write(path, data)

    def clear(self, workspace, config_path):
        self.json.delete(self.path(workspace, config_path))


class StorageServices:
    """Group document, path, preference, bookmark, and recovery services."""
    def __init__(self, documents=None):
        self.documents: DocumentRepository = documents if documents is not None else LocalDocuments()
        self.paths = PathPolicy()
        self.files = LocalFiles()
        self.json = JsonFiles()
        self.preferences = Preferences(self.json)
        self.bookmarks = Bookmarks(self.json)
        self.recovery = Recovery(self.json)

    def export_text(self, target, text):
        return self.files.create_unique(
            target, lambda path: self.documents.save(path, text, expected_version=None))

    def snapshot_directory(self, workspace, config_path):
        if workspace is not None:
            return self.files.area(workspace, 'snapshots')
        path = Path(config_path).parent / '.markprompt-snapshots'
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise io_error(error, path, 'write_failed') from error
        return path

    def export_snapshot(self, target, value):
        target = Path(target)
        if target.suffix.lower() != '.json':
            raise StorageError('invalid_path', target, 'Snapshot destination must end in .json')
        text = json.dumps(value, ensure_ascii=False, indent=2)
        if len(text.encode('utf-8')) > MAX_JSON_BYTES:
            raise StorageError('invalid_data', target, 'Snapshot exceeds JSON size limit')
        if not target.parent.is_dir():
            raise StorageError('not_directory', target.parent)
        return self.export_text(target, text).path


def configuration_path(base, filename='markprompt.json'):
    """Check writability with a temporary file before choosing the config directory."""
    base = Path(base)
    try:
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=base):
            pass
        return base/filename
    except OSError:
        fallback = Path.home()/'.markprompt'
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback/filename
