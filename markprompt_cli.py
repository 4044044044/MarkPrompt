"""Run MarkPrompt commands from a terminal or script."""
import argparse
from functools import partial
import json
from pathlib import Path
import re
import sys

from markprompt_core import __version__
from markprompt_core.application.session import Session, capabilities
from markprompt_core.localization import LANGUAGES, tr
from markprompt_core.storage.local import StorageError, StorageServices

SCHEMA_VERSION = 1
MAX_SCRIPT_BYTES = 8 * 1024 * 1024


class UsageError(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    """Keep argparse's language scoped to this parser and its children."""
    def __init__(self, *args, language='en', **kwargs):
        self.language = LANGUAGES.normalize(language)
        kwargs['add_help'] = False
        kwargs['formatter_class'] = partial(HelpFormatter, language=self.language)
        super().__init__(*args, **kwargs)
        self._positionals.title = tr(self.language, 'cli.positionals')
        self._optionals.title = tr(self.language, 'cli.options')
        self.add_argument('-h', '--help', action='help', help=tr(self.language, 'cli.help'))

    def add_subparsers(self, **kwargs):
        kwargs.setdefault('parser_class', partial(Parser, language=self.language))
        return super().add_subparsers(**kwargs)

    def localized_error(self, message):
        for pattern, key in [
                (r'^argument (.+?): (.+)$', 'cli.error_argument'),
                (r'^the following arguments are required: (.+)$', 'cli.error_required'),
                (r'^unrecognized arguments: (.+)$', 'cli.error_unrecognized'),
                (r'^invalid choice: (.+) \(choose from (.+)\)$', 'cli.error_choice'),
                (r'^invalid (.+) value: (.+)$', 'cli.error_type'),
                (r'^expected (\d+) arguments$', 'cli.error_count'),
                (r'^ignored explicit argument (.+)$', 'cli.error_explicit'),
                (r'^ambiguous option: (.+) could match (.+)$', 'cli.error_ambiguous')]:
            match = re.match(pattern, message)
            if match:
                values = match.groups()
                if key == 'cli.error_argument':
                    values = (values[0], self.localized_error(values[1]))
                return tr(self.language, key) % values
        for text, key in [('expected one argument', 'cli.error_one'),
                          ('expected at least one argument', 'cli.error_at_least_one'),
                          ('expected at most one argument', 'cli.error_at_most_one')]:
            if message == text:
                return tr(self.language, key)
        return message

    def error(self, message):
        raise UsageError(self.localized_error(message))


class HelpFormatter(argparse.HelpFormatter):
    def __init__(self, *args, language='en', **kwargs):
        self.language = language
        super().__init__(*args, **kwargs)

    def _format_usage(self, usage, actions, groups, prefix):
        return super()._format_usage(usage, actions, groups,
                                     tr(self.language, 'cli.usage') if prefix is None else prefix)


def selected_language(argv):
    """Choose help language before argparse exits, without changing saved settings."""
    values = {}
    for index, value in enumerate(argv):
        if value == '--':
            break
        for option in ('--language', '--config'):
            if value == option and index + 1 < len(argv):
                values[option] = argv[index + 1]
            elif value.startswith(option + '='):
                values[option] = value.split('=', 1)[1]
    if '--language' in values:
        return LANGUAGES.normalize(values['--language'])
    if '--config' in values:
        try:
            return LANGUAGES.normalize(StorageServices().preferences.load(Path(values['--config'])).get('language'))
        except (StorageError, OSError, ValueError):
            pass  # Session reports invalid settings during execution.
    return 'en'


def parser(language='en'):
    text = lambda key: tr(language, 'cli.' + key)
    result = Parser(language=language, description=text('description'))
    result.set_defaults(_cli_language=LANGUAGES.normalize(language))
    result.add_argument('--version', action='version', version=__version__, help=text('version'))
    result.add_argument('--language', choices=LANGUAGES.codes(), help=text('language'))
    modes = result.add_subparsers(dest='mode', required=True)
    listing = modes.add_parser('commands', help=text('commands'), description=text('commands'))
    listing.add_argument('--json', action='store_true', help=text('json'))
    gui = modes.add_parser('gui', help=text('gui'), description=text('gui'))
    from markprompt_core.automation.cli import configure
    configure(gui, language)
    for name in ('exec', 'run', 'shell'):
        mode = modes.add_parser(name, help=text(name), description=text(name))
        mode.add_argument('--workspace', type=Path, help=text('workspace'))
        mode.add_argument('--file', type=Path, help=text('file'))
        mode.add_argument('--config', type=Path, help=text('config'))
        mode.add_argument('--json', action='store_true', help=text('json'))
        mode.add_argument('--include-text', action='store_true', help=text('include_text'))
        mode.add_argument('--allow-dirty', action='store_true', help=text('allow_dirty'))
        if name == 'exec':
            mode.add_argument('-c', '--command', action='append', required=True, help=text('command'))
        elif name == 'run':
            mode.add_argument('--script', required=True, help=text('script'))
            mode.add_argument('--script-format', choices=['auto', 'json', 'lines'], default='auto', help=text('script_format'))
            mode.add_argument('--continue-on-error', action='store_true', help=text('continue_on_error'))
    return result


def envelope(**values):
    return {'schema_version': SCHEMA_VERSION, 'version': __version__, **values}


def failure(code, message, exit_code):
    return envelope(ok=False, code=code, message=str(message), exit_code=exit_code)


def output(value, as_json, language='en'):
    if as_json:
        print(json.dumps(value, ensure_ascii=False))
        return
    if 'commands' in value:
        for command in value['commands']:
            marker = '' if command['cli_supported'] else tr(language, 'ui.cli_gui_only')
            print('/%s %s%s\n  %s' % (command['name'], command['usage'], marker, command['description']))
        return
    for result in value.get('results', []):
        language = result.get('state', {}).get('language', language)
        label = tr(language, 'cli.pending' if result['status'] == 'needs_confirmation' else 'cli.ok' if result['ok'] else 'cli.error')
        print('%s %s' % (label, result['command']))
        if result['state'].get('pending'):
            print(tr(language, 'ui.cli_reply') + ', '.join(result['state']['pending']['choices']))
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
        language = state.get('language', language)
        print('%s %s' % (state['prompt'], state.get('directory') or ''))
        if state.get('pending'):
            print(tr(language, 'ui.cli_confirmation') + ', '.join(state['pending']['choices']))
        document = state.get('document')
        if document and document['dirty'] and 'text' in document:
            print(tr(language, 'ui.cli_draft') + '\n' + document['text'])


def read_script(path, format_name, language='en'):
    if path == '-':
        content = sys.stdin.read(MAX_SCRIPT_BYTES + 1)
        if len(content.encode('utf-8')) > MAX_SCRIPT_BYTES:
            raise UsageError(tr(language, 'cli.workflow_too_large'))
    else:
        with Path(path).open('rb') as stream:
            data = stream.read(MAX_SCRIPT_BYTES + 1)
        if len(data) > MAX_SCRIPT_BYTES:
            raise UsageError(tr(language, 'cli.workflow_too_large'))
        content = data.decode('utf-8-sig')
    content = content.lstrip('\ufeff')
    if format_name == 'auto':
        format_name = 'json' if (path != '-' and Path(path).suffix.lower() == '.json') or content.lstrip().startswith('[') else 'lines'
    if format_name == 'json':
        try:
            values = json.loads(content)
        except json.JSONDecodeError as error:
            raise UsageError(tr(language, 'cli.workflow_invalid_json') % (error.lineno, error.colno)) from error
        if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
            raise UsageError(tr(language, 'cli.workflow_type'))
        return values
    return [line.rstrip('\r') for line in content.splitlines()
            if line.strip() and not line.lstrip().startswith('#')]


def finish(session, results, allow_dirty=False, include_text=False):
    errors = [result for result in results if not result['ok']]
    if errors:
        code, message = errors[0]['code'], errors[0]['message']
        exit_code = 5 if code == 'disk_changed' else 2 if code == 'invalid_arguments' else 3 if code == 'confirmation_required' else 1
    elif session.pending:
        code, message, exit_code = 'confirmation_required', tr(session.language, 'ui.confirm_required'), 3
    elif session.buffer_dirty and not allow_dirty:
        code, message, exit_code = 'unsaved_changes', tr(session.language, 'ui.cli_unsaved'), 4
    else:
        code, message, exit_code = 'ok', '', 0
    return envelope(ok=exit_code == 0, code=code, message=message, exit_code=exit_code,
                    results=results, state=session.snapshot(include_text or session.buffer_dirty), gui_control=False)


def run(args):
    language = getattr(args, 'language', None) or getattr(args, '_cli_language', 'en')
    if args.mode == 'gui':
        from markprompt_core.automation.cli import run as run_gui
        return run_gui(args)
    if args.mode == 'commands':
        output(envelope(ok=True, commands=capabilities(language), gui_control=False), args.json, language)
        return 0
    session = Session(workspace=args.workspace, config_path=args.config)
    if getattr(args, 'language', None):
        setup = session.execute('/lang ' + args.language)
        if not setup['ok']:
            report = finish(session, [setup], args.allow_dirty, args.include_text)
            output(report, args.json)
            return report['exit_code']
    commands = read_script(args.script, args.script_format, session.language) if args.mode == 'run' else args.command if args.mode == 'exec' else None
    try:
        return run_session(args, session, commands)
    except KeyboardInterrupt:
        report = finish(session, [], args.allow_dirty, True)
        report.update(ok=False, code='cancelled', message=tr(session.language, 'ui.cli_interrupted'), exit_code=130)
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
                raise UsageError(tr(session.language, 'cli.command_too_large'))
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
    language = selected_language(argv)
    try:
        return run(parser(language).parse_args(argv))
    except (UsageError, UnicodeError, ValueError) as error:
        output(failure('invalid_arguments', error, 2), '--json' in argv)
        return 2
    except (StorageError, OSError) as error:
        output(failure(getattr(error, 'code', 'io_error'), error, 1), '--json' in argv)
        return 1
    except KeyboardInterrupt:
        output(failure('cancelled', tr(language, 'ui.cli_interrupted'), 130), '--json' in argv)
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
