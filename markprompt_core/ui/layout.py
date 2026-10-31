"""Measure terminal text in display cells."""
import unicodedata

def display_width(text):
    """Measure display cells, counting full-width characters as two cells."""
    width = 0
    for char in text:
        if unicodedata.combining(char):
            continue
        width += 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
    return width


def fit_display(text, width):
    if display_width(text) <= width:
        return text + " " * (width - display_width(text))
    kept = ""
    for char in text:
        if display_width(kept + char + "…") > width:
            break
        kept += char
    return kept + "…" + " " * max(0, width - display_width(kept + "…"))

