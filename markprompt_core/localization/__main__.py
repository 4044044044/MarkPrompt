"""Validate installed language resources without starting the GUI."""
import argparse
from . import LANGUAGES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', required=True)
    parser.parse_args()
    baseline = set(LANGUAGES.languages()[0].messages)
    for language in LANGUAGES.languages():
        missing = len(baseline - set(language.messages))
        print('%s: %d messages, %d English fallbacks' % (language.code, len(language.messages), missing))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
