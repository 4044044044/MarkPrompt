"""Describe session state and supported Markdown elements for automation."""
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
from uuid import uuid4

from markprompt_core import __version__
from markprompt_core.commands.catalog import REGISTRY, GUI_COMMANDS
from markprompt_core.documents.content import iter_search_hits
from markprompt_core.documents.markdown import inline_images, inline_links
from markprompt_core.storage.local import StorageError

SCHEMA_VERSION = 1
TEXT_LIMIT = 65536
ITEM_LIMIT = 200
STRUCTURE_LIMIT = 500


def section(items, limit=ITEM_LIMIT):
    kept, total = [], 0
    for item in items:
        total += 1
        if len(kept) < limit:
            kept.append(item)
    return {'items': kept, 'total': total, 'omitted': total - len(kept), 'truncated': total > len(kept)}


def excerpt(text, line=1, full=False):
    lines = text.splitlines(True)
    start_line = 1 if full or len(text) <= TEXT_LIMIT else max(1, min(line, len(lines)) - 30)
    start = sum(map(len, lines[:start_line - 1]))
    body = text[start:] if full else text[start:start + TEXT_LIMIT]
    return {'text': body, 'start_offset': start, 'end_offset': start + len(body),
            'total_chars': len(text), 'start_line': start_line,
            'complete': start == 0 and len(body) == len(text)}


def syntax(argument):
    value = argument.strip()
    full = value == '--full' or value.startswith('--full ')
    if full:
        value = value[6:].strip()
    if value.startswith('-- '):
        value = value[3:]
    elif value.startswith('-'):
        raise ValueError('Usage: /snapshot [--full] [--] [file.json]')
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    if value and Path(value).suffix.lower() != '.json':
        raise ValueError('Snapshot destination must end in .json')
    return full, value


def structure(text, note, paths):
    """Describe supported Markdown elements, retaining raw source as the authority."""
    lines, outside, references, fence = text.splitlines(), [], {}, None
    for line in lines:
        match = re.match(r'^\s{0,3}(`{3,}|~{3,})(.*)$', line)
        if match:
            token = match[1]
            if fence is None:
                fence = (token[0], len(token))
            elif token[0] == fence[0] and len(token) >= fence[1] and not match[2].strip():
                fence = None
            outside.append(False)
            continue
        outside.append(fence is None)
        if fence is None:
            match = re.match(r'^\s{0,3}\[([^\]]+)\]:\s*(?:<([^>]+)>|(\S+))', line)
            if match:
                references[' '.join(match[1].split()).casefold()] = match[2] or match[3]

    def elements():
        fence = None
        for number, line in enumerate(lines, 1):
            marker = re.match(r'^\s{0,3}(`{3,}|~{3,})(.*)$', line)
            if marker:
                token = marker[1]
                if fence is None:
                    fence = (token[0], len(token), number, marker[2].strip())
                elif token[0] == fence[0] and len(token) >= fence[1] and not marker[2].strip():
                    yield {'type': 'code_block', 'line': fence[2], 'end_line': number, 'language': fence[3][:80], 'closed': True}
                    fence = None
                continue
            if not outside[number - 1]:
                continue
            heading = re.match(r'^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$', line)
            if heading:
                yield {'type': 'heading', 'line': number, 'level': len(heading[1]), 'text': heading[2][:300], 'text_truncated': len(heading[2]) > 300}
            elif number < len(lines) and outside[number] and line.strip() and re.fullmatch(r'\s{0,3}(?:=+|-+)\s*', lines[number]):
                yield {'type': 'heading', 'line': number, 'end_line': number + 1, 'level': 1 if lines[number].lstrip().startswith('=') else 2, 'text': line[:300], 'text_truncated': len(line) > 300}
            task = re.match(r'^\s*[-*+]\s+\[([ xX])\]\s*(.*)', line)
            if task:
                yield {'type': 'task', 'line': number, 'checked': task[1].lower() == 'x', 'text': task[2][:300], 'text_truncated': len(task[2]) > 300}
            if re.match(r'^\s*>', line):
                yield {'type': 'quote', 'line': number}
            if '|' in line and number < len(lines) and re.fullmatch(r'\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*', lines[number]):
                yield {'type': 'table', 'line': number}
            # Inline code contents are data, not active links or images.
            inline = re.sub(r'(`+).*?\1', lambda match: ' ' * len(match[0]), line)
            for start, end, label, target in inline_links(inline, references):
                yield {'type': 'link', 'line': number, 'start': start, 'end': end, 'label': label[:300],
                       'target': target[:2048], 'metadata_truncated': len(label) > 300 or len(target) > 2048}
            for start, end, alt, target in inline_images(inline, references):
                image = {'type': 'image', 'line': number, 'start': start, 'end': end, 'alt': alt[:300],
                         'target': target[:2048], 'metadata_truncated': len(alt) > 300 or len(target) > 2048,
                         'decode_checked': False}
                try:
                    if len(target) > 2048:
                        raise StorageError('path_too_long')
                    path = paths.image(target, note)
                    image.update(path=str(path), resolution='local_file' if path.is_file() else 'not_file',
                                 format_supported=path.suffix.lower() in {'.png', '.jpg', '.jpeg'})
                except StorageError as error:
                    image.update(path=None, resolution=error.code)
                yield image
        if fence is not None:
            yield {'type': 'code_block', 'line': fence[2], 'end_line': len(lines), 'language': fence[3][:80], 'closed': False}
    return section(elements(), STRUCTURE_LIMIT)


def command_states(app, pending, kind):
    result = []
    for spec in sorted(REGISTRY.specs.values(), key=lambda spec: spec.name):
        reason = None
        if kind == 'cli' and spec.name in GUI_COMMANDS:
            reason = 'gui_required'
        elif getattr(app, 'closed', False) and not spec.inspection:
            reason = 'session_closed'
        elif pending and not spec.inspection:
            reason = 'confirmation_pending'
        elif any(app.states.has(state) for state in spec.blocked_states):
            reason = spec.refusal
        elif spec.requirement == 'document' and app.current_file is None:
            reason = 'no_note'
        elif spec.requirement == 'document' and app.current_file.suffix.lower() == '.txt':
            reason = 'text_readonly'
        elif spec.requirement == 'workspace' and app.workspace is None:
            reason = 'workspace_needed'
        elif spec.name in {'replace', 'delete', 'next', 'prev'} and not app.search_term:
            reason = 'search_needed'
        result.append({'name': spec.name, 'usage': spec.usage, 'route_available': reason is None,
                       'reason': reason, 'navigation': spec.navigation})
    return result


def capture(app, full=False):
    """Observe a single in-memory session without refreshing, saving, or navigating it."""
    surface = app._snapshot_surface()
    kind, pending = surface['kind'], surface.get('pending')
    text, path = app.buffer_text, app.buffer_path
    position = max(1, surface.get('position_line') or getattr(app, '_last_position_line', 1) or 1)
    document = None
    if path is not None and text is not None:
        document = {'path': str(path), 'active': path == app.current_file,
                    'source': 'memory_buffer', 'content_trust': 'user_data',
                    'dirty': app.buffer_dirty, 'dirty_lines': sorted(app.dirty_lines),
                    'disk_version_at_load': app.document.version.hex() if app.document.version else None,
                    'text_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
                    'line_count': len(text.splitlines()), 'content': excerpt(text, position, full),
                    'can_undo': bool(app.buffer._undo), 'can_redo': bool(app.buffer._redo),
                    'structure': structure(text, path, app.storage.paths) if path.suffix.lower() == '.md' else section(())}
    scope, scoped_line = app.search_scope, app.search_scope_line
    hits = section({'line': hit.line, 'start': hit.start, 'end': hit.end,
                    'in_scope': scope != 'line' or hit.line == scoped_line}
                   for hit in iter_search_hits(text, app.search_term, app.search_fuzzy))
    point = app.navigation.search
    find_future = getattr(app, '_find_future', None)
    frames = [frame.kind for frame in app.states.frames]
    return {'schema': 'markprompt.ai_snapshot', 'schema_version': SCHEMA_VERSION,
            'app_version': __version__, 'snapshot_id': uuid4().hex,
            'captured_at': datetime.now(timezone.utc).isoformat(),
            'source': {'kind': kind, 'scope': 'current_process_session'},
            'context': {'workspace': str(app.workspace) if app.workspace else None,
                        'directory': str(app.current_dir) if app.current_dir else None,
                        'current_file': str(app.current_file) if app.current_file else None,
                        'view': app.view_mode},
            'interaction': {'business': frames, 'active': app.states.active,
                            'max_depth': app.states.MAX_DEPTH, 'pending': pending,
                            'plain_input': 'confirmation_choice' if pending else app.states.active or 'path',
                            'closed': bool(getattr(app, 'closed', False))},
            'document': document, 'surface': surface,
            'search': {'active': app.search_mode, 'term': app.search_term, 'ignore_case': app.search_fuzzy,
                       'scope': scope, 'scope_line': scoped_line, 'hits': hits},
            'listing': section({'number': n, 'path': str(p), 'name': p.name,
                                'type': 'directory' if p.is_dir() else 'file', 'find_match': p in app.find_file_hits}
                               for n, p in app.listed_items.items()),
            'find': {'term': app.find_term, 'in_progress': find_future is not None,
                     'job': {'kind': app.search.job_kind, 'status': app.search.job_status,
                             'error': app.search.job_error, 'generation': app.search.generation},
                     'results': section({'path': str(p), 'matching_lines': count} for p, count in app._find_rows)},
            'navigation': {'back_to_find': point is not None,
                           'return_search': {'term': point.term, 'directory': str(point.directory),
                                             'result_count': len(point.rows), 'position': point.top_index,
                                             'in_progress': point.pending} if point else None},
            'commands': command_states(app, pending, kind),
            'limits': {'body_chars': None if full else TEXT_LIMIT, 'items_per_section': ITEM_LIMIT,
                       'structure_items': STRUCTURE_LIMIT, 'offset_units': 'unicode_codepoints',
                       'line_base': 1, 'column_base': 0, 'end_exclusive': True,
                       'markdown_structure': 'supported_subset', 'image_pixels_included': False,
                       'disk_rechecked': False, 'restorable_backup': False}}
