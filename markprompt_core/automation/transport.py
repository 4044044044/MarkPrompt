"""Authenticate local connections and queue work for the GUI thread."""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import hashlib
import hmac
import json
import os
from pathlib import Path
import queue
import secrets
import socket
import struct
import threading
from time import monotonic
from uuid import uuid4

from markprompt_core import __version__

PROTOCOL = 1
MAX_REQUEST = 8 * 1024 * 1024
MAX_RESPONSE = 32 * 1024 * 1024
MAX_RECORDS = 128
CACHE_BYTES = 16 * 1024 * 1024


class LiveError(Exception):
    def __init__(self, code, message, request_id=None):
        self.code, self.request_id = code, request_id
        super().__init__(message)


def runtime_directory():
    base = Path(os.environ['LOCALAPPDATA']) if os.environ.get('LOCALAPPDATA') else Path.home()/'.cache'
    return base/'MarkPrompt'/'runtime'


def response(ok=True, code='ok', **data):
    return {'protocol_version': PROTOCOL, 'ok': ok, 'code': code, **data}


def receive(stream, limit):
    def exact(size):
        result = bytearray()
        while len(result) < size:
            part = stream.recv(min(65536, size-len(result)))
            if not part:
                raise LiveError('connection_closed', 'Connection closed before the complete frame arrived')
            result.extend(part)
        return bytes(result)
    length = struct.unpack('!I', exact(4))[0]
    if length > limit:
        raise LiveError('frame_too_large', 'Frame exceeds the protocol size limit')
    try:
        value = json.loads(exact(length).decode('utf-8'))
    except (UnicodeError, ValueError) as error:
        raise LiveError('invalid_request', 'Expected a UTF-8 JSON object') from error
    if not isinstance(value, dict):
        raise LiveError('invalid_request', 'Expected a JSON object')
    return value


def send(stream, value, limit=MAX_RESPONSE):
    data = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    if len(data) > limit:
        raise LiveError('frame_too_large', 'Response exceeds the protocol size limit')
    stream.sendall(struct.pack('!I', len(data))+data)


@dataclass
class Request:
    id: str
    method: str
    params: dict
    fingerprint: str
    deadline: float
    status: str = 'queued'
    result: dict = None
    done: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    size: int = 0


class BridgeServer:
    def __init__(self, directory=None, source=None):
        self.directory = Path(directory) if directory is not None else runtime_directory()
        self.id, self.token = uuid4().hex, secrets.token_urlsafe(32)
        self.path = self.directory/(self.id+'.json')
        self.requests = queue.Queue(maxsize=16)
        self.records = OrderedDict()
        self.lock = threading.RLock()
        self.closed = threading.Event()
        self.listener = None
        self.clients = threading.BoundedSemaphore(8)
        self.metadata = {'id': self.id, 'pid': os.getpid(), 'version': __version__,
                         'protocol_version': PROTOCOL, 'source': str(source) if source else None}

    def start(self):
        if self.closed.is_set():
            raise RuntimeError('A closed bridge cannot be restarted')
        if self.listener is not None:
            return self.metadata
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.bind(('127.0.0.1', 0))
            listener.listen(8)
            listener.settimeout(.2)
            self.metadata['port'] = listener.getsockname()[1]
            self.metadata['host'] = '127.0.0.1'
            descriptor = {**self.metadata, 'token': self.token}
            with os.fdopen(os.open(self.path, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'w', encoding='utf-8') as stream:
                json.dump(descriptor, stream, ensure_ascii=False)
            self.listener = listener
            threading.Thread(target=self._accept, name='markprompt-live-listener', daemon=True).start()
            return self.metadata
        except BaseException:
            listener.close()
            raise

    def _accept(self):
        while not self.closed.is_set():
            try:
                stream, _address = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            if not self.clients.acquire(blocking=False):
                stream.close()
                continue
            threading.Thread(target=self._serve, args=(stream,), name='markprompt-live-client', daemon=True).start()

    def _serve(self, stream):
        with stream:
            try:
                stream.settimeout(3)
                message = receive(stream, MAX_REQUEST)
                answer = self.submit(message)
                stream.settimeout(3)
                try:
                    send(stream, answer)
                except LiveError:
                    send(stream, response(False, 'frame_too_large', message='Use a bounded snapshot'))
            except (LiveError, OSError, ValueError) as error:
                try:
                    send(stream, response(False, getattr(error, 'code', 'connection_error'), message=str(error)))
                except (OSError, LiveError):
                    pass
            finally:
                self.clients.release()

    def submit(self, message):
        if message.get('protocol_version') != PROTOCOL:
            return response(False, 'protocol_mismatch')
        if (message.get('window') != self.id or not isinstance(message.get('token'), str)
                or not hmac.compare_digest(message['token'], self.token)):
            return response(False, 'unauthorized')
        method = message.get('method')
        if not isinstance(method, str):
            return response(False, 'invalid_request')
        if not isinstance(message.get('params', {}), dict):
            return response(False, 'invalid_request')
        if method == 'ping':
            return response(window=dict(self.metadata))
        if method == 'result':
            if not isinstance(message.get('params', {}).get('request_id'), str):
                return response(False, 'invalid_request')
            return self.result(message.get('params', {}).get('request_id'))
        if method not in {'snapshot', 'execute', 'respond'}:
            return response(False, 'unknown_method')
        request_id, params = message.get('request_id'), message.get('params', {})
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 100 or not isinstance(params, dict):
            return response(False, 'invalid_request')
        try:
            timeout = float(message.get('timeout', 5))
            if not .1 <= timeout <= 60:
                raise ValueError()
        except (TypeError, ValueError):
            return response(False, 'invalid_timeout')
        fingerprint = hashlib.sha256(json.dumps([method, params], sort_keys=True).encode('utf-8')).hexdigest()
        with self.lock:
            if self.closed.is_set():
                return response(False, 'window_closed', executed=False)
            task = self.records.get(request_id)
            if task and task.fingerprint != fingerprint:
                return response(False, 'request_id_conflict', request_id=request_id)
            if task is None:
                # Retention is bounded. Pending work is never evicted.
                if len(self.records) >= MAX_RECORDS:
                    oldest = next((key for key, old in self.records.items() if old.done.is_set()), None)
                    if oldest is None:
                        return response(False, 'busy', executed=False)
                    self.records.pop(oldest)
                task = Request(request_id, method, params, fingerprint, monotonic()+timeout)
                try:
                    self.requests.put_nowait(task)
                except queue.Full:
                    return response(False, 'busy', executed=False)
                self.records[request_id] = task
        if not task.done.wait(timeout):
            with task.lock:
                if task.status == 'queued':
                    task.status = 'cancelled'
                    task.result = response(False, 'request_expired', request_id=task.id, executed=False)
                    task.done.set()
                elif task.status == 'running':
                    return response(False, 'request_pending', request_id=task.id, executed=None)
        return self.result(task.id)

    def result(self, request_id):
        with self.lock:
            task = self.records.get(request_id)
            if task is None:
                return response(False, 'request_not_found', request_id=request_id, executed=None)
            with task.lock:
                if task.result is not None:
                    return task.result
                code = 'result_unavailable' if task.done.is_set() else 'request_pending'
                return response(False, code, request_id=request_id, executed=None, status=task.status)

    def drain(self, handler, count=4):
        """Call only on the GUI thread. Network workers never call handler."""
        for _index in range(count):
            try:
                task = self.requests.get_nowait()
            except queue.Empty:
                break
            with task.lock:
                if task.status != 'queued':
                    continue
                if monotonic() >= task.deadline or self.closed.is_set():
                    task.status = 'cancelled'
                    task.result = response(False, 'request_expired', request_id=task.id, executed=False)
                    task.done.set()
                    continue
                task.status = 'running'
            try:
                result = handler(task.method, task.params)
                answer = {**result, 'protocol_version': PROTOCOL, 'request_id': task.id, 'window_id': self.id}
                size = len(json.dumps(answer, ensure_ascii=False, allow_nan=False).encode('utf-8'))
            except Exception as error:
                answer = response(False, 'internal_error', message=str(error), request_id=task.id)
                size = len(json.dumps(answer).encode('utf-8'))
            with task.lock:
                task.result, task.status = answer, 'done'
                task.size = size
                task.done.set()
            with self.lock:
                total = sum(old.size for old in self.records.values() if old.result is not None)
                for old in self.records.values():
                    if total <= CACHE_BYTES:
                        break
                    if old is not task and old.done.is_set() and old.result is not None:
                        total -= old.size
                        old.result = None
        return not self.requests.empty()

    def close(self):
        self.closed.set()
        if self.listener is not None:
            self.listener.close()
        with self.lock:
            for task in self.records.values():
                with task.lock:
                    if task.status == 'queued':
                        task.status = 'cancelled'
                        task.result = response(False, 'window_closed', request_id=task.id, executed=False)
                        task.done.set()
        if self.path.is_file():
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                pass  # Stale descriptors are ignored by discovery after close.


def rpc(descriptor, method, params=None, timeout=5, request_id=None):
    request_id = request_id or uuid4().hex
    if (descriptor.get('host') != '127.0.0.1' or descriptor.get('protocol_version') != PROTOCOL
            or not isinstance(descriptor.get('port'), int) or not 1 <= descriptor['port'] <= 65535
            or not isinstance(descriptor.get('id'), str) or not isinstance(descriptor.get('token'), str)):
        raise LiveError('invalid_descriptor', 'Invalid local window descriptor')
    message = {'protocol_version': PROTOCOL, 'window': descriptor['id'], 'token': descriptor['token'],
               'method': method, 'params': params or {}, 'timeout': timeout, 'request_id': request_id}
    try:
        with socket.create_connection(('127.0.0.1', descriptor['port']), timeout=min(timeout+1, 61)) as stream:
            stream.settimeout(timeout+1)
            send(stream, message, MAX_REQUEST)
            return receive(stream, MAX_RESPONSE)
    except LiveError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise LiveError('connection_error', 'GUI connection failed; command outcome may be unknown. Query its request ID before retrying.', request_id) from error


def _probe(path):
    try:
        with path.open('rb') as stream:
            raw = stream.read(8193)
        if len(raw) > 8192:
            return None
        descriptor = json.loads(raw.decode('utf-8'))
        if not isinstance(descriptor, dict) or path.stem != descriptor.get('id'):
            return None
        answer = rpc(descriptor, 'ping', timeout=.2)
        if answer.get('ok') and answer.get('window', {}).get('id') == descriptor['id']:
            return descriptor
    except (OSError, ValueError, LiveError, KeyError, TypeError):
        pass
    return None


def windows(directory=None):
    root = Path(directory) if directory is not None else runtime_directory()
    paths = []
    for path in root.glob('*.json'):
        try:
            paths.append((path.stat().st_mtime_ns, path))
        except OSError:
            pass
    candidates = [path for _stamp, path in sorted(paths, reverse=True)[:128]]
    if not candidates:
        return []
    with ThreadPoolExecutor(max_workers=8, thread_name_prefix='markprompt-live-discovery') as pool:
        return [item for item in pool.map(_probe, candidates) if item is not None]


def select_window(window_id=None, directory=None):
    if window_id:
        root = Path(directory) if directory is not None else runtime_directory()
        if len(window_id) != 32 or any(char not in '0123456789abcdef' for char in window_id):
            raise LiveError('window_not_found', 'Unknown window ID')
        descriptor = _probe(root/(window_id+'.json'))
        found = [descriptor] if descriptor else []
    else:
        found = windows(directory)
    if not found:
        raise LiveError('window_not_found', 'No reachable MarkPrompt window; start or restart the updated GUI first')
    if len(found) != 1:
        raise LiveError('ambiguous_window', 'Multiple windows are open; select one using --window ID')
    return found[0]
