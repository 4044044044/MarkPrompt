"""Text operations shared by rendering and session inspection."""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Hit:
    line: int
    start: int
    end: int
    text: str


def iter_search_hits(text, term, ignore_case=False):
    if not term or text is None:
        return
    pattern = re.compile(re.escape(term), re.IGNORECASE if ignore_case else 0)
    for number, line in enumerate(text.splitlines(), 1):
        for match in pattern.finditer(line):
            yield Hit(number, match.start(), match.end(), line)


def search_hits(text, term, ignore_case=False):
    return list(iter_search_hits(text, term, ignore_case))


def safe_name(name):
    return re.sub(r'[<>:"/\\|?*]+', '-', name).strip(' .')[:100]


def split_tags(value):
    return [tag.strip() for tag in value.split(',') if tag.strip()]


def tags_in(content):
    match = re.search(r'^<!-- markprompt-tags: (.*?) -->$', content, flags=re.MULTILINE)
    return split_tags(match.group(1)) if match else []


def plain_text(content):
    content = re.sub(r'^<!-- markprompt-tags: .*? -->\n?', '', content, flags=re.MULTILINE)
    content = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', content)
    return re.sub(r'(\*\*|__|`)', '', content)


class ContentMixin:
    _safe_name = staticmethod(safe_name)
    _split_tags = staticmethod(split_tags)
    _tags_in = staticmethod(tags_in)
    _plain_text = staticmethod(plain_text)

    @staticmethod
    def _format_hit_lines(numbers):
        shown = ', '.join(str(number) for number in numbers[:20])
        return shown + (' …(+%d)' % (len(numbers) - 20) if len(numbers) > 20 else '')

    def _hit_lines(self):
        return sorted({hit.line for hit in search_hits(self.buffer_text, self.search_term, self.search_fuzzy)})
