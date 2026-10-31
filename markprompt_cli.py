"""Run MarkPrompt commands from a terminal or script."""
import argparse
import json
from pathlib import Path
import sys

from markprompt_core import __version__
from markprompt_core.application.session import Session, capabilities
from markprompt_core.storage.local import StorageError

SCHEMA_VERSION = 1
MAX_SCRIPT_BYTES = 8 * 1024 * 1024


class UsageError(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


def parser():
    result = Parser(description='Native MarkPrompt commands without opening a window.')
    result.add_argument('--version', action='version', version=__version__)
    modes = result.add_subparsers(dest='mode', required=True)
    listing = modes.add_parser('commands', help='List command syntax and CLI capabilities')
    listing.add_argument('--json', action='store_true')
    gui = modes.add_parser('gui', help='Observe or control an already running window')
    from markprompt_core.automation.cli import configure
    configure(gui)
    for name, help_text in [('exec', 'Execute commands in a single session'),
                            ('run', 'Run a JSON or line-based workflow'),
                            ('shell', 'Keep a command session alive')]:
        mode = modes.add_parser(name, help=help_text)
        mode.add_argument('--workspace', type=Path, help='Explicit workspace; never inferred from the app directory')
        mode.add_argument('--file', type=Path, help='Open a note before executing commands')
        mode.add_argument('--config', type=Path, help='Optional settings file; preferences otherwise stay in this process')
        mode.add_argument('--json', action='store_true', help='JSON report; shell emits JSON lines')
        mode.add_argument('--include-text', action='store_true', help='Include text in each document state')
        mode.add_argument('--allow-dirty', action='store_true', help='Allow a returned in-memory draft without /save')
        if name == 'exec':
            mode.add_argument('-c', '--command', action='append', required=True)
        elif name == 'run':
            mode.add_argument('--script', required=True, help='Workflow file, or - for stdin')
            mode.add_argument('--script-format', choices=['auto', 'json', 'lines'], default='auto')
            mode.add_argument('--continue-on-error', action='store_true')
    return result


def envelope(**values):
    return {'schema_version': SCHEMA_VERSION, 'version': __version__, **values}


def failure(code, message, exit_code):
    return envelope(ok=False, code=code, message=str(message), exit_code=exit_code)


def output(value, as_json):
    if as_json:
        print(json.dumps(value, ensure_ascii=False))
        return
    if 'commands' in value:
        for command in value['commands']:
            marker = '' if command['cli_supported'] else ' [GUI only]'
            print('/%s %s%s\n  %s' % (command['name'], command['usage'], marker, command['description']))
        return
    for result in value.get('results', []):
        label = 'PENDING' if result['status'] == 'needs_confirmation' else 'OK' if result['ok'] else 'ERROR'
        print('%s %s' % (label, result['command']))
        if result['state'].get('pending'):
            print('Reply: ' + ', '.join(result['state']['pending']['choices']))
        if result['message']:
            print(result['message'])
        data = result['data']
        if 'text' in data:
            print(data['text'], end='' if data['text'].endswith('\n') else '\n')
        elif data:
            print(json.dumps(data, ensure_ascii=False))
    if value.get('message'):
        print(value['message'])
    state = value.get('state', {})
    if state:
        print('%s %s' % (state['prompt'], state.get('directory') or ''))
        if state.get('pending'):
            print('Confirmation required: ' + ', '.join(state['pending']['choices']))
        document = state.get('document')
        if document and document['dirty'] and 'text' in document:
            print('UNSAVED DRAFT:\n' + document['text'])


def read_script(path, format_name):
    if path == '-':
        content = sys.stdin.read(MAX_SCRIPT_BYTES + 1)
        if len(content.encode('utf-8')) > MAX_SCRIPT_BYTES:
            raise UsageError('Workflow exceeds 8 MiB')
    else:
        with Path(path).open('rb') as stream:
            data = stream.read(MAX_SCRIPT_BYTES + 1)
        if len(data) > MAX_SCRIPT_BYTES:
            raise UsageError('Workflow exceeds 8 MiB')
        content = data.decode('utf-8-sig')
    content = content.lstrip('\ufeff')
    if format_name == 'auto':
        format_name = 'json' if (path != '-' and Path(path).suffix.lower() == '.json') or content.lstrip().startswith('[') else 'lines'
    if format_name == 'json':
        try:
            values = json.loads(content)
        except ValueError as error:
            raise UsageError('Invalid JSON workflow: ' + str(error)) from error
        if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
            raise UsageError('A JSON workflow must be an array of command strings')
        return values
    return [line.rstrip('\r') for line in content.splitlines()
            if line.strip() and not line.lstrip().startswith('#')]


def finish(session, results, allow_dirty=False, include_text=False):
    errors = [result for result in results if not result['ok']]
    if errors:
        code, message = errors[0]['code'], errors[0]['message']
        exit_code = 5 if code == 'disk_changed' else 2 if code == 'invalid_arguments' else 3 if code == 'confirmation_required' else 1
    elif session.pending:
        code, message, exit_code = 'confirmation_required', 'An explicit response is required', 3
    elif session.buffer_dirty and not allow_dirty:
        code, message, exit_code = 'unsaved_changes', 'Changes remain in memory. Add /save or explicitly use --allow-dirty.', 4
    else:
        code, message, exit_code = 'ok', '', 0
    return envelope(ok=exit_code == 0, code=code, message=message, exit_code=exit_code,
                    results=results, state=session.snapshot(include_text or session.buffer_dirty), gui_control=False)


def run(args):
    if args.mode == 'gui':
        from markprompt_core.automation.cli import run as run_gui
        return run_gui(args)
    if args.mode == 'commands':
        output(envelope(ok=True, commands=capabilities(), gui_control=False), args.json)
        return 0
    commands = read_script(args.script, args.script_format) if args.mode == 'run' else args.command if args.mode == 'exec' else None
    session = Session(workspace=args.workspace, config_path=args.config)
    try:
        return run_session(args, session, commands)
    except KeyboardInterrupt:
        report = finish(session, [], args.allow_dirty, True)
        report.update(ok=False, code='cancelled', message='Interrupted', exit_code=130)
    except (UsageError, UnicodeError, OSError) as error:
        report = finish(session, [], args.allow_dirty, True)
        report.update(ok=False, code='io_error', message=str(error), exit_code=2)
    except Exception as error:
        report = finish(session, [], args.allow_dirty, True)
        report.update(ok=False, code='internal_error', message=str(error), exit_code=70)
    output(report, args.json)
    return report['exit_code']


def run_session(args, session, commands):
    if args.file is not None:
        target = args.file
        if not target.is_absolute():
            target = (session.current_dir or Path.cwd()) / target
        setup = session.execute('/open ' + str(target), args.include_text)
        if not setup['ok']:
            report = finish(session, [setup], args.allow_dirty, args.include_text)
            output(report, args.json)
            return report['exit_code']
    if args.mode == 'shell':
        last = []
        while not session.closed:
            if sys.stdin.isatty() and not args.json:
                print(session.snapshot()['prompt'] + ' ', end='', file=sys.stderr, flush=True)
            line = sys.stdin.readline(MAX_SCRIPT_BYTES + 1)
            if not line:
                break
            if len(line.encode('utf-8')) > MAX_SCRIPT_BYTES:
                raise UsageError('A command exceeds 8 MiB')
            result = session.execute(line.rstrip('\r\n'), args.include_text)
            last = [result]
            if args.json:
                print(json.dumps(envelope(event='command', **result), ensure_ascii=False), flush=True)
            else:
                output(envelope(results=[result]), False)
        report = finish(session, last, args.allow_dirty, args.include_text)
        report['event'] = 'session_end'
        if not args.json:
            report['results'] = []
        output(report, args.json)
        return report['exit_code']
    results = []
    for value in commands:
        result = session.execute(value, args.include_text)
        results.append(result)
        if session.closed or (not result['ok'] and not getattr(args, 'continue_on_error', False)):
            break
    report = finish(session, results, args.allow_dirty, args.include_text)
    output(report, args.json)
    return report['exit_code']


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    try:
        return run(parser().parse_args(argv))
    except (UsageError, UnicodeError, ValueError) as error:
        output(failure('invalid_arguments', error, 2), '--json' in argv)
        return 2
    except (StorageError, OSError) as error:
        output(failure(getattr(error, 'code', 'io_error'), error, 1), '--json' in argv)
        return 1
    except KeyboardInterrupt:
        output(failure('cancelled', 'Interrupted', 130), '--json' in argv)
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
