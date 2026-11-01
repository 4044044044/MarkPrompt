"""Render Markdown and map displayed content back to source lines."""
from markprompt_core.localization import tr
import re
import tkinter as tk
from markprompt_core.ui.images import Image, LocalImageStore
from markprompt_core.documents.markdown import inline_images
from markprompt_core.ui.layout import display_width
try:
    from PIL import ImageTk
except ImportError:
    ImageTk = None
MARKDOWN_ANIM_TOTAL_MS = 1100
MARKDOWN_ANIM_TICK_MS = 16
MARKDOWN_ANIM_MAX_LINES_PER_TICK = 80


class MarkdownAnimator:
    """Reveal Markdown in timed batches through the normal line renderer.

    Adjust batch size to the target duration, subject to the per-tick limit.
    """

    def __init__(self, renderer, after_callback, lines, digits, on_complete=None, dirty_lines=None,
                 total_ms=MARKDOWN_ANIM_TOTAL_MS,
                 tick_ms=MARKDOWN_ANIM_TICK_MS,
                 max_lines_per_tick=MARKDOWN_ANIM_MAX_LINES_PER_TICK):
        self.renderer = renderer
        self.output = renderer.output
        self.after_callback = after_callback
        self.lines = lines
        self.digits = digits
        self.on_complete = on_complete
        self.dirty_lines = dirty_lines
        self.tick_ms = tick_ms
        self.index = 0
        self.code = False
        self.after_id = None
        # Spread lines across the target duration, up to the per-tick limit.
        target_ticks = max(1, total_ms // tick_ms)
        per_tick = -(-len(lines) // target_ticks)  # Round up.
        self.lines_per_tick = max(1, min(per_tick, max_lines_per_tick))

    def start(self):
        """Enable output and draw the first batch."""
        self.output.config(state="normal")
        self._draw_next()

    def stop(self):
        """Cancel pending drawing without calling on_complete."""
        if self.after_id is not None:
            scheduler = getattr(self.after_callback, "__self__", self.output)
            scheduler.after_cancel(self.after_id)
            self.after_id = None

    def _draw_next(self):
        """Draw the next lines, then schedule another batch or call on_complete."""
        for _ in range(self.lines_per_tick):
            if self.index >= len(self.lines):
                break
            line = self.lines[self.index]
            self.code = self.renderer._draw_line(self.index + 1, line, self.digits, self.code, self.dirty_lines)
            self.index += 1
        self.output.see("end")
        if self.index >= len(self.lines):
            self.after_id = None
            self.output.config(state="disabled")
            if self.on_complete is not None:
                self.on_complete()
            return
        self.after_id = self.after_callback(self.tick_ms, self._draw_next)


class MarkdownRenderer:
    """Write Markdown and source views into a Tk Text widget."""

    def __init__(self, output, theme, mono):
        self.output = output
        self.theme = theme
        self.mono = mono
        self.image_store = LocalImageStore()
        self.image_refs = []
        self.photo_cache = {}
        self.note_path = None
        self.references = {}
        self.reference_lines = set()
        self.table_rows = {}
        self.table_tags = []
        self.setext = {}
        self.hidden_underlines = set()
        self.document_text = None
        self.line_count = 0
        self.line_marks = {}
        self.source_mode = False
        self.has_images = False
        self.image_width = 640
        self.translate = lambda key: tr("en", "ui." + key)

    def source_index(self, number):
        if number is None or number < 1 or number > self.line_count:
            return None
        if self.source_mode:
            return number
        mark = self.line_marks.get(number)
        if mark is not None:
            return int(self.output.index(mark).split('.')[0])
        return None

    def set_document(self, path, markdown, translate):
        self.note_path = path
        self.translate = translate
        self.document_text = markdown
        self.references = {}
        self.reference_lines = set()
        fence = None
        lines = markdown.splitlines()
        outside = []
        for number, line in enumerate(lines, 1):
            marker = re.match(r"^\s{0,3}(`{3,}|~{3,})(.*)$", line)
            if marker:
                token = marker[1]
                if fence is None:
                    fence = (token[0], len(token))
                elif token[0] == fence[0] and len(token) >= fence[1] and not marker[2].strip():
                    fence = None
                outside.append(False)
                continue
            outside.append(fence is None)
            if fence is not None:
                continue
            match = re.match(r'^\s{0,3}\[([^\]]+)\]:\s*(?:<([^>]+)>|(\S+))', line)
            if match:
                self.references[" ".join(match.group(1).split()).casefold()] = match.group(2) or match.group(3)
                self.reference_lines.add(number)
        measured = self.output.winfo_width()
        self.image_width = max(80, min(1200, measured - self.mono.measure(" [000] ") - 55)) if measured > 1 else 640
        self._prepare_tables(lines, outside)
        self.setext, self.hidden_underlines = {}, set()
        for index in range(1, len(lines)):
            if (outside[index] and outside[index - 1] and lines[index - 1].strip() and
                    index + 1 not in self.table_rows and
                    re.fullmatch(r"\s{0,3}(?:=+|-+)\s*", lines[index])):
                self.setext[index] = 1 if lines[index].lstrip().startswith("=") else 2
                self.hidden_underlines.add(index + 1)

    @staticmethod
    def _table_cells(line):
        line = line.strip()
        if line.startswith("|"):
            line = line[1:]
        if line.endswith("|") and not line.endswith("\\|"):
            line = line[:-1]
        return [cell.strip().replace("\\|", "|") for cell in re.split(r"(?<!\\)\|", line)]

    def _prepare_tables(self, lines, outside):
        if self.table_tags:
            self.output.tag_delete(*self.table_tags)
        self.table_tags, self.table_rows = [], {}
        index = 0
        while index + 1 < len(lines):
            if not (outside[index] and outside[index + 1] and "|" in lines[index]):
                index += 1
                continue
            cells, delimiters = self._table_cells(lines[index]), self._table_cells(lines[index + 1])
            if not (2 <= len(cells) <= 16 and len(cells) == len(delimiters) and
                    all(re.fullmatch(r":?-{3,}:?", cell) for cell in delimiters)):
                index += 1
                continue
            rows, stop = [(index + 1, cells)], index + 2
            while stop < len(lines) and outside[stop] and "|" in lines[stop] and lines[stop].strip():
                rows.append((stop + 1, self._table_cells(lines[stop])))
                stop += 1
            widths = [4] * len(cells)
            for _number, values in rows:
                for column, value in enumerate(values[:len(cells)]):
                    plain = re.sub(r"[*_`~]", "", value)
                    widths[column] = max(widths[column], min(24, display_width(plain)))
            left = self.mono.measure(" [" + "0" * max(3, len(str(len(lines)))) + "]   ")
            cell = max(1, self.mono.measure("0"))
            tabs = []
            for width, delimiter in zip(widths, delimiters):
                size = width * cell + 20
                # Left anchors keep arbitrary long cells out of the line-number gutter.
                alignment = "left"
                anchor = left + (size / 2 if alignment == "center" else size - 10 if alignment == "right" else 0)
                tabs.extend((int(anchor), alignment))
                left += size
            tag = "table-%d" % index
            self.output.tag_configure(tag, tabs=tuple(tabs))
            self.table_tags.append(tag)
            for number, values in rows:
                padded = (values + [""] * len(cells))[:len(cells)]
                self.table_rows[number] = (tag, padded, number == index + 1)
            self.table_rows[index + 2] = (tag, ["─" * width for width in widths], False)
            index = stop

    def _begin_render(self):
        self.image_refs.clear()
        self.photo_cache.clear()
        self.has_images = False
        self.line_marks = {}
        self.source_mode = False
        self.fence_marker = None
        self.code_before = {}
        self.code_after = False
        self.insert_at = "end"
        marks = [mark for mark in self.output.mark_names() if mark.startswith("source-line-")]
        if marks:
            self.output.mark_unset(*marks)

    def _mark_line(self, number):
        name = "source-line-%d" % number
        self.output.mark_set(name, self._position())
        self.output.mark_gravity(name, "left")
        self.line_marks[number] = name

    def _add_image(self, alt, target):
        self.has_images = True
        if not self.note_path:
            self._add("![%s](%s)" % (alt, target))
            return
        try:
            raster = self.image_store.load(target, self.note_path, self.image_width)
            key = raster._markprompt_key
            photo = self.photo_cache.get(key)
            if photo is None:
                photo = ImageTk.PhotoImage(raster, master=self.output)
                self.photo_cache[key] = photo
            self.image_refs.append(photo)
            self.output.image_create(self.insert_at, image=photo, padx=4, pady=10, align="center")
        except (OSError, ValueError, tk.TclError, Image.DecompressionBombError if Image else ValueError):
            remote = re.match(r"^(?:https?://|data:|//|\\\\)", target, re.I)
            key = "image_local_only" if remote else "image_failed"
            self._add(self.translate(key) % (alt or target), "muted")

    def configure_tags(self):
        """Map the current theme and text styles to Tk tags."""
        family = self.mono.actual("family")
        tags = {
            "h1": {"foreground": self.theme["heading"], "font": (family, 18, "bold"), "spacing3": 8},
            "h2": {"foreground": self.theme["heading"], "font": (family, 13, "bold"), "spacing1": 10, "spacing3": 4},
            "h3": {"foreground": self.theme["heading"], "font": (family, 12, "bold"), "spacing1": 8, "spacing3": 3},
            "h4": {"foreground": self.theme["heading"], "font": (family, 11, "bold"), "spacing1": 6},
            "h5": {"foreground": self.theme["heading"], "font": (family, 11, "bold")},
            "h6": {"foreground": self.theme["muted"], "font": (family, 11, "bold")},
            "task": {"foreground": self.theme["foreground"]}, "done": {"foreground": self.theme["muted"]},
            "quote": {"foreground": self.theme["muted"], "lmargin1": 18, "lmargin2": 18},
            "command": {"foreground": self.theme["command"]}, "string": {"foreground": self.theme["string"]},
            "success": {"foreground": self.theme["success"]}, "warning": {"foreground": self.theme["warning"]},
            "error": {"foreground": self.theme["error"]}, "muted": {"foreground": self.theme["muted"]},
            "art": {"foreground": self.theme["command"]},
            "marker": {"foreground": self.theme["muted"]},
            "bold": {"foreground": self.theme["heading"], "font": (family, 11, "bold")},
            "italic": {"foreground": self.theme["foreground"], "font": (family, 11, "italic")},
            "inline-code": {"foreground": self.theme["string"]}, "link": {"foreground": self.theme["command"], "underline": True},
            "strike": {"overstrike": True},
            "unsaved": {"foreground": self.theme["unsaved"]},
            # Use a background for hits so dirty-line text can keep its foreground color.
            "search-hit": {"background": self.theme["search_hit"]},
            # Mark matching notes and folders containing matches in the directory view.
            "find-hit": {"foreground": self.theme["command"]},
        }
        for name, options in tags.items():
            self.output.tag_configure(name, **options)
        # Dirty text takes precedence over heading and emphasis colors.
        self.output.tag_raise("unsaved")
        self.output.tag_raise("sel")

    def _add(self, text, tag=None):
        self.output.insert(self.insert_at, text, tag)

    def _position(self):
        return self.output.index("end-1c" if self.insert_at == "end" else self.insert_at)

    def _add_inline(self, text, base_tag=None):
        # Render inline emphasis, code, and link labels.
        token = re.compile(r"(\*\*.+?\*\*|__.+?__|`[^`]+`|~~.+?~~|\[[^\]]+\]\([^)]*\)|\[[^\]]+\]\[[^\]]*\]|\[[^\]]+\]|\*[^*]+\*)")
        cursor = 0
        images = list(inline_images(text, self.references))
        while cursor < len(text):
            match = token.search(text, cursor)
            picture = next((item for item in images if item[0] >= cursor), None)
            if picture is not None and (match is None or picture[0] <= match.start()):
                self._add(text[cursor:picture[0]], base_tag)
                self._add_image(picture[2], picture[3])
                cursor = picture[1]
                continue
            if match is None:
                break
            self._add(text[cursor:match.start()], base_tag)
            value = match.group(0)
            if value.startswith(("**", "__")):
                self._add_inline(value[2:-2], "bold")
            elif value.startswith("`"):
                self._add(value[1:-1], "inline-code")
            elif value.startswith("~~"):
                self._add_inline(value[2:-2], "strike")
            elif value.startswith("["):
                label = value[1:value.index("]")]
                if "](" in value:
                    self._add(label, "link")
                else:
                    reference = value[value.index("]") + 2:-1] if "][" in value else label
                    reference = " ".join((reference or label).split()).casefold()
                    self._add(label, "link") if reference in self.references else self._add(value, base_tag)
            else:
                self._add_inline(value[1:-1], "italic")
            cursor = match.end()
        self._add(text[cursor:], base_tag)

    def _add_code_line(self, line):
        # Code blocks use lightweight command and string coloring.
        match = re.match(r"(\s*)(\S+)(.*)", line)
        if not match:
            self._add("\n")
            return
        self._add("  " + match.group(1))
        self._add(match.group(2), "command")
        for part in re.split(r'("[^"]*"|\'[^\']*\')', match.group(3)):
            self._add(part, "string" if part.startswith(("\"", "'")) else None)
        self._add("\n")

    def _add_text_line(self, line):
        # ATX headings need a space after the hash marks.
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading:
            level, content = len(heading.group(1)), heading.group(2)
            content = re.sub(r"\s+#+\s*$", "", content)
            self._add("  ")
            self._add_inline(content, "h" + str(level))
            self._add("\n")
            return
        nested = re.match(r"^(\s*)([-+*]|\d+[.)])\s+(?:\[([ xX])\]\s+)?(.+)$", line)
        if nested:
            indent, bullet, checked, text = nested.groups()
            marker = "[x] " if checked and checked.lower() == "x" else "[ ] " if checked else (bullet + " " if bullet[0].isdigit() else "• ")
            self._add("  " + indent.expandtabs(4) + marker, "marker")
            self._add_inline(text, "done" if checked and checked.lower() == "x" else "task" if checked else None)
            self._add("\n")
            return
        rules = (("- [ ] ", "task", 6), ("- [x] ", "done", 6))
        for prefix, tag, start in rules:
            if line.startswith(prefix):
                marker = "[ ] " if prefix == "- [ ] " else "[x] " if prefix == "- [x] " else ""
                self._add("  " + marker, "marker")
                self._add_inline(line[start:], tag)
                self._add("\n")
                return
        if line.startswith(("- ", "* ")):
            self._add("  • ", "marker")
            self._add_inline(line[2:])
        elif re.match(r"^\d+\.\s", line):
            number, item = re.split(r"\.\s+", line, maxsplit=1)
            self._add("  " + number + ". ", "marker")
            self._add_inline(item)
        elif line.startswith("> "):
            self._add("  │ ", "command")
            self._add_inline(line[2:], "quote")
        elif line == "---":
            self._add("  ═══════════════════════════════════════", "muted")
        elif line.startswith(("[OK]", "[!]", "[ERR]")):
            mark, tag, rest = ("[OK]", "success", line[4:]) if line.startswith("[OK]") else ("[!]", "warning", line[3:]) if line.startswith("[!]") else ("[ERR]", "error", line[5:])
            self._add("  " + mark, tag)
            self._add_inline(rest)
        elif line:
            self._add("  ")
            self._add_inline(line)
        self._add("\n")

    def _draw_line(self, number, line, digits, code, dirty_lines=None):
        self.code_before[number] = code
        if not code and (line.startswith("<!-- markprompt-tags:") or number in self.reference_lines or number in self.hidden_underlines):
            return code
        self._mark_line(number)
        # One hanging indent keeps wrapped text out of the line-number gutter.
        # Tk Text inserts before its permanent final newline. "end" would
        # start the tag on the following paragraph, leaving wrapped text bare.
        start = self._position()
        # Apply indentation at insertion time; some Tk builds ignore it when added later.
        self._add(" [%0*d] " % (digits, number), ("numbered-line", "marker"))
        fence = re.match(r"^\s{0,3}(`{3,}|~{3,})(.*)$", line)
        closes = (fence is not None and code and self.fence_marker is not None and
                  fence[1][0] == self.fence_marker[0] and len(fence[1]) >= self.fence_marker[1] and not fence[2].strip())
        if fence and (not code or closes):
            label = fence[2].strip() or "text"
            self._add("  ┌─ " + label + "\n" if not code else "  └───────────────────────────────────────\n", "marker")
            self.fence_marker = None if code else (fence[1][0], len(fence[1]))
            code = not code
        elif code:
            self._add_code_line(line)
        elif number in self.table_rows:
            tag, cells, heading = self.table_rows[number]
            for cell in cells:
                self._add("\t")
                self._add_inline(cell, "bold" if heading else None)
            self._add("\n")
            self.output.tag_add(tag, start, "end-1c")
        elif number in self.setext:
            self._add("  ")
            self._add_inline(line.strip(), "h%d" % self.setext[number])
            self._add("\n")
        else:
            self._add_text_line(line)
        self.output.tag_add("numbered-line", start, self._position())
        # Apply dirty-line color after the normal formatting tags.
        if dirty_lines and number in dirty_lines:
            self.output.tag_add("unsaved", start, self._position())
        self.code_after = code
        return code

    def render(self, markdown, dirty_lines=None):
        """Render all Markdown lines immediately."""
        if self.document_text != markdown:
            self.set_document(self.note_path, markdown, self.translate)
        self._begin_render()
        lines = list(enumerate(markdown.splitlines(), start=1))
        self.line_count = len(lines)
        digits = max(3, len(str(len(lines))))
        # Include the number and following spaces in the continuation indent.
        indent = self.mono.measure(" [" + "0" * digits + "]   ")
        self.output.tag_configure("numbered-line", lmargin1=0, lmargin2=indent)
        self.output.config(state="normal")
        code = False
        for number, line in lines:
            code = self._draw_line(number, line, digits, code, dirty_lines)
        self.output.config(state="disabled")

    def render_source(self, markdown, dirty_lines=None):
        """Render literal source with line numbers and dirty-line colors.

        Keep Markdown punctuation visible so search offsets match the editing copy.
        """
        self._begin_render()
        lines = list(enumerate(markdown.splitlines(), start=1))
        self.line_count = len(lines)
        self.source_mode = True
        digits = max(3, len(str(len(lines))))
        indent = self.mono.measure(" [" + "0" * digits + "]   ")
        self.output.tag_configure("numbered-line", lmargin1=0, lmargin2=indent)
        self.output.config(state="normal")
        start_row = int(self.output.index("end-1c").split(".")[0])
        self._add("".join(" [%0*d] %s\n" % (digits, number, line) for number, line in lines))
        self.output.tag_add("numbered-line", "%d.0" % start_row, "end-1c")
        markers, dirty = [], []
        for number, _line in lines:
            row = start_row + number - 1
            markers.extend(("%d.0" % row, "%d.%d" % (row, digits + 4)))
            if dirty_lines and number in dirty_lines:
                dirty.extend(("%d.0" % row, "%d.end" % row))
        if markers:
            self.output.tag_add("marker", *markers)
        if dirty:
            self.output.tag_add("unsaved", *dirty)
        self.output.config(state="disabled")

    def render_animated(self, markdown, after_callback, on_complete=None, dirty_lines=None):
        """Render Markdown in timed batches using the same formatting as render().

        Call on_complete once after natural completion; cancellation leaves it uncalled.
        """
        if self.document_text != markdown:
            self.set_document(self.note_path, markdown, self.translate)
        self._begin_render()
        lines = markdown.splitlines()
        self.line_count = len(lines)
        if not lines:
            self.output.config(state="disabled")
            if on_complete is not None:
                on_complete()
            return None

        digits = max(3, len(str(len(lines))))
        indent = self.mono.measure(" [" + "0" * digits + "]   ")
        self.output.tag_configure("numbered-line", lmargin1=0, lmargin2=indent)
        self.output.config(state="normal")

        animator = MarkdownAnimator(self, after_callback, lines, digits, on_complete, dirty_lines)
        animator.start()
        return animator

