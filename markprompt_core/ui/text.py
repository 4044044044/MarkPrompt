"""Use separate fonts for terminal text and CJK glyphs."""
import re
import tkinter as tk
from tkinter import font
CJK_RUN = re.compile(r"[\u2e80-\ua4cf\uac00-\ud7af\uf900-\ufaff\uff00-\uffef]+")
TYPE_SIZES = {"body": 11, "h1": 18, "h2": 13, "h3": 12, "h4": 11, "h5": 11, "h6": 11,
              "bold": 11, "italic": 11}


class RoutedText(tk.Text):
    """Keep the terminal face for Latin text and route CJK glyphs to a regular CJK face."""

    def __init__(self, master, cjk_family, **options):
        super().__init__(master, **options)
        self.cjk_family = cjk_family
        self._cjk_fonts = {}

    def insert(self, index, chars, *args):
        matches = list(CJK_RUN.finditer(chars))
        start = self.index("end-1c" if index == "end" else index) if matches else None
        if matches:
            row = int(start.split(".")[0])
            column = len(self.get("%d.0" % row, "end-1c" if index == "end" else index))
        super().insert(index, chars, *args)
        if not matches:
            return
        tags = args[0] if args else ()
        tags = (tags,) if isinstance(tags, str) else (tags or ())
        style = next((tag for tag in tags if tag in TYPE_SIZES), "body")
        name = "cjk-" + style
        if name not in self._cjk_fonts:
            face = font.Font(root=self, family=self.cjk_family, size=TYPE_SIZES[style],
                             weight="bold" if style.startswith("h") or style == "bold" else "normal",
                             slant="italic" if style == "italic" else "roman")
            self._cjk_fonts[name] = face
            self.tag_configure(name, font=face)
        ranges, previous = [], 0
        for match in matches:
            # Char arithmetic works across Tk 8.6 variants' differing numeric
            # column handling for non-BMP characters; keep each lookup line-local.
            gap = chars[previous:match.start()]
            if "\n" in gap:
                row += gap.count("\n")
                column = len(gap.rsplit("\n", 1)[1])
            else:
                column += len(gap)
            length = len(match.group())
            ranges.extend(("%d.0+%dc" % (row, column), "%d.0+%dc" % (row, column + length)))
            previous, column = match.end(), column + length
        self.tag_add(name, *ranges)
        self.tag_raise(name)

