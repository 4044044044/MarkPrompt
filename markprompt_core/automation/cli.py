"""Read and control a running window from the CLI."""
import json
from pathlib import Path
from time import monotonic, sleep
from uuid import uuid4

from markprompt_core import __version__
from markprompt_core.commands.catalog import REGISTRY
from markprompt_core.automation.transport import LiveError, rpc, select_window, windows
from markprompt_core.localization import tr


# Match both the code and the known transport text. Unknown diagnostics retain
# their details, and messages returned by the running GUI never pass here.
TRANSPORT_MESSAGES = {
    ('window_not_found', 'Unknown window ID'): 'cli.window_unknown',
    ('window_not_found', 'No reachable MarkPrompt window; start or restart the updated GUI first'): 'cli.window_not_found',
    ('ambiguous_window', 'Multiple windows are open; select one using --window ID'): 'cli.window_ambiguous',
    ('connection_error', 'GUI connection failed; command outcome may be unknown. Query its request ID before retrying.'): 'cli.connection_failed',
    ('invalid_descriptor', 'Invalid local window descriptor'): 'cli.descriptor_invalid',
    ('connection_closed', 'Connection closed before the complete frame arrived'): 'cli.connection_closed',
    ('frame_too_large', 'Frame exceeds the protocol size limit'): 'cli.frame_too_large',
    ('frame_too_large', 'Response exceeds the protocol size limit'): 'cli.response_too_large',
    ('invalid_request', 'Expected a UTF-8 JSON object'): 'cli.expected_utf8_object',
    ('invalid_request', 'Expected a JSON object'): 'cli.expected_object',
}


def configure(parser, language='en'):
    text = lambda key: tr(language, 'cli.' + key)
    modes = parser.add_subparsers(dest='gui_mode', required=True)
    for name in ['windows', 'snapshot', 'exec', 'respond', 'wait', 'result']:
        mode = modes.add_parser(name, help=text('gui_' + name), description=text('gui_' + name))
        mode.add_argument('--runtime-dir', type=Path, help=text('runtime_dir'))
        mode.add_argument('--json', action='store_true', help=text('json'))
        mode.add_argument('--timeout', type=float, default=10, help=text('timeout'))
        if name != 'windows':
            mode.add_argument('--window', help=text('window'))
        if name == 'snapshot':
            mode.add_argument('--full', action='store_true', help=text('full'))
        elif name == 'exec':
            mode.add_argument('-c', '--command', action='append', required=True, help=text('command'))
            mode.add_argument('--no-wait', action='store_true', help=text('no_wait'))
            mode.add_argument('--request-id', help=text('request_id'))
            mode.add_argument('--expect-sha256', help=text('expect_sha256'))
            mode.add_argument('--expect-file', help=text('expect_file'))
        elif name == 'respond':
            mode.add_argument('--confirmation', required=True, help=text('confirmation'))
            mode.add_argument('choice', choices=['save', 'discard', 'cancel', 'y', 'n'], help=text('choice'))
            mode.add_argument('--request-id', help=text('request_id'))
        elif name == 'result':
            mode.add_argument('request_id', help=text('query_request_id'))


def exit_code(value):
    code = value.get('code', 'ok')
    if code == 'confirmation_required':
        return 3
    if code == 'disk_changed':
        return 5
    if code in {'invalid_arguments', 'invalid_request', 'invalid_timeout'}:
        return 2
    if code in {'request_pending', 'request_expired', 'request_not_found', 'result_unavailable', 'wait_timeout'}:
        return 7
    return 0 if value.get('ok') else 1


def wait_ready(descriptor, snapshot, timeout, check_job=False, language='en'):
    deadline = monotonic()+timeout
    check_job = check_job or snapshot['find']['in_progress']
    generation = snapshot.get('find', {}).get('job', {}).get('generation')
    while not snapshot.get('ready') and not snapshot['interaction']['closed']:
        if snapshot['interaction']['pending']:
            return {'ok': False, 'code': 'confirmation_required', 'snapshot': snapshot}
        if monotonic() >= deadline:
            return {'ok': False, 'code': 'wait_timeout', 'snapshot': snapshot}
        sleep(.04)
        observed = rpc(descriptor, 'snapshot', timeout=max(.1, min(timeout, deadline-monotonic())))
        if not observed.get('ok'):
            return observed
        snapshot = observed['snapshot']
        job = snapshot.get('find', {}).get('job', {})
        if generation is not None and job.get('generation') != generation:
            return {'ok': False, 'code': 'state_changed', 'message': tr(language, 'cli.search_changed'), 'snapshot': snapshot}
    job = snapshot.get('find', {}).get('job', {})
    if check_job and job.get('error'):
        return {'ok': False, 'code': 'search_failed', 'message': job['error'], 'snapshot': snapshot}
    return {'ok': True, 'code': 'ok', 'snapshot': snapshot}


def run(args):
    language = getattr(args, 'language', None) or getattr(args, '_cli_language', 'en')
    report = {'schema_version': 1, 'version': __version__, 'gui_control': True}
    try:
        if not .1 <= args.timeout <= 60:
            raise LiveError('invalid_arguments', tr(language, 'cli.timeout_range'))
        if args.gui_mode == 'windows':
            found = windows(args.runtime_dir)
            answer = {'ok': True, 'code': 'ok', 'windows': [
                {key: item.get(key) for key in ['id', 'pid', 'version', 'protocol_version', 'source']} for item in found]}
        else:
            descriptor = select_window(args.window, args.runtime_dir)
            if args.gui_mode in {'snapshot', 'wait'}:
                answer = rpc(descriptor, 'snapshot', {'full': getattr(args, 'full', False)}, args.timeout)
                if args.gui_mode == 'wait' and answer.get('ok'):
                    pending = answer['snapshot']['interaction']['pending']
                    answer = ({'ok': False, 'code': 'confirmation_required', 'snapshot': answer['snapshot']}
                              if pending else wait_ready(descriptor, answer['snapshot'], args.timeout, check_job=True, language=language))
            elif args.gui_mode == 'result':
                answer = rpc(descriptor, 'result', {'request_id': args.request_id}, args.timeout)
            else:
                commands = args.command if args.gui_mode == 'exec' else [args.choice]
                if args.gui_mode == 'exec' and len(commands) > 1 and (args.request_id or args.expect_file or args.expect_sha256):
                    raise LiveError('invalid_arguments', tr(language, 'cli.single_command'))
                results = []
                for command in commands:
                    request_id = args.request_id or uuid4().hex
                    if args.gui_mode == 'exec':
                        params = {'command': command, 'expect_file': args.expect_file, 'expect_sha256': args.expect_sha256}
                    else:
                        params = {'choice': command, 'confirmation_id': args.confirmation}
                    answer = rpc(descriptor, 'execute' if args.gui_mode == 'exec' else 'respond', params,
                                 timeout=args.timeout, request_id=request_id)
                    if answer.get('ok') and answer.get('snapshot') and not getattr(args, 'no_wait', False):
                        request = REGISTRY.parse(command) if command.startswith('/') else None
                        completed = wait_ready(descriptor, answer['snapshot'], args.timeout,
                                               check_job=bool(request and request.spec.name in {'find', 'files'}), language=language)
                        answer['snapshot'] = completed.get('snapshot', answer['snapshot'])
                        if not completed.get('ok'):
                            answer.update(ok=False, code=completed['code'], message=completed.get('message', ''))
                    results.append(answer)
                    if not answer.get('ok') or answer.get('status') == 'needs_confirmation':
                        break
                answer = {**answer, 'results': results}
            answer['window_id'] = descriptor['id']
        report.update(answer)
        code = exit_code(report)
    except LiveError as error:
        key = TRANSPORT_MESSAGES.get((error.code, str(error)))
        report.update(ok=False, code=error.code, message=tr(language, key) if key else str(error))
        if error.request_id:
            report['request_id'] = error.request_id
        code = 2 if error.code == 'invalid_arguments' else 6
    report['exit_code'] = code
    if code:
        report['ok'] = False
    print(json.dumps(report, ensure_ascii=False, indent=None if args.json else 2))
    return code
