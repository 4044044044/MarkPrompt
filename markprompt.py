"""MarkPrompt window, keyboard input, and native UI adapters."""

from pathlib import Path
from markprompt_core.ui.text import RoutedText, TYPE_SIZES
from markprompt_core.ui import images as image_model
LocalImageStore = image_model.LocalImageStore
Image = image_model.Image
ImageOps = image_model.ImageOps
from markprompt_core.ui.reader import MarkdownRenderer
from markprompt_core.ui import reader as reader_ui
MarkdownAnimator = reader_ui.MarkdownAnimator
ImageTk = reader_ui.ImageTk
from markprompt_core.ui.console import HistoryAnimator
from markprompt_core.ui.scrollbar import TerminalScrollbar
from markprompt_core.ui.layout import display_width, fit_display
from markprompt_core.documents import buffer as buffer_model
from markprompt_core.documents.session import DocumentAdapter, DocumentSession
from markprompt_core.search.session import SearchAdapter, SearchSession
from markprompt_core.documents.content import ContentMixin, search_hits
from markprompt_core.search import index as search_engine
WorkspaceSearch = search_engine.WorkspaceSearch
from markprompt_core.documents import markdown as markdown_syntax
inline_images = markdown_syntax.inline_images
from markprompt_core.ui.snapshot import SnapshotSurface

BufferModel = buffer_model.BufferModel
from markprompt_core.storage import local as disk_storage
from markprompt_core.storage.local import StorageServices, StorageError
from markprompt_core.ui.storage_adapter import StorageMixin

# Keep these public aliases pointing at the shared storage helpers.
atomic_write_text = disk_storage.atomic_write_text
decode_dropped_text = disk_storage.decode_text
from markprompt_core.application.states import BusinessStates
from markprompt_core.application.navigation import NavigationMemory
from markprompt_core.commands.catalog import REGISTRY
from markprompt_core.commands.routing import CommandRouter
from markprompt_core.commands.arguments import split_chain
from markprompt_core.application.workflows import WorkflowMixin, PROMPTS
from markprompt_core.commands.presentation import bind_presentation
from markprompt_core.automation.controller import GuiControl
from uuid import uuid4
from markprompt_core.commands.actions import CommandActions
from markprompt_core.ui.resources import THEMES, DEFAULT_THEME_NAME

DEFAULT_THEME = THEMES['dark']
LIGHT_THEME = THEMES['light']

from markprompt_core.localization import LANGUAGES, tr

ROUTER = CommandRouter(REGISTRY)

import os
import re
import sys
import tkinter as tk
from tkinter import font
from collections import OrderedDict

_DND_IMPORT_ERROR = ""
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
except ImportError as error:
    TkinterDnD = None
    DND_FILES = "DND_Files"
    _DND_IMPORT_ERROR = str(error)

# Tk roots need the DnD mixin; BaseWidget extensions do not reach them.
_DnDMethods = TkinterDnD.DnDWrapper if TkinterDnD is not None else object

# Give the window its own taskbar icon before Tk creates it.
if os.name == "nt":
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MarkPrompt.LocalMarkdown.1")

APP_DIR = Path(__file__).resolve().parent
ICON_FILE = APP_DIR / "MarkPrompt.ico"
DROP_ICON_FILE = APP_DIR / "MarkPrompt.png"
TEXT_FILE_SUFFIXES = frozenset({".md", ".txt"})


# Locate preferences before loading the workspace they point to.
CONFIG_FILENAME = "markprompt.json"
CONFIG_VERSION = 1


def _app_base_dir() -> Path:
    """Use the executable directory for frozen builds; __file__ points at unpacked data."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return APP_DIR


def default_config_path() -> Path:
    return disk_storage.configuration_path(_app_base_dir(), CONFIG_FILENAME)


MAX_RECENT_FILES = 12
MAX_AUTOCOMPLETE_VISIBLE = 10
# Grow for explicit newlines; scroll after this limit.
MAX_ENTRY_LINES = 6
CURSOR_BLINK_ON_MS = 500
CURSOR_WIDTH_PX = 18
AUTOCOMPLETE_ITEM_HEIGHT_PX = 30
AUTOCOMPLETE_COUNT_LABEL_HEIGHT_PX = 20
CONSOLE_MAX_WIDTH_CHARS = 72
CONSOLE_NARROW_THRESHOLD_PX = 250
CONSOLE_MIN_WIDTH_CHARS = 36
TREE_MAX_CHILDREN = 12
HISTORY_TICK_DELAY_MS = 16
HISTORY_LINE_DELAY_MS = 15
HISTORY_COLUMNS_PER_TICK = 12


# Keep animation timing roughly constant as documents grow.
MARKDOWN_ANIM_TOTAL_MS = 1100
MARKDOWN_ANIM_TICK_MS = 16
MARKDOWN_ANIM_MAX_LINES_PER_TICK = 80

# Layout spacing.
UI_FRAME_PADX = 10
UI_FRAME_PADY = 10
UI_PROMPT_PADX = (0, 10)
UI_SEND_BUTTON_PADX = (12, 0)
UI_SEND_BUTTON_PADY = 5
UI_SEND_BUTTON_PAD = 12
UI_BODY_PADX = 12
UI_BODY_PADY = 10
UI_OUTPUT_PADX = 12
UI_OUTPUT_PADY = 8
UI_AC_ITEM_PADX = 12
UI_AC_ITEM_PADY = 4
UI_AC_CMD_DESC_PADX = (12, 8)

# Font sizes
FONT_SIZE_SMALL = 9
FONT_SIZE_NORMAL = 10
FONT_SIZE_BOLD = 11
FONT_SIZE_H2 = 13
FONT_SIZE_H3 = 12

# Scrollbar constants
SCROLLBAR_THUMB_MIN = 30

# Place navigation targets about a third of the way down the viewport.
# Tk clamps the position near the start and end of the document.
VIEW_TARGET_FRACTION = 0.33

# A:\> meets UTF-8. Keep the wordmark in a fixed-width font.
MARKPROMPT_ART = (
    "┌│┐┌─┐  ┌│───┐  ┌│───┐   │  │  ┌│───┐  ┌│───┐  ┌│───┐  ┌│┐┌─┐  ┌│───┐  ┌─│─┐",
    " ││││    │  │    │  │    │ ┌┘   │  │    │  │    │  │    ││││    │  │     │",
    " │└┘│   ┌───│┐  ┌────┐  ┌│─│┐  ┌───│┐  ┌────┐   │  │    │└┘│   ┌───│┐    │",
    " │  │    │  │    │  ┐    │ └┐   │       │  ┐    │  │    │  │    │        │",
    " │  │    │  │    │  │    │  │   │       │  │   └───│┘   │  │    │        │",
)


class MarkPromptApp(SnapshotSurface, SearchAdapter, DocumentAdapter, ContentMixin, StorageMixin, WorkflowMixin, CommandActions, tk.Tk, _DnDMethods):
    """Connect application sessions to the Tk window."""

    def _present_clear(self):
        self._stop_history_animation()
        # Clear command feedback without closing the preview.
        if self.view_mode == "read" and self.current_file:
            self.console_history = self.console_history[:self.preview_history_start]
            self._show_markdown(self.current_file)
            return
        self.console_history = []
        self._transition_view_mode("console")
        self._set_header("MARKPROMPT.EXE  ·  " + self._t("command"))
        self._clear_output()
        self.output.config(state="disabled")


    def _present_prompt(self):
        top = self.states.top
        text, color = PROMPTS[top.kind] if top else ('MARK>', 'heading')
        self.prompt_label.config(text=text, fg=self.theme[color])
        self._refresh_header_mode()

    def _transition_view_mode(self, new_mode):
        """Apply the cleanup needed when the displayed view changes."""
        valid_modes = {"console", "read", "source"}
        if new_mode not in valid_modes:
            raise ValueError(f"无效的视图模式: {new_mode}")

        old_mode = self.view_mode
        if old_mode == new_mode:
            return

        self.view_mode = new_mode

        if new_mode == "console":
            self._stop_history_animation()
        elif new_mode == "source":
            # Cancel pending output before switching to source view.
            self._stop_history_animation()
        elif new_mode == "read":
            pass

    def __init__(self, storage=None, enable_bridge=True, bridge_directory=None):
        super().__init__()
        self.storage = storage if storage is not None else StorageServices()
        self.control = None
        self.closed = False
        self.document = DocumentSession(self.storage.documents)
        self.search = SearchSession(self.storage.documents)
        self.presentation = bind_presentation(self, gui=True)
        # Build widgets with the saved palette so the first frame uses the right colors.
        self.config_path = default_config_path()
        startup = self._load_config()
        self.theme_name = startup.get("theme")
        self.animations = startup.get("animations", False) is True
        if self.theme_name not in THEMES:
            self.theme_name = DEFAULT_THEME_NAME
        self.theme = THEMES[self.theme_name].copy()
        self.title("MarkPrompt")
        if ICON_FILE.is_file():
            try:
                self.iconbitmap(default=str(ICON_FILE))
            except tk.TclError:
                pass  # ICO is not supported by every Tk platform.
        if DROP_ICON_FILE.is_file():
            self._app_icon = tk.PhotoImage(master=self, file=str(DROP_ICON_FILE))
            self.iconphoto(True, self._app_icon)
        self.geometry("900x620")
        self.minsize(620, 420)
        self.configure(bg=self.theme["background"])
        self.mono = font.Font(root=self, family="Cascadia Mono", size=11)
        available = set(font.families(self))
        self.cjk_family = next((name for name in (
            "Sarasa Mono SC", "Noto Sans Mono CJK SC", "Microsoft YaHei UI", "PingFang SC",
            "Noto Sans CJK SC", "WenQuanYi Micro Hei") if name in available),
            font.nametofont("TkDefaultFont").actual("family"))
        self.ui_font = font.Font(root=self, family=self.cjk_family, size=TYPE_SIZES["body"], weight="normal")
        # Restore only an explicitly chosen workspace.
        self.language = LANGUAGES.normalize(startup.get("language"))
        self._restored = False
        self._stale_workspace = None
        self.workspace = None
        self.current_dir = None
        self.current_file = None
        self.listed_items = {}
        self.recent_files = []
        # Keep console history separate so /back can restore it.
        self.view_mode = "console"
        self.console_history = []
        # Only commands issued after opening this note belong in its preview.
        self.preview_history_start = 0
        self.states = BusinessStates()
        self.navigation = NavigationMemory()
        # Sessions own document and search data; this window owns widgets and Tk callbacks.
        self._navigation_bypass = False
        self._navigation_tail = []
        self._last_disk_read = None
        self._buffer_disk_version = None
        self._rendered_text = None
        self._rendered_path = None
        self._rendered_view = None
        self._rendered_lines = []
        self._reading_positions = OrderedDict()
        self._last_position_line = 0
        self._find_after = None
        # A new command may interrupt the current reply.
        self.history_after_id = None
        # Keep the scroll target through feedback-driven redraws.
        self._scroll_target = None
        self.history_animator = None
        self.markdown_animator = None

        # Keep frame widgets available for theme changes.
        self.outer = tk.Frame(self, bg=self.theme["border"], padx=2, pady=2)
        self.outer.pack(fill="both", expand=True, padx=UI_FRAME_PADX, pady=UI_FRAME_PADY)
        self.middle = tk.Frame(self.outer, bg=self.theme["background"], padx=2, pady=2)
        self.middle.pack(fill="both", expand=True)
        self.app = tk.Frame(self.middle, bg=self.theme["background"])
        self.app.pack(fill="both", expand=True)
        app = self.app

        self.header = tk.Label(
            app, text=" MARKPROMPT.EXE  ·  LOCAL MARKDOWN", anchor="w",
            bg=self.theme["panel"], fg=self.theme["foreground"], font=self.ui_font,
            padx=14, pady=9,
        )
        self.header.pack(fill="x")

        self.composer = tk.Frame(app, bg=self.theme["panel"], padx=14, pady=11)
        self.composer.pack(fill="x", side="bottom")
        self.prompt_label = tk.Label(self.composer, text="MARK>", bg=self.theme["panel"], fg=self.theme["heading"], font=self.mono)
        # Align the prompt with the first input line.
        self.prompt_label.pack(side="left", padx=UI_PROMPT_PADX, anchor="n")
        # Start at one line; explicit newlines grow the input.
        self.entry = RoutedText(
            self.composer, cjk_family=self.cjk_family, height=1, bg=self.theme["panel"], fg=self.theme["foreground"],
            selectbackground=self.theme["selection_background"], selectforeground=self.theme["selection_foreground"],
            inactiveselectbackground=self.theme["selection_background"], selectborderwidth=0,
            insertbackground=self.theme["foreground"], relief="flat", font=self.mono,
            insertwidth=18, insertontime=500, insertofftime=500,
            wrap="word", padx=0, pady=0,
        )
        self.entry.pack(side="left", fill="x", expand=True)
        self.send = tk.Button(
            self.composer, text="[ SEND ]", command=self._placeholder_send,
            bg=self.theme["panel"], fg=self.theme["foreground"], activebackground=self.theme["muted"],
            activeforeground=self.theme["background"], relief="solid", borderwidth=2, highlightthickness=0,
            padx=UI_SEND_BUTTON_PAD, pady=UI_SEND_BUTTON_PADY, font=self.ui_font,
        )
        self.send.pack(side="right", padx=UI_SEND_BUTTON_PADX)
        self.entry.bind("<Return>", self._placeholder_send)

        # Completion opens above the input and follows the active theme.
        self.ac_frame = tk.Frame(app, bg=self.theme["ac_bg"], highlightbackground=self.theme["ac_border"],
                                  highlightthickness=1, highlightcolor=self.theme["ac_border"])
        self.ac_count_label = tk.Label(self.ac_frame, text="", bg=self.theme["ac_count_bg"], fg=self.theme["ac_count_fg"],
                                        font=(self.cjk_family, FONT_SIZE_SMALL), anchor="w", padx=UI_AC_ITEM_PADX, pady=2)
        self.ac_count_label.pack(fill="x")
        self.ac_canvas = tk.Canvas(self.ac_frame, bg=self.theme["ac_bg"], highlightthickness=0, height=0)
        self.ac_canvas.pack(fill="x")
        self.ac_inner = tk.Frame(self.ac_canvas, bg=self.theme["ac_bg"])
        self.ac_canvas_window = self.ac_canvas.create_window(0, 0, window=self.ac_inner, anchor="nw")
        self.ac_inner.bind("<Configure>", lambda _e: self.ac_canvas.config(scrollregion=self.ac_canvas.bbox("all")))
        self.ac_canvas.bind("<Configure>", self._ac_resize)
        self.ac_item_widgets = []
        self.ac_filtered = []
        self.ac_active_index = 0
        self.ac_visible = False
        self.ac_scroll_offset = 0
        self.ac_mode = "command"
        self.ac_cmd = ""
        self.ac_keywords = {}

        self.entry.bind("<Tab>", self._ac_tab)
        self.entry.bind("<KeyRelease>", self._ac_on_key)
        self.entry.bind("<KeyPress-Up>", self._ac_up)
        self.entry.bind("<KeyPress-Down>", self._ac_down)
        self.entry.bind("<KeyPress-Escape>", self._ac_escape)
        # Keep completion bindings when adding input resizing.
        # Measure pasted text after Tk's paste handler has run.
        self.entry.bind("<KeyRelease>", self._autosize_entry, add="+")
        self.entry.bind("<<Paste>>", lambda _e: self.after_idle(self._autosize_entry), add="+")

        # Use this window's bindtag; bind_all would leak shortcuts to other windows.
        self.bind("<Control-s>", self._shortcut_save)
        self.bind("<Control-z>", self._shortcut_undo)
        self.bind("<Control-y>", self._shortcut_redo)
        self.bind("<Control-f>", lambda _event: self._focus_command("/search "))
        self.bind("<Control-p>", lambda _event: self._focus_command("/files "))
        self.bind("<Control-o>", lambda _event: self._run_command_as_shortcut("/outline"))
        self.bind("<F3>", lambda _event: self._run_command_as_shortcut('/next'))
        self.bind("<Shift-F3>", lambda _event: self._run_command_as_shortcut('/prev'))
        self._entry_shortcut_draft = None

        self.body_frame = tk.Frame(app, bg=self.theme["background"])
        self.body_frame.pack(fill="both", expand=True, padx=UI_BODY_PADX, pady=UI_BODY_PADY)
        self.scrollbar = TerminalScrollbar(self.body_frame, self.theme, command=lambda *args: self.output.yview(*args))
        self.scrollbar.pack(side="right", fill="y")
        self.output = RoutedText(
            self.body_frame, cjk_family=self.cjk_family, bg=self.theme["background"], fg=self.theme["foreground"],
            selectbackground=self.theme["selection_background"], selectforeground=self.theme["selection_foreground"],
            inactiveselectbackground=self.theme["selection_background"], selectborderwidth=0,
            insertbackground=self.theme["foreground"], relief="flat", borderwidth=0,
            font=self.mono, wrap="word", padx=UI_OUTPUT_PADX, pady=UI_OUTPUT_PADY,
            yscrollcommand=self.scrollbar.set, state="disabled",
        )
        self.output.pack(side="left", fill="both", expand=True)
        self.renderer = MarkdownRenderer(self.output, self.theme, self.mono)
        self.renderer.configure_tags()
        self._restore_persisted_workspace()
        self._show_welcome(reset=True)
        self._announce_restored_workspace()
        self._check_recovery()                # Offer recovery for drafts left by a previous run.
        self.entry.focus_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._init_file_drop()
        self._image_resize_after = None
        self.output.bind("<Configure>", self._on_read_area_resize, add="+")
        self._key_tag = "MarkPromptKeys_%s" % id(self)
        self.bind_class(self._key_tag, "<KeyPress>", self._on_window_key)
        def register_keys(widget):
            widget.bindtags((self._key_tag,) + widget.bindtags())
            for child in widget.winfo_children():
                register_keys(child)
        register_keys(self)
        if enable_bridge:
            self.control = GuiControl(self, bridge_directory, source=Path(__file__).resolve())
            if not self.control.start():
                self._append_notice('[!] GUI connection unavailable: ' + self.control.error, 'warning')

    def _on_window_key(self, event):
        if event.keysym == "Escape" and self._entry_shortcut_draft is not None:
            self._restore_command_draft()
            self._ac_hide()
            return "break"
        if event.keysym == "Escape" and self._find_future is not None and not self.ac_visible:
            self._cancel_find()
            self._append_notice("[!] " + self._t("find_cancelled"), "warning")
            return "break"
        if self.grab_current() is not None or self._drop_open_pending:
            return None
        if event.keysym == "Escape" and self._drop_overlay is not None and self._drop_overlay.winfo_ismapped():
            self._hide_drop_feedback()
            return "break"
        if event.state & (0x4 | 0x8 | 0x20000):
            return None
        if event.char == "/" and event.widget is not self.entry:
            self.entry.focus_set()
            self.entry.insert("insert", "/")
            self._ac_on_key()
            return "break"
        if event.keysym not in ("Up", "Down") or self.ac_visible or self.confirm_mode:
            return None
        if self.entry.get("1.0", "end-1c") or self.entry.tag_ranges("sel") or self.output.tag_ranges("sel"):
            return None
        self.output.yview_scroll(-1 if event.keysym == "Up" else 1, "units")
        return "break"

    def destroy(self):
        control = self.__dict__.get('control')
        if control is not None:
            control.close()
        self.closed = True
        self._cancel_find()
        self.search.close()
        # Cancel delayed callbacks before their widgets are destroyed.
        for name in ("_image_resize_after", "_drop_leave_after"):
            pending = getattr(self, name, None)
            if pending is not None:
                try:
                    self.after_cancel(pending)
                except tk.TclError:
                    pass
                setattr(self, name, None)
        super().destroy()

    def _on_read_area_resize(self, _event=None):
        if self._image_resize_after is not None:
            self.after_cancel(self._image_resize_after)
        self._image_resize_after = self.after(180, self._resize_images)

    def _resize_images(self):
        self._image_resize_after = None
        if self.view_mode != "read" or not self.current_file or not self.renderer.has_images:
            return
        width = max(80, min(1200, self.output.winfo_width() - self.mono.measure(" [000] ") - 55))
        if abs(width - self.renderer.image_width) < 8:
            return
        if self.markdown_animator and self.markdown_animator.after_id is not None:
            self._image_resize_after = self.after(180, self._resize_images)
        else:
            self._show_markdown(self.current_file)

    # Native file drops.
    def _confirm_navigation(self, action, target=None, defer=False):
        """Ask about unsaved changes before commands, navigation, or drops leave a note."""
        if (not self.buffer_dirty or self._navigation_bypass or
                (target is not None and Path(target) == self.buffer_path)):
            return True
        if getattr(self, "_drop_open_pending", False):
            return False
        self._drop_open_pending = True
        previous = self.buffer_path
        recovery = self._recovery_file()

        def resume():
            self._navigation_bypass = True
            try:
                action()
            finally:
                self._navigation_bypass = False
            if self.current_file is None and self.buffer_path == previous:
                self.document.close(discard=True)
            if self.buffer_path != previous or not self.buffer_dirty:
                if recovery is not None:
                    try:
                        self.storage.json.delete(recovery)
                    except StorageError:
                        pass
            self._recovery_sync()
            tail, self._navigation_tail = self._navigation_tail, []
            for segment in tail:
                self._dispatch(segment)

        if defer:
            self.after_idle(lambda: self._show_exit_dialog(on_continue=resume))
        else:
            self._show_exit_dialog(on_continue=resume)
        return False

    def _init_file_drop(self):
        self._drop_overlay = None
        self._drop_leave_after = None
        self._drop_open_pending = False
        self._drop_targets = set()
        self._drop_error = _DND_IMPORT_ERROR
        self._drop_version = None
        self.drop_enabled = False
        if TkinterDnD is not None:
            try:
                self._drop_version = TkinterDnD.require(self)
                self._register_file_drop(self)
                self.drop_enabled = True
            except (RuntimeError, tk.TclError) as error:
                self._drop_error = str(error)
        if not self.drop_enabled:
            detail = " (%s; Python: %s)" % (self._drop_error, sys.executable)
            self._append_notice("[!] " + self._t("drop_unavailable") + detail, "warning")

    def _register_file_drop(self, widget):
        if str(widget) in self._drop_targets:
            return
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<DropEnter>>", self._on_drop_position)
        widget.dnd_bind("<<DropPosition>>", self._on_drop_position)
        widget.dnd_bind("<<DropLeave>>", self._on_drop_leave)
        widget.dnd_bind("<<Drop>>", self._on_file_drop)
        self._drop_targets.add(str(widget))
        # Register child widgets too, including the drop badge's canvas.
        # Separate dialogs keep their own drop behavior.
        for child in widget.winfo_children():
            if not isinstance(child, tk.Toplevel):
                self._register_file_drop(child)

    def _drop_paths(self, data):
        # Tcl list quoting handles spaces, braces, backslashes and Unicode paths.
        try:
            return tuple(Path(value) for value in self.tk.splitlist(data))
        except (tk.TclError, TypeError, ValueError):
            return ()

    def _drop_state(self, paths):
        if self.confirm_mode or self._drop_open_pending or self.grab_current() is not None:
            return "drop_busy"
        if len(paths) != 1:
            return "drop_single" if paths else "drop_hint"
        try:
            if paths[0].is_dir():
                return "drop_folder"
        except OSError:
            pass
        suffix = paths[0].suffix.lower()
        return {".md": "drop_md", ".txt": "drop_txt"}.get(suffix, "drop_unknown")

    def _on_drop_position(self, event):
        if self._drop_leave_after is not None:
            self.after_cancel(self._drop_leave_after)
            self._drop_leave_after = None
        paths = self._drop_paths(event.data)
        self._drop_hover_name = paths[0].name if len(paths) == 1 else ""
        state = self._drop_state(paths)
        self._show_drop_feedback(state)
        return "copy" if state in ("drop_md", "drop_txt", "drop_folder", "drop_hint") else "refuse_drop"

    def _show_drop_feedback(self, state):
        ink = self.winfo_rgb(self.theme["foreground"])
        ground = self.winfo_rgb(self.theme["background"])
        dim = "#" + "".join("%02x" % int((back + (front - back) * 0.22) / 257)
                             for front, back in zip(ink, ground))
        self.output.tag_configure("drop-dim", foreground=dim)
        self.output.tag_add("drop-dim", "1.0", "end")
        self.output.tag_raise("drop-dim")
        if self._drop_overlay is None:
            top = tk.Toplevel(self)
            top.withdraw()
            top.overrideredirect(True)
            top.transient(self)
            top.attributes("-alpha", 0.98)
            top.configure(padx=20, pady=16, highlightthickness=2)
            row = tk.Frame(top)
            row.pack(fill="x")
            self._drop_row = row
            self._drop_symbol = tk.Canvas(row, width=32, height=34, highlightthickness=0)
            self._drop_symbol.pack(side="left", padx=(0, 12))
            text = tk.Frame(row)
            text.pack(side="left", fill="x", expand=True)
            self._drop_text_frame = text
            self._drop_caption = tk.Label(text, font=(self.cjk_family, 13, "normal"), anchor="w")
            self._drop_caption.pack(anchor="w")
            self._drop_overlay = top
            self._register_file_drop(top)
        top = self._drop_overlay
        bg = self.theme["drop_panel"]
        top.configure(bg=bg, highlightbackground=self.theme["drop_edge"],
                      highlightcolor=self.theme["drop_edge"])
        for widget in (self._drop_row, self._drop_text_frame, self._drop_symbol):
            widget.configure(bg=bg)
        title = state.replace("drop_", "badge_", 1)
        caption_color = self.theme["drop_unknown_color"] if state == "drop_unknown" else self.theme["heading"]
        self._drop_caption.configure(text=self._t(title), bg=bg, fg=caption_color)
        self._drop_symbol.delete("all")
        color = {
            "drop_unknown": self.theme["drop_unknown_color"],
            "drop_folder": self.theme["warning"],
            "drop_txt": self.theme["heading"],
        }.get(state, self.theme["command"])
        if state == "drop_folder":
            self._drop_symbol.create_polygon(2, 9, 12, 9, 15, 13, 30, 13, 30, 29, 2, 29,
                                             fill="", outline=color, width=2.5)
        else:
            self._drop_symbol.create_polygon(5, 2, 20, 2, 28, 10, 28, 31, 5, 31,
                                             fill="", outline=color, width=2.5)
            self._drop_symbol.create_line(20, 2, 20, 10, 28, 10, fill=color, width=2.5)
            if state == "drop_txt":
                for y, end in ((17, 22), (22, 22), (27, 18)):
                    self._drop_symbol.create_line(10, y, end, y, fill=color, width=2.5)
            elif state == "drop_md":
                self._drop_symbol.create_line(10, 26, 10, 18, 15, 23, 20, 18, 20, 26,
                                              fill=color, width=2.5)
            else:
                self._drop_symbol.create_line(11, 24, 22, 14, fill=color, width=2.5)
        top.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - top.winfo_reqwidth()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - top.winfo_reqheight()) // 2
        top.geometry("+%d+%d" % (x, y))
        top.deiconify()
        top.lift()
        # In-process OLE drags may defer Tk expose events until release.
        # Paint the badge without starting a nested event loop.
        top.update_idletasks()

    def _on_drop_leave(self, _event=None):
        if self._drop_leave_after is not None:
            self.after_cancel(self._drop_leave_after)
        # Crossing onto our own badge emits leave then enter; defer hiding to avoid flicker.
        self._drop_leave_after = self.after(80, self._hide_drop_feedback)
        return "copy"

    def _hide_drop_feedback(self):
        self.output.tag_remove("drop-dim", "1.0", "end")
        if self._drop_leave_after is not None:
            self.after_cancel(self._drop_leave_after)
            self._drop_leave_after = None
        if self._drop_overlay is not None:
            self._drop_overlay.withdraw()

    def _drop_notice(self, key, detail=""):
        message = "[!] " + self._t(key) + detail
        self.presentation.notice(message, "warning", code=key)
        if self.view_mode == "source" and self.current_file:
            self.output.config(state="normal")
            self.output.insert("end", "\n  " + message + "\n", "warning")
            self.output.config(state="disabled")
            self.output.see("end")


    def _on_file_drop(self, event):
        self._hide_drop_feedback()
        paths = self._drop_paths(event.data)
        state = self._drop_state(paths)
        if state not in ("drop_md", "drop_txt", "drop_folder"):
            self._drop_notice(state)
            return "refuse_drop"
        path = paths[0]
        try:
            path = path.resolve(strict=True)
        except (OSError, ValueError) as error:
            self._drop_notice("drop_failed", str(error))
            return "refuse_drop"
        content = "" if state == "drop_folder" else self._read_drop_text(path)
        if content is None:
            return "refuse_drop"
        if self._confirm_navigation(lambda: self._finish_file_drop(path),
                                    target=None if path.is_dir() else path, defer=True):
            self._finish_file_drop(path, content)
        return "copy"

    def _finish_file_drop(self, path, content=None):
        if path.is_dir():
            # List the directory before changing state so an access failure preserves the draft.
            try:
                self.storage.files.list_directory(path)
            except StorageError as error:
                self._drop_notice("drop_failed", str(error))
                return
            previous = self.buffer_path
            self._clear_mode_stack()
            self._show_directory(path)
            if self.current_file is None and self.current_dir == path:
                self.document.close(discard=True)
                if previous is not None:
                    self._recovery_clear()
            self.entry.focus_set()
            return
        # Recheck the target after a dialog; it may have changed while waiting.
        if content is None:
            content = self._read_drop_text(path)
        if content is None:
            return
        if self.buffer.is_same_note(path) and self.buffer_dirty:
            self._show_markdown(path)  # Dropping the current note must preserve its unsaved edits.
        else:
            self._show_markdown(path, loaded_text=content)
        self._clear_mode_stack()
        self._recovery_sync()
        self.entry.focus_set()

    def _autosize_entry(self, _event=None):
        """Grow the input for explicit newlines, up to MAX_ENTRY_LINES. Wrapped text does not
        add rows.
        """
        lines = int(self.entry.index("end-1c").split(".")[0])
        self.entry.config(height=max(1, min(MAX_ENTRY_LINES, lines)))

    def _placeholder_send(self, event=None):
        if event and event.state & 0x0001:
            return None
        value = self.entry.get('1.0', 'end-1c').rstrip('\r\n')
        self.entry.delete('1.0', 'end')
        self._restore_command_draft()
        self._autosize_entry()
        self._ac_hide()
        if not value.strip():
            return 'break'
        prompt = value if '\n' not in value else '[pasted %d lines]' % len(value.splitlines())
        self._input_scroll_origin = (float(self.output.yview()[0]), self.output.index('@0,0'))
        if not REGISTRY.inspection(value):
            self._record_prompt(prompt)
        if REGISTRY.inspection(value):
            self._dispatch(value.strip())
        elif self.confirm_mode:
            self._handle_confirm(value.strip())
        elif '\n' in value:
            self._append_content(value)
        else:
            self._dispatch(value.strip())
        self._input_scroll_origin = None
        return 'break'

    def _run_command_as_shortcut(self, command_text):
        """Record and dispatch a shortcut through the normal command path."""
        self._input_scroll_origin = (float(self.output.yview()[0]), self.output.index('@0,0'))
        self._record_prompt(command_text)
        self._dispatch(command_text)
        self._input_scroll_origin = None
        return "break"

    def _focus_command(self, text):
        if self.grab_current() is not None or self._drop_open_pending:
            return "break"
        if self._entry_shortcut_draft is None:
            self._entry_shortcut_draft = self.entry.get("1.0", "end-1c")
        self.entry.delete("1.0", "end")
        self.entry.insert("1.0", text)
        self.entry.focus_set()
        self._autosize_entry()
        self._ac_on_key()
        return "break"

    def _restore_command_draft(self):
        if self._entry_shortcut_draft is not None:
            draft, self._entry_shortcut_draft = self._entry_shortcut_draft, None
            self.entry.delete("1.0", "end")
            self.entry.insert("1.0", draft)
            self._autosize_entry()

    def _shortcut_save(self, _event=None):
        return self._run_command_as_shortcut("/save")

    def _shortcut_undo(self, _event=None):
        return self._run_command_as_shortcut("/undo")

    def _shortcut_redo(self, _event=None):
        return self._run_command_as_shortcut("/redo")

    def _ac_all_commands(self):
        return REGISTRY.names()

    def _ac_on_key(self, _event=None):
        value = self.entry.get("1.0", "end-1c")
        if "\n" in value or not value.startswith("/"):
            self._ac_hide()
            return
        if _event and _event.keysym in ("Up", "Down", "Left", "Right", "Prior", "Next", "Home", "End"):
            return
        # A space starts keyword completion for the selected command.
        if " " in value:
            self._ac_update_keyword(value)
            return
        self._ac_update(value)

    def _ac_update(self, value):
        self.ac_mode = "command"
        query = value[1:].strip().lower()
        all_cmds = self._ac_all_commands()
        self.ac_filtered = [c for c in all_cmds if c.startswith(query)]
        if not self.ac_filtered:
            self._ac_hide()
            return
        self.ac_scroll_offset = 0
        self.ac_active_index = 0
        if not self.ac_visible or len(self.ac_item_widgets) == 0:
            self._ac_rebuild_items(query)
        else:
            self._ac_update_items()
        self._ac_show()

    def _ac_update_keyword(self, value):
        """Suggest registered keywords after a complete command name."""
        cmd, _, partial = value[1:].partition(" ")
        cmd = cmd.strip().lower()
        kw_map = REGISTRY.keywords(self.language)
        keywords = kw_map.get(cmd)
        # Stop suggesting once the keyword's following argument has begun.
        if not keywords or " " in partial:
            self._ac_hide()
            return
        prefix = partial.strip().lower()
        self.ac_mode = "keyword"
        self.ac_cmd = cmd
        self.ac_keywords = {k: d for k, d in keywords}
        # Hide exact matches so KeyRelease cannot reopen the same suggestion.
        if prefix in self.ac_keywords:
            self._ac_hide()
            return
        self.ac_filtered = [k for k, _d in keywords if k.startswith(prefix)]
        if not self.ac_filtered:
            self._ac_hide()
            return
        self.ac_scroll_offset = 0
        self.ac_active_index = 0
        if not self.ac_visible or len(self.ac_item_widgets) == 0:
            self._ac_rebuild_items(prefix)
        else:
            self._ac_update_items()
        self._ac_show()

    def _ac_update_items(self):
        """Refresh visible completion rows while reusing their widgets."""
        desc_map = REGISTRY.descriptions(self.language)
        max_visible = MAX_AUTOCOMPLETE_VISIBLE
        total = len(self.ac_filtered)
        count_text = self._t("matches") % total
        self.ac_count_label.config(text=count_text)
        showing = self.ac_filtered[self.ac_scroll_offset:self.ac_scroll_offset + max_visible]
        while len(self.ac_item_widgets) < len(showing):
            row = tk.Frame(self.ac_inner, bg=self.theme["ac_bg"], cursor="hand2")
            row.pack(fill="x")
            cmd_label = tk.Label(row, bg=self.theme["ac_bg"], fg=self.theme["ac_cmd_fg"],
                                  font=(self.cjk_family, FONT_SIZE_BOLD), anchor="w", padx=UI_AC_ITEM_PADX, pady=UI_AC_ITEM_PADY)
            cmd_label.pack(side="left", padx=UI_AC_CMD_DESC_PADX)
            desc_label = tk.Label(row, bg=self.theme["ac_bg"], fg=self.theme["muted"],
                                   font=(self.cjk_family, FONT_SIZE_NORMAL), anchor="e", padx=UI_AC_ITEM_PADX, pady=UI_AC_ITEM_PADY)
            desc_label.pack(side="right", fill="x", expand=True)
            self.ac_item_widgets.append(row)
        for w in self.ac_item_widgets[len(showing):]:
            w.pack_forget()
        for local_i, cmd in enumerate(showing):
            actual_index = self.ac_scroll_offset + local_i
            row = self.ac_item_widgets[local_i]
            cmd_label = row.winfo_children()[0]
            desc_label = row.winfo_children()[1]
            if self.ac_mode == "keyword":
                cmd_label.config(text=cmd)
                desc_label.config(text=self.ac_keywords.get(cmd, ""))
            else:
                cmd_label.config(text="/" + cmd)
                desc_label.config(text=desc_map.get(cmd, ""))
            for widget in (row, cmd_label, desc_label):
                widget.unbind("<Enter>")
                widget.unbind("<Button-1>")
                widget.bind("<Enter>", lambda _e, idx=actual_index: self._ac_set_active(idx))
                widget.bind("<Button-1>", lambda _e, idx=actual_index: self._ac_select_and_send(idx))
            row.pack(fill="x")
        self._ac_apply_highlight()
        item_height = AUTOCOMPLETE_ITEM_HEIGHT_PX
        count_height = AUTOCOMPLETE_COUNT_LABEL_HEIGHT_PX
        display_height = count_height + len(showing) * item_height
        self.ac_canvas.config(height=display_height)

    def _ac_rebuild_items(self, query):
        """Rebuild completion rows for a new result list."""
        for w in self.ac_item_widgets:
            w.destroy()
        self.ac_item_widgets = []
        self._ac_update_items()

    def _ac_apply_highlight(self):
        for local_i, w in enumerate(self.ac_item_widgets):
            actual_index = self.ac_scroll_offset + local_i
            bg = self.theme["ac_active_bg"] if actual_index == self.ac_active_index else self.theme["ac_bg"]
            fg_cmd = self.theme["ac_cmd_fg"]
            fg_desc = self.theme["ac_desc_active_fg"] if actual_index == self.ac_active_index else self.theme["muted"]
            w.config(bg=bg)
            cmd_label = w.winfo_children()[0]
            desc_label = w.winfo_children()[1]
            cmd_label.config(bg=bg, fg=fg_cmd)
            desc_label.config(bg=bg, fg=fg_desc)

    def _ac_set_active(self, index):
        if index < 0:
            index = 0
        if index >= len(self.ac_filtered):
            index = len(self.ac_filtered) - 1
        old_index = self.ac_active_index
        self.ac_active_index = index
        max_visible = MAX_AUTOCOMPLETE_VISIBLE
        if index > old_index:
            if index >= self.ac_scroll_offset + max_visible:
                self.ac_scroll_offset = index - max_visible + 1
                self._ac_update_items()
                return
        elif index < old_index:
            if index < self.ac_scroll_offset:
                self.ac_scroll_offset = index
                self._ac_update_items()
                return
        self._ac_apply_highlight()

    def _ac_show(self):
        if not self.ac_visible:
            self.ac_frame.pack(fill="x", side="bottom", before=self.body_frame)
            self.ac_visible = True

    def _ac_hide(self):
        if self.ac_visible:
            self.ac_frame.pack_forget()
            self.ac_visible = False

    def _ac_select(self, index=None):
        if index is None:
            index = self.ac_active_index
        if 0 <= index < len(self.ac_filtered):
            item = self.ac_filtered[index]
            self.entry.delete("1.0", "end")
            if self.ac_mode == "keyword":
                # Complete keywords without a trailing space, ready for Enter.
                self.entry.insert("1.0", "/" + self.ac_cmd + " " + item)
            else:
                self.entry.insert("1.0", "/" + item + " ")
            self._ac_hide()

    def _ac_select_and_send(self, index):
        self._ac_select(index)

    def _ac_tab(self, _event=None):
        if self.ac_visible and self.ac_filtered:
            self._ac_select()
            return "break"
        value = self.entry.get("1.0", "end-1c")
        if "\n" in value or not value.startswith("/"):
            return "break"
        typed = value[1:].strip().lower()
        if " " in typed:
            return "break"
        matches = [c for c in self._ac_all_commands() if c.startswith(typed)]
        if len(matches) == 1:
            self.entry.delete("1.0", "end")
            self.entry.insert("1.0", "/" + matches[0] + " ")
        elif matches:
            shared = os.path.commonprefix(matches)
            if len(shared) > len(typed):
                self.entry.delete("1.0", "end")
                self.entry.insert("1.0", "/" + shared)
        return "break"

    def _ac_up(self, _event=None):
        if self.ac_visible:
            self._ac_set_active(self.ac_active_index - 1)
            return "break"

    def _ac_down(self, _event=None):
        if self.ac_visible:
            self._ac_set_active(self.ac_active_index + 1)
            return "break"

    def _ac_escape(self, _event=None):
        if self.ac_visible:
            self._ac_hide()
            return "break"

    def _ac_resize(self, _event=None):
        self.ac_canvas.itemconfig(self.ac_canvas_window, width=self.ac_canvas.winfo_width())

    def _t(self, key):
        return tr(self.language, "ui." + key)

    # Business modes.
    # Mode properties read from the shared state stack.

    def _needs_workspace(self):
        if self.workspace:
            return False
        self.presentation.error('workspace_needed', self._t('workspace_needed'))
        return True

    def _split_chain(self, value):
        return split_chain(value)

    def _dispatch(self, value):
        """Dispatch commands and mode input without passing text to a shell."""
        if REGISTRY.inspection(value):
            return ROUTER.dispatch(self, value)
        effect_cursor = self.presentation.cursor
        segments = self._split_chain(value)
        for index, segment in enumerate(segments):
            self._dispatch_one(segment)
            if self._drop_open_pending:
                self._navigation_tail = segments[index + 1:]
                break
        # Sync recovery once after the full command chain completes.
        self._recovery_sync()
        return self.presentation.result_since(effect_cursor)

    def _dispatch_one(self, value):
        self._scroll_target = None
        return ROUTER.dispatch(self, value)


    def _workspace_files(self):
        return list(self.storage.files.scan(self.workspace))


    def _on_close(self):
        """Ask about unsaved changes before closing the window."""
        if self.buffer_dirty:
            self._show_exit_dialog()
        else:
            self._quit_app()

    def _quit_app(self):
        if self.control is not None and self.control.defer_quit():
            return
        self.closed = True
        self._stop_history_animation()
        if self.markdown_animator is not None:
            self.markdown_animator.stop()
        self.destroy()

    def _exit_save(self):
        # Keep the window open when saving fails.
        if self._flush_buffer():
            # The saved buffer no longer needs a recovery snapshot.
            self._recovery_sync()
            self._quit_app()

    def _exit_discard(self):
        # Discarding a draft must also discard its recovery snapshot.
        # Syncing here would save the still-dirty draft again.
        self._recovery_clear()
        self._quit_app()

    def _exit_cancel(self):
        # Closing the dialog already leaves the current draft in place.
        pass

    def _show_exit_dialog(self, on_continue=None):
        """Show the themed, keyboard-driven exit dialog."""
        ink = self.theme["dialog_ink"]
        paper = self.theme["dialog_paper"]
        muted = self.theme["dialog_muted"]
        top = tk.Toplevel(self)
        self._snapshot_dialog_kind = 'unsaved_navigation' if on_continue else 'unsaved_exit'
        self._snapshot_dialog_id = uuid4().hex
        top.transient(self)
        top.overrideredirect(True)
        top.configure(bg=paper)
        top.attributes("-topmost", True)

        # Match the main window's double frame.
        outer = tk.Frame(top, bg=ink, padx=2, pady=2)
        outer.pack(padx=10, pady=10)
        gap = tk.Frame(outer, bg=paper, padx=2, pady=2)
        gap.pack(fill="both", expand=True)
        inner = tk.Frame(gap, bg=ink, padx=1, pady=1)
        inner.pack(fill="both", expand=True)
        box = tk.Frame(inner, bg=paper)
        box.pack(fill="both", expand=True)

        tk.Label(box, text=self._t("drop_pending" if on_continue else "exit_title"), bg=ink, fg=paper,
                 font=self.ui_font, pady=2).pack(fill="x")
        name = self.buffer_path.name if self.buffer_path else ""
        tk.Label(box, text=self._t("exit_line") % (name, len(self.dirty_lines)),
                 bg=paper, fg=ink, font=self.ui_font, anchor="w", padx=8, pady=6).pack(fill="x")

        row = tk.Frame(box, bg=paper)
        row.pack(fill="x", padx=6, pady=(0, 6))
        labels = (self._t("exit_save"), self._t("exit_discard"), self._t("exit_cancel"))
        buttons = [tk.Label(row, text=text, bg=paper, fg=ink, font=self.ui_font, padx=2) for text in labels]
        for button in buttons:
            button.pack(side="left", padx=1)

        tk.Frame(box, bg=ink, height=1).pack(fill="x")
        tk.Label(box, text=self._t("exit_foot"), bg=paper, fg=muted,
                 font=self.ui_font, pady=2).pack(fill="x")

        state = {"sel": 0}

        def select(index):
            state["sel"] = index % len(buttons)
            for position, button in enumerate(buttons):
                on = position == state["sel"]
                button.configure(bg=ink if on else paper, fg=paper if on else ink)

        def act(index):
            self._snapshot_dialog_kind = None
            self._snapshot_dialog_id = None
            self._snapshot_dialog_answer = None
            # Release the modal grab before destroying its window.
            top.grab_release()
            top.destroy()
            # Restore focus to the command input after the dialog closes.
            # Tk may leave focus on the root; force it back to the input after idle.
            self.after(0, self.entry.focus_force)
            if on_continue is None:
                (self._exit_save, self._exit_discard, self._exit_cancel)[index]()
            else:
                self._drop_open_pending = False
                if index == 0:
                    if self._flush_buffer():
                        self._recovery_sync()
                        on_continue()
                    else:
                        self._navigation_tail = []
                elif index == 1:
                    on_continue()
                else:
                    self._navigation_tail = []

        self._snapshot_dialog_answer = lambda choice: act(('save', 'discard', 'cancel').index(choice))
        for index, button in enumerate(buttons):
            button.bind("<Enter>", lambda _event, index=index: select(index))
            button.bind("<Button-1>", lambda _event, index=index: act(index))

        def on_key(event):
            if event.keysym == "Escape":
                act(2)
            elif event.keysym == "Return":
                act(state["sel"])
            elif event.keysym in ("Tab", "Right", "Down"):
                select(state["sel"] + 1)
            elif event.keysym in ("Left", "Up"):
                select(state["sel"] - 1)
            return "break"

        top.bind("<Key>", on_key)
        select(0)
        self.update_idletasks()
        top.update_idletasks()
        top.geometry("+%d+%d" % (
            self.winfo_rootx() + (self.winfo_width() - top.winfo_reqwidth()) // 2,
            self.winfo_rooty() + (self.winfo_height() - top.winfo_reqheight()) // 2,
        ))
        # Map and raise borderless dialogs explicitly on Windows.
        top.deiconify()
        top.lift()
        top.update()
        top.focus_force()
        # Only grab input once the dialog is visible.
        if top.winfo_ismapped():
            top.grab_set()


    # Draft recovery.


    def _check_recovery(self):
        """Offer to restore a draft when its note still exists and differs from disk.

        Restoring loads the editing copy; only /save writes it back to the note.
        """
        data = self._recovery_load()
        if data is None:
            self._recovery_clear()   # Remove stale recovery data without interrupting startup.
            return
        note = Path(data["path"])
        snapshot_text = data["text"]
        # Read directly so stale recovery data does not produce a startup error.
        try:
            document = self.storage.documents.read(note)
            disk_text, disk_version = document.text, document.version
        except StorageError:
            disk_text = None
        if disk_text is None or disk_text == snapshot_text:
            self._recovery_clear()
            return
        dirty_lines = set(data.get("dirty_lines", ()))

        def _restore():
            # Restore the draft before rendering so the display uses it instead of disk.
            self.document.set(note, snapshot_text, dirty_lines=dirty_lines, dirty=True)
            self._buffer_disk_version = disk_version
            self._show_markdown(note)
            self._append_notice("[OK] " + self._t("recover_restored"), "success")

        def _discard():
            self._recovery_clear()
            self._append_notice("[!] " + self._t("recover_discarded"), "warning")

        self._append_notice("[!] " + self._t("recover_found") % note.name, "warning")
        self._set_confirm_mode(on_yes=_restore, on_no=_discard)

    # Saved preferences.


    def _persist_theme(self, name):
        """Save the theme without replacing other preferences."""
        config = self._load_config()
        config["version"] = config.get("version", CONFIG_VERSION)
        config["theme"] = name
        self._save_config(config)

    def _apply_theme(self, name):
        """Recolor existing widgets and text tags without rebuilding the document."""
        palette = THEMES[name]
        self.theme_name = name
        self.theme.clear()
        self.theme.update(palette)
        self.configure(bg=self.theme["background"])
        self.outer.config(bg=self.theme["border"])
        self.middle.config(bg=self.theme["background"])
        self.app.config(bg=self.theme["background"])
        self.body_frame.config(bg=self.theme["background"])
        self.header.config(bg=self.theme["panel"], fg=self.theme["foreground"])
        self.composer.config(bg=self.theme["panel"])
        self.prompt_label.config(bg=self.theme["panel"], fg=self.theme["heading"])
        self.entry.config(bg=self.theme["panel"], fg=self.theme["foreground"],
                          insertbackground=self.theme["foreground"])
        self.send.config(bg=self.theme["panel"], fg=self.theme["foreground"],
                         activebackground=self.theme["muted"], activeforeground=self.theme["background"])
        self.output.config(bg=self.theme["background"], fg=self.theme["foreground"],
                           insertbackground=self.theme["foreground"])
        for widget in (self.output, self.entry):
            widget.configure(selectbackground=self.theme["selection_background"],
                             selectforeground=self.theme["selection_foreground"],
                             inactiveselectbackground=self.theme["selection_background"])
        self.scrollbar.set_theme(self.theme)
        # Rebuild completion rows with the new palette next time they open.
        self.ac_frame.config(bg=self.theme["ac_bg"], highlightbackground=self.theme["ac_border"],
                             highlightcolor=self.theme["ac_border"])
        self.ac_count_label.config(bg=self.theme["ac_count_bg"], fg=self.theme["ac_count_fg"])
        self.ac_canvas.config(bg=self.theme["ac_bg"])
        self.ac_inner.config(bg=self.theme["ac_bg"])
        self._ac_hide()
        for w in self.ac_item_widgets:
            w.destroy()
        self.ac_item_widgets = []
        self.renderer.configure_tags()
        self._persist_theme(name)

    def _persist_workspace(self, path):
        """Save the workspace path while keeping other preferences."""
        config = self._load_config()
        config["version"] = config.get("version", CONFIG_VERSION)
        config["workspace"] = str(path)
        self._save_config(config)

    def _restore_persisted_workspace(self):
        """Restore a valid workspace, or remember the stale path for a notice."""
        self._restored = False
        self._stale_workspace = None
        raw = self._load_config().get("workspace")
        if not raw or not isinstance(raw, str):
            return
        path = Path(raw)
        if path.is_dir():
            self.workspace = self.current_dir = path
            self._restored = True
        else:
            self._stale_workspace = raw

    def _announce_restored_workspace(self):
        """List the restored workspace or report its stale path."""
        if self._restored:
            self._show_directory(self.workspace)
            self._append_notice("[OK] " + self._t("workspace_restored") + str(self.workspace), "success")
        elif self._stale_workspace:
            self._append_notice("[!] " + self._t("workspace_missing") + self._stale_workspace, "warning")


    def _clear_output(self):
        if self._rendered_path is not None:
            key = (self._rendered_path, self._rendered_view)
            self._reading_positions[key] = self.output.yview()[0]
            self._reading_positions.move_to_end(key)
            while len(self._reading_positions) > 24:
                self._reading_positions.popitem(last=False)
        self._rendered_text = None
        self._rendered_path = None
        self._rendered_view = None
        self._rendered_lines = []
        self.output.config(state="normal")
        self.renderer._begin_render()
        self.output.delete("1.0", "end")

    def _write(self, text, tag=None):
        self.console_history.append((text, tag))

    def _record_prompt(self, value):
        # Finish the previous reply before recording the next command.
        self._stop_history_animation()
        if self.append_mode:
            prompt = "APPEND> "
            tag = "string"
        elif self.open_mode:
            prompt = "OPEN> "
            tag = "success"
        else:
            prompt = "MARK> "
            tag = "marker"
        self.console_history.append(("\n" + prompt, tag))
        # Color command verbs and arguments separately.
        match = re.match(r"(/\S+)(.*)", value)
        if match:
            self.console_history.append((match.group(1), "command"))
            self.console_history.append((match.group(2) + "\n", "string" if match.group(2) else None))
        else:
            self.console_history.append((value + "\n", None))
        if self.view_mode == "console":
            self._render_history()

    def _console_width(self):
        """Fit terminal boxes to the available text width."""
        pixels = self.output.winfo_width() - 2 * int(self.output.cget("padx")) - 8
        cell = max(1, self.mono.measure("0"))
        return CONSOLE_MAX_WIDTH_CHARS if pixels < CONSOLE_NARROW_THRESHOLD_PX else max(CONSOLE_MIN_WIDTH_CHARS, min(CONSOLE_MAX_WIDTH_CHARS, pixels // cell - 4))

    def _stop_history_animation(self):
        """Cancel pending output before another command replaces it."""
        if self.history_after_id is not None:
            self.after_cancel(self.history_after_id)
            self.history_after_id = None
        if self.history_animator is not None:
            self.history_animator.stop()
            self.history_animator = None
        if hasattr(self, 'markdown_animator') and self.markdown_animator is not None:
            self.markdown_animator.stop()
            self.markdown_animator = None

    def _render_history(self):
        """Draw the complete command history immediately."""
        self._stop_history_animation()
        self._clear_output()
        for text, tag in self.console_history:
            self.output.insert("end", text, tag)
        self.output.config(state="disabled")
        self.output.see("end")

    def _animate_history_from(self, start, tick_delay=HISTORY_TICK_DELAY_MS, line_delay=HISTORY_LINE_DELAY_MS, columns_per_tick=HISTORY_COLUMNS_PER_TICK):
        """Draw earlier history immediately, then animate the new reply."""
        if not self.animations:
            self._render_history()
            return
        self._stop_history_animation()
        self._clear_output()
        for text, tag in self.console_history[:start]:
            self.output.insert("end", text, tag)

        # Store the animator so a later command can cancel it.
        animator = HistoryAnimator(
            self.output,
            self.after,
            self.console_history,
            start,
            tick_delay,
            line_delay,
            columns_per_tick
        )
        self.history_animator = animator
        animator.start()

    def _set_header(self, text):
        # The header shows the parent mode; the prompt shows the active mode.
        self._header_base = text
        self.header.config(text=" " + text + self._mode_tag())

    def _mode_tag(self):
        """Use the outer business mode as the header label."""
        if not self.mode_stack:
            return ""
        outer = self.mode_stack[0]
        return "  ·  " + outer.kind.upper() + " " + self._t("mode_suffix")

    def _refresh_header_mode(self):
        """Update the mode label without redrawing the document."""
        base = getattr(self, "_header_base", None)
        if base is not None:
            self.header.config(text=" " + base + self._mode_tag())

    def _show_console(self, title, lines):
        """Draw directory listings, help, and other results in a terminal box."""
        width = self._console_width()
        start = len(self.console_history)
        self._transition_view_mode("console")
        self._set_header("MARKPROMPT.EXE  ·  " + self._t("command"))
        caption = fit_display(" " + title + " ", width - 1).rstrip()
        # Leave the right edge open so narrow windows and wide glyphs still fit.
        self._write("  ┌─" + caption + "─" * max(0, width - 1 - display_width(caption)) + "\n", "marker")
        for line in lines:
            # Rows may carry a tag for search-result highlighting.
            if isinstance(line, tuple):
                text, tag = line
            else:
                text, tag = line, None
            self._write("  │ " + fit_display(text, width - 2).rstrip() + "\n", tag)
        self._write("  └" + "─" * width + "\n", "marker")
        self._animate_history_from(start)

    def _show_welcome(self, reset=False):
        """Show the wordmark and starting commands."""
        if not self._confirm_navigation(lambda: self._show_welcome(reset)):
            return
        self._cancel_find()
        start = 0 if reset else len(self.console_history)
        self._transition_view_mode("console")
        if reset:
            self._stop_history_animation()
            self.console_history = []
        self.current_file = None
        self._set_header(self._t("home_header"))
        self._write("\n")
        for line in MARKPROMPT_ART:
            self._write("  " + line + "\n", "art")
        self._write("\n  " + self._t("home") + "\n\n", "heading")
        if self.workspace:
            self._write("  [OK] " + self._t("workspace_set") + " " + str(self.workspace) + "\n", "muted")
            self._write("  /ls  ·  /new Title  ·  /help\n", "muted")
        else:
            self._write("  [!] " + self._t("no_workspace") + "\n", "muted")
            self._write("  " + self._t("home_hint") + "\n", "muted")
            self._write("  " + self._t("choose_workspace") + "\n", "muted")
            self._write("  " + self._t("example") + " /ws C:\\Notes\n", "string")
        if reset:
            self._render_history()
        else:
            self._animate_history_from(start)

    def _show_directory(self, path, change_directory=True):
        """List a directory and assign item numbers for /open."""
        if not self._confirm_navigation(lambda: self._show_directory(path, change_directory)):
            return False
        try:
            items = self.storage.files.list_directory(path)
        except StorageError as error:
            self._report_storage_error(error)
            return False
        if self.current_file is not None:
            self._clear_mode_stack()
            self.navigation.clear()
        if change_directory:
            self.current_dir = path
        self.current_file = None
        self.listed_items = dict(enumerate(items, start=1))
        rows = []
        for number, item in self.listed_items.items():
            kind = "D" if item.is_dir() else "M" if item.suffix.lower() == ".md" else "F"
            text = "[%s] %02d  %s" % (kind, number, item.name)
            # Highlight matching notes and folders containing matches.
            rows.append((text, "find-hit") if self._find_hit_mark(item) else text)
        self._show_console(self._t("directory") + "  " + str(path) + "  ·  %d " % len(items) + self._t("items_label"), rows or [self._t("empty")])
        self._set_header("MARKPROMPT.EXE  ·  " + self._t("browse") + "  ·  " + str(path))
        return True

    def _find_hit_mark(self, item):
        """Mark matching notes and folders whose descendants contain matches."""
        if not self.find_file_hits:
            return False
        if item.is_dir():
            return any(item in hit.parents for hit in self.find_file_hits)
        return item in self.find_file_hits


    def _apply_unsaved_tags(self):
        """Reapply dirty-line colors after text and command feedback are in place.

        Find lines by their number prefixes so appended feedback cannot shift the tags.
        """
        self.output.tag_remove("unsaved", "1.0", "end")
        if not self.dirty_lines or self.buffer_text is None:
            return
        ranges = []
        for number in self.dirty_lines:
            row = self._display_index_of_line(number)
            if row is not None:
                ranges.extend(("%d.0" % row, "%d.end" % row))
        if ranges:
            self.output.tag_add("unsaved", *ranges)

    # Search highlights use source-text character offsets.

    def _clear_search_highlights(self):
        self.output.tag_remove("search-hit", "1.0", "end")

    def _apply_search_highlights(self):
        self._clear_search_highlights()
        if not self.search_mode or self.view_mode != 'source':
            return 0
        hits = search_hits(self.buffer_text, self.search_term, self.search_fuzzy)
        prefix = max(3, len(str(len((self.buffer_text or '').splitlines())))) + 4
        for hit in hits:
            display = self._display_index_of_line(hit.line)
            if display is not None:
                self.output.tag_add('search-hit', '%d.0+%dc' % (display, prefix + hit.start),
                                    '%d.0+%dc' % (display, prefix + hit.end))
        return len(hits)

    def _cancel_scheduled(self, callback):
        try:
            self.after_cancel(callback)
        except tk.TclError:
            pass

    def _navigation_position(self):
        return (getattr(self, '_input_scroll_origin', None) or
                (float(self.output.yview()[0]), self.output.index('@0,0')))

    def _present_search_return(self, point):
        self._render_history()
        self._set_header('MARKPROMPT  ·  FIND  ·  ' + point.term)
        self._refresh_prompt()
        self.update_idletasks()
        self.output.yview(point.top_index)

    def _restore_search_scroll(self, value):
        self.update_idletasks()
        self.output.yview_moveto(value)


    def _scroll_to_first_hit(self):
        """Scroll to the source line containing the first search hit."""
        numbers = self._hit_lines()
        if numbers:
            self._scroll_to_line(numbers[0])

    def _display_index_of_line(self, number):
        return self.renderer.source_index(number)

    def _scroll_to_line(self, number):
        """Place a source line near VIEW_TARGET_FRACTION using its rendered pixel height.

        Tk clamps the position at document edges. Unmapped widgets have no geometry and
        are left alone.
        """
        index = self._display_index_of_line(number)
        if index is None:
            return
        target = "%d.0" % index
        self.output.see(target)          # Tk needs the line on screen before dlineinfo can measure it.
        self.update_idletasks()
        info = self.output.dlineinfo(target)
        self._last_position_line = number
        height = self.output.winfo_height()
        if info is None or height <= 1:
            return
        _x, y, _w, _h, _baseline = info
        delta = y - int(height * VIEW_TARGET_FRACTION)
        if delta:
            self.output.yview_scroll(delta, "pixels")

    def _show_markdown(self, path, scroll_to=None, loaded_text=None):
        """Show the current editing copy as Markdown, including unsaved changes.

        After rendering, an optional source line becomes the navigation target.
        """
        if path.suffix.lower() == ".txt":
            self._show_source(path, scroll_to=scroll_to, loaded_text=loaded_text)
            return
        if path.suffix.lower() != ".md" or not path.is_file():
            self._append_notice("[ERR] " + self._t("not_found") + " " + str(path), "error")
            return
        if not self._confirm_navigation(lambda: self._show_markdown(path, scroll_to=scroll_to), target=path):
            return
        if self.current_file != path:
            self._clear_mode_stack()
        prepared = self._prepare_document(path, loaded_text)
        if prepared is None:
            return
        content, switching_from_dirty = prepared
        # Animate a newly opened note; redraws of the same note keep their position.
        new_preview = self.current_file != path or self.view_mode == "console"
        # Clear stale navigation targets when changing notes.
        if scroll_to is not None:
            self._scroll_target = scroll_to
        elif new_preview:
            self._scroll_target = None
        if new_preview:
            # Start this note's feedback log after the opening command.
            self.preview_history_start = len(self.console_history)
        self.current_file = path
        self.current_dir = path.parent
        self._transition_view_mode("read")
        self.recent_files = [item for item in self.recent_files if item != path]
        self.recent_files.insert(0, path)
        self.recent_files = self.recent_files[:MAX_RECENT_FILES]
        label = "MARKPROMPT.EXE  ·  " + self._t("read") + "  ·  " + path.name
        if self.buffer_dirty:
            label += "  ·  [" + self._t("unsaved_marker") + "]"
        self._set_header(label)
        if not new_preview and self._patch_markdown(path, content):
            if self._scroll_target is not None:
                self._scroll_to_line(self._scroll_target)
            self.title("MarkPrompt — " + ("* " if self.buffer_dirty else "") + path.name)
            return
        if (not new_preview and self._rendered_path == path and self._rendered_view == "read" and
                self._rendered_text == content and
                (not self.renderer.has_images or abs(self.output.winfo_width() - self.mono.measure(" [000] ") - 55 - self.renderer.image_width) < 8)):
            self._refresh_preview_log()
            self._apply_unsaved_tags()
            if self._scroll_target is not None:
                self._scroll_to_line(self._scroll_target)
            self.title("MarkPrompt — " + ("* " if self.buffer_dirty else "") + path.name)
            return
        self._stop_history_animation()
        # Keep the viewport when a redraw has no explicit navigation target.
        preserve_frac = None if new_preview else self.output.yview()[0]
        self._clear_output()

        # Append feedback after the document animation has finished.
        self.renderer.set_document(path, content, self._t)
        def _finish_preview():
            self._set_preview_tail(path, content, "read")
            self._append_preview_log()
            self._append_bottom_padding()   # Allow the last line to reach the navigation target height.
            self._apply_unsaved_tags()
            if self._scroll_target is not None:
                self._scroll_to_line(self._scroll_target)
            elif new_preview:
                position = self._reading_positions.get((path, "read"), 0)
                if position:
                    self.output.yview_moveto(position)
                else:
                    self.output.see("1.0")
            else:
                self.output.yview_moveto(preserve_frac or 0.0)

        if new_preview and self.animations:
            # Only animate the first preview, not each edit or save.
            self.markdown_animator = self.renderer.render_animated(
                content, self.after, on_complete=_finish_preview, dirty_lines=self.dirty_lines)
        else:
            self.renderer.render(content, self.dirty_lines)
            _finish_preview()
        self.title("MarkPrompt — " + ("* " if self.buffer_dirty else "") + path.name)
        if switching_from_dirty:
            self._append_notice("[!] " + self._t("unsaved_lost"), "warning")

    def _show_source(self, path, scroll_to=None, loaded_text=None):
        """Show the editing copy with line numbers and literal Markdown syntax.

        Switching views of the same note preserves its viewport and skips the opening
        animation.
        """
        if path.suffix.lower() not in TEXT_FILE_SUFFIXES or not path.is_file():
            self._append_notice("[ERR] " + self._t("not_found") + " " + str(path), "error")
            return
        if not self._confirm_navigation(lambda: self._show_source(path, scroll_to=scroll_to), target=path):
            return
        prepared = self._prepare_document(path, loaded_text)
        if prepared is None:
            return
        content, switching_from_dirty = prepared
        new_note = self.current_file != path
        if scroll_to is not None:
            self._scroll_target = scroll_to
        elif new_note:
            self._scroll_target = None
        if new_note:
            self.preview_history_start = len(self.console_history)
        self.current_file = path
        self.current_dir = path.parent
        self._transition_view_mode("source")
        self.recent_files = [item for item in self.recent_files if item != path]
        self.recent_files.insert(0, path)
        self.recent_files = self.recent_files[:MAX_RECENT_FILES]
        kind = "text_preview" if path.suffix.lower() == ".txt" else "source"
        label = "MARKPROMPT.EXE  ·  " + self._t(kind) + "  ·  " + path.name
        if self.buffer_dirty:
            label += "  ·  [" + self._t("unsaved_marker") + "]"
        self._set_header(label)
        self._stop_history_animation()
        preserve_frac = None if new_note else self.output.yview()[0]
        self._clear_output()
        self.renderer.render_source(content, self.dirty_lines)
        self._set_preview_tail(path, content, "source")
        self._append_preview_log()
        self._append_bottom_padding()   # Allow the last line to reach the navigation target height.
        self._apply_unsaved_tags()
        self._apply_search_highlights()   # Reapply search highlights after rebuilding the source view.
        if self._scroll_target is not None:
            self._scroll_to_line(self._scroll_target)
        elif new_note:
            self.output.see("1.0")
        else:
            self.output.yview_moveto(preserve_frac or 0.0)
        self.title("MarkPrompt — " + ("* " if self.buffer_dirty else "") + path.name)
        if switching_from_dirty:
            self._append_notice("[!] " + self._t("unsaved_lost"), "warning")

    def _patch_markdown(self, path, content):
        """Patch a local line edit or append; structural changes use the full renderer."""
        if (self._rendered_path != path or self._rendered_view != "read" or
                self._rendered_text == content or self.renderer.has_images or
                self.renderer.table_rows or self.renderer.setext):
            return False
        old, new = self._rendered_lines, content.splitlines()
        if max(3, len(str(len(old)))) != max(3, len(str(len(new)))):
            return False
        structural = re.compile(r"^\s*(?:`{3,}|~{3,}|\[.+\]:|<!--|[=-]+\s*$)|\|")
        append = len(new) > len(old) and new[:len(old)] == old and len(new) - len(old) <= 200
        if append:
            changed = list(range(len(old), len(new)))
        elif len(new) == len(old):
            changed = [index for index, (before, after) in enumerate(zip(old, new)) if before != after]
            if len(changed) != 1 or changed[0] + 1 not in self.renderer.line_marks:
                return False
        else:
            return False
        if any(structural.search(new[index]) or (index < len(old) and structural.search(old[index])) for index in changed):
            return False
        self.output.configure(state="normal")
        if append:
            self.output.delete("preview-tail", "end-1c")
            code = self.renderer.code_after
            self.renderer.set_document(path, content, self._t)
            for index in changed:
                code = self.renderer._draw_line(index + 1, new[index], max(3, len(str(len(new)))), code, self.dirty_lines)
            self._set_preview_tail(path, content, "read")
            self._append_preview_log()
            self._append_bottom_padding()
        else:
            number = changed[0] + 1
            start = self.output.index(self.renderer.line_marks[number])
            following = next((mark for row, mark in self.renderer.line_marks.items() if row > number), "preview-tail")
            self.output.delete(start, following)
            self.output.mark_set("render-insert", start)
            self.output.mark_gravity("render-insert", "right")
            code = self.renderer.code_before[number]
            final_code = self.renderer.code_after
            self.renderer.set_document(path, content, self._t)
            self.renderer.insert_at = "render-insert"
            try:
                self.renderer._draw_line(number, new[number - 1], max(3, len(str(len(new)))), code, self.dirty_lines)
                self.renderer.code_after = final_code
                self.output.mark_set(following, "render-insert")
            finally:
                self.renderer.insert_at = "end"
                self.output.mark_unset("render-insert")
            self._rendered_text, self._rendered_lines = content, new
            self._refresh_preview_log()
        self.renderer.line_count = len(new)
        self._apply_unsaved_tags()
        self.output.configure(state="disabled")
        return True

    def _set_preview_tail(self, path, content, view):
        self.output.mark_set("preview-tail", "end-1c")
        self.output.mark_gravity("preview-tail", "left")
        self._rendered_path, self._rendered_text, self._rendered_view = path, content, view
        self._rendered_lines = content.splitlines()

    def _refresh_preview_log(self):
        """Refresh command feedback without rebuilding the document or its images."""
        if self._rendered_path != self.current_file or self._rendered_text != self.buffer_text:
            return False
        position = self.output.yview()[0]
        self.output.configure(state="normal")
        self.output.delete("preview-tail", "end-1c")
        self._append_preview_log()
        self._append_bottom_padding()
        self.output.configure(state="disabled")
        self.output.yview_moveto(position)
        return True

    def _append_preview_log(self):
        """Append this note's command feedback to the display, not to the file."""
        entries = self.console_history[self.preview_history_start:]
        if not entries:
            return
        self.output.config(state="normal")
        self.output.insert("end", "\n  " + "─" * 54 + "\n", "marker")
        self.output.insert("end", "  " + self._t("command_log") + "\n", "heading")
        for text, tag in entries:
            self.output.insert("end", text, tag)
        self.output.config(state="disabled")

    def _append_bottom_padding(self):
        """Add display-only space so the last source line can reach the navigation target.

        Padding has no line-number prefix and does not affect source mapping or dirty
        tags. Unmapped widgets need no padding.
        """
        viewport = self.output.winfo_height()
        line_px = self.mono.metrics("linespace")
        if viewport <= 1 or line_px <= 0:
            return
        needed = int(viewport * (1.0 - VIEW_TARGET_FRACTION))
        pad_lines = -(-needed // line_px) + 1     # Round up and allow for mixed line heights.
        self.output.config(state="normal")
        self.output.insert("end", "\n" * pad_lines)
        self.output.config(state="disabled")

    def _append_notice(self, message, tag):
        """Append an OK, warning, or error message to the current display."""
        start = len(self.console_history)
        if self.console_history:
            self.console_history.append(("\n", None))
        match = re.match(r"(\[[^\]]+\])(.*)", message)
        if match:
            self.console_history.append(("  " + match.group(1), tag))
            self.console_history.append((match.group(2) + "\n", None))
        else:
            self.console_history.append(("  " + message + "\n", tag))
        if self.view_mode == "console":
            self._animate_history_from(start)
        elif self.view_mode in ("read", "source") and self.current_file:
            # Let the running animation append feedback when it finishes.
            anim = self.markdown_animator
            if anim is not None and anim.after_id is not None:
                return
            if not self._refresh_preview_log():
                if self.view_mode == "source":
                    self._show_source(self.current_file)
                else:
                    self._show_markdown(self.current_file)


if __name__ == "__main__":
    MarkPromptApp().mainloop()
