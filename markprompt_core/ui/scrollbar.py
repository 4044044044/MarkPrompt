"""Draw and operate the terminal-style scrollbar."""
import tkinter as tk
SCROLLBAR_THUMB_MIN = 30


class TerminalScrollbar(tk.Canvas):
    """Draw a theme-aware scrollbar that matches the terminal frame."""

    def __init__(self, parent, theme, command):
        super().__init__(parent, width=20, bg=theme["background"], bd=0, highlightthickness=0,
                         takefocus=0, cursor="arrow")
        self.theme = theme
        self.command = command
        self.first, self.last = 0.0, 1.0
        self.drag_offset = None
        self.hovered = False
        self.bind("<Configure>", lambda _event: self._draw())
        self.bind("<Button-1>", self._click)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", lambda _event: setattr(self, "drag_offset", None))
        self.bind("<Enter>", lambda _event: self._hover(True))
        self.bind("<Leave>", lambda _event: self._hover(False))

    def _hover(self, value):
        self.hovered = value
        self._draw()

    def set_theme(self, theme):
        """Apply the new palette and redraw the scrollbar."""
        self.theme = theme
        self.config(bg=theme["background"])
        self._draw()

    def set(self, first, last):
        self.first, self.last = float(first), float(last)
        self._draw()

    def _geometry(self):
        button, height = 20, max(1, self.winfo_height())
        top, bottom = button, max(button + 1, height - button)
        track = bottom - top
        visible = max(0.0, min(1.0, self.last - self.first))
        thumb = min(track, max(SCROLLBAR_THUMB_MIN, int(track * visible)))
        # At the bottom, Text.yview reports 1 - visible; normalize to the track.
        maximum_first = max(0.0, 1.0 - visible)
        progress = self.first / maximum_first if maximum_first else 0.0
        position = top + int((track - thumb) * max(0.0, min(1.0, progress)))
        return button, top, bottom, thumb, position

    def _draw(self):
        self.delete("all")
        width, height = self.winfo_width(), self.winfo_height()
        if width < 2 or height < 60:
            return
        _button, top, bottom, thumb, position = self._geometry()
        center = width / 2
        color = self.theme["foreground"] if self.hovered else self.theme["muted"]
        self.create_line(center - 4, 12, center, 8, center + 4, 12,
                         fill=color, width=2, capstyle="round", joinstyle="round", tags="arrow-up")
        self.create_line(center - 4, height - 12, center, height - 8, center + 4, height - 12,
                         fill=color, width=2, capstyle="round", joinstyle="round", tags="arrow-down")
        self.create_line(center, top, center, bottom,
                         fill=self.theme["scroll_track"], width=8 if self.hovered else 6)
        if self.last - self.first < 0.999:
            half = 4 if self.hovered else 3
            self.create_rectangle(center - half, position, center + half, position + thumb,
                                  fill=color, outline="")

    def _click(self, event):
        button, _top, bottom, thumb, position = self._geometry()
        if event.y < button:
            self.command("scroll", -1, "units")
        elif event.y > bottom:
            self.command("scroll", 1, "units")
        elif position <= event.y <= position + thumb:
            self.drag_offset = event.y - position
        else:
            self.command("scroll", -1 if event.y < position else 1, "pages")

    def _drag(self, event):
        if self.drag_offset is None:
            return
        _button, top, bottom, thumb, _position = self._geometry()
        progress = (event.y - top - self.drag_offset) / max(1, bottom - top - thumb)
        visible = max(0.0, min(1.0, self.last - self.first))
        fraction = max(0.0, min(1.0, progress)) * (1.0 - visible)
        self.command("moveto", fraction)

