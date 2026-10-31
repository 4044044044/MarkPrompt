"""Open files and URLs with the desktop default application."""
import os
import sys
import subprocess

def system_open(target):
    """Open a file or URL with the desktop association, without invoking a shell."""
    if os.name == "nt":
        os.startfile(str(target))
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(target)],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
