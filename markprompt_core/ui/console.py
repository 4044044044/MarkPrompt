"""Animate command history with a text widget and Tk scheduler."""
HISTORY_TICK_DELAY_MS = 16
HISTORY_LINE_DELAY_MS = 15
HISTORY_COLUMNS_PER_TICK = 12


class HistoryAnimator:
    """Reveal command-history text in scheduled batches."""

    def __init__(self, output, after_callback, history_entries, start_index,
                 tick_delay=HISTORY_TICK_DELAY_MS,
                 line_delay=HISTORY_LINE_DELAY_MS,
                 columns_per_tick=HISTORY_COLUMNS_PER_TICK):
        self.output = output
        self.after_callback = after_callback
        self.pending = iter(history_entries[start_index:])
        self.tick_delay = tick_delay
        self.line_delay = line_delay
        self.columns_per_tick = columns_per_tick
        self.after_id = None
        self.current_text = ""
        self.current_tag = None
        self.offset = 0

    def start(self):
        """Enable output and draw the first batch."""
        self.output.config(state="normal")
        self._draw_next()

    def stop(self):
        """Cancel the next scheduled batch."""
        if self.after_id is not None:
            # Cancel on the widget that registered the Tcl callback, usually root.
            scheduler = getattr(self.after_callback, "__self__", self.output)
            scheduler.after_cancel(self.after_id)
            self.after_id = None

    def _draw_next(self):
        """Draw another batch of characters and schedule any remaining output."""
        delay = self.tick_delay
        for _column in range(self.columns_per_tick):
            while self.offset >= len(self.current_text):
                try:
                    self.current_text, self.current_tag = next(self.pending)
                    self.offset = 0
                except StopIteration:
                    self.after_id = None
                    self.output.config(state="disabled")
                    return
            character = self.current_text[self.offset]
            self.offset += 1
            self.output.insert("end", character, self.current_tag)
            if character == "\n":
                delay = self.line_delay
                break
        self.output.see("end")
        self.after_id = self.after_callback(delay, self._draw_next)

