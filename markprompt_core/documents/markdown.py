"""Parse inline Markdown targets for rendering and snapshots."""
import re


def _inline_targets(text, references=None, images=True):
    """Yield image spans with balanced destinations and optional Markdown titles."""
    references = references or {}
    pattern = r"(?<!\\)!\[((?:\\.|[^\]\\])*)\]" if images else r"(?<!!)(?<!\\)\[((?:\\.|[^\]\\])*)\]"
    for match in re.finditer(pattern, text):
        pos = match.end()
        alt = re.sub(r"\\([\[\]\\])", r"\1", match.group(1))
        if pos < len(text) and text[pos] == "(":
            depth, quote, angle, end = 1, None, False, pos + 1
            while end < len(text):
                char = text[end]
                if char == "\\" and end + 1 < len(text) and text[end + 1] in "()<>\\\"'":
                    end += 2
                    continue
                if quote:
                    if char == quote:
                        quote = None
                elif char in "\"'" and end > pos + 1 and text[end - 1].isspace():
                    quote = char
                elif char == "<":
                    angle = True
                elif char == ">":
                    angle = False
                elif not angle and char == "(":
                    depth += 1
                elif not angle and char == ")":
                    depth -= 1
                    if depth == 0:
                        break
                end += 1
            if depth:
                continue
            raw = text[pos + 1:end].strip()
            if raw.startswith("<") and ">" in raw:
                target = raw[1:raw.index(">")]
            else:
                target = re.sub(r"\s+[\"'].*[\"']\s*$", "", raw)
            target = re.sub(r"\\([()<> ])", r"\1", target)
            yield match.start(), end + 1, alt, target
        else:
            end, key = pos, alt
            if pos < len(text) and text[pos] == "[":
                close = text.find("]", pos + 1)
                if close < 0:
                    continue
                key = text[pos + 1:close] or alt
                end = close + 1
            target = references.get(" ".join(key.split()).casefold())
            if target:
                yield match.start(), end, alt, target


def inline_images(text, references=None):
    return _inline_targets(text, references, images=True)


def inline_links(text, references=None):
    return _inline_targets(text, references, images=False)
