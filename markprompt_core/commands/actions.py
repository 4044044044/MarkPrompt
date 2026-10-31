"""Shared command actions for window and headless sessions."""
import re
from pathlib import Path
from markprompt_core.application.navigation import SearchReturn
from markprompt_core.storage.platform import system_open
from markprompt_core.ui.resources import TEXT, THEMES
from markprompt_core.commands.catalog import REGISTRY
from markprompt_core.storage.local import StorageError

TREE_MAX_CHILDREN = 12
EXT_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]*)\)")

EXT_URL_RE = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.\-]*://|mailto:)", re.IGNORECASE)

class CommandActions:
    background_search = True
    snapshot_export_default = True

    def _command_snapshot(self, argument):
        from markprompt_core.automation.snapshot import capture, syntax
        try:
            full, destination = syntax(argument)
            snapshot = capture(self, full)
            exported = None
            if destination:
                target = Path(destination).expanduser()
                if not target.is_absolute():
                    target = (self.current_dir or self.workspace or Path.cwd()) / target
                exported = self.storage.export_snapshot(target, snapshot)
            elif self.snapshot_export_default:
                target = self.storage.snapshot_directory(self.workspace, self.config_path) / ('snapshot-' + snapshot['snapshot_id'] + '.json')
                exported = self.storage.export_snapshot(target, snapshot)
            self.presentation.data(snapshot=snapshot, snapshot_path=str(exported) if exported else None)
            if exported:
                self.presentation.notice('[OK] Snapshot: ' + str(exported), 'success')
        except ValueError as error:
            self.presentation.error('invalid_arguments', str(error))
        except StorageError as error:
            self._report_storage_error(error)

    def _command_data(self, **data):
        """Presentation hook; structured adapters may consume action results."""

    def _command_open(self, argument):
        if not argument:
            self._set_open_mode(True)
            self.presentation.notice('[OK] ' + self._t('open_on'), 'success')
            return
        shortcut = argument.strip().strip('"').lower()
        if shortcut == 'desktop':
            choices = (Path.home() / 'Desktop', Path.home() / 'OneDrive' / 'Desktop')
            target = next((p for p in choices if p.is_dir()), choices[0])
        elif shortcut in ('workspace', 'ws'):
            if self._needs_workspace():
                return
            target = self.workspace
        elif shortcut.startswith('@'):
            if self._needs_workspace():
                return
            value = self._bookmarks().get(shortcut[1:])
            if value is None:
                self.presentation.notice('[!] ' + self._t('bookmark_not_found') + shortcut, 'warning')
                return
            target = Path(value)
        elif re.fullmatch(r'[0-9]+', shortcut):
            target = self.listed_items.get(int(shortcut))
            if target is None:
                self.presentation.notice('[!] ' + self._t('list_not_found') + shortcut, 'warning')
                return
        else:
            target = self._resolve_path(argument)
        if target is not None and not self.presentation.confirm(
                lambda: self._command_open(argument), target=target if target.is_file() else None):
            return
        if target is not None and self._visit_path(target) and target.is_dir():
            self._set_open_mode(True)

    def _capture_search_return(self):
        if not self.find_mode or self.current_file is not None or self.workspace is None:
            return None
        scroll, top = self.presentation.position()
        return SearchReturn(self.workspace, self.current_dir or self.workspace, self.find_term or '',
                            frozenset(self.find_file_hits), tuple(self._find_rows),
                            self.presentation.history(), dict(self.listed_items),
                            scroll, pending=self._find_future is not None, top_index=top)

    def _refresh_document(self, scroll_to=None):
        if self.presentation.view == 'source':
            self.presentation.source(self.current_file, scroll_to=scroll_to)
        else:
            self.presentation.document(self.current_file, scroll_to=scroll_to)

    def _visit_path(self, path):
        if not path.exists():
            self.presentation.notice('[ERR] ' + self._t('not_found') + ' ' + str(path), 'error')
            return False
        if not self.presentation.confirm(lambda: self._visit_path(path), target=path if path.is_file() else None):
            return False
        if path.is_dir():
            was_document = self.current_file is not None
            if not self.presentation.directory(path, True):
                return False
            if was_document:
                self._clear_mode_stack()
                self.navigation.clear()
            return True
        if path.suffix.lower() not in ('.md', '.txt'):
            self.presentation.notice('[!] ' + self._t('markdown_only'), 'warning')
            return False
        content = self.buffer_text if self.buffer.is_same_note(path) and self.buffer_dirty else self._read_disk(path)
        if content is None:
            return False
        point = self._capture_search_return()
        if self.buffer.is_same_note(path) and self.buffer_dirty:
            self.presentation.document(path)
        else:
            self.presentation.document(path, loaded_text=content)
        if self.current_file != path:
            return False
        self._clear_mode_stack()
        if point is not None:
            self.navigation.remember(point)
            if point.term.lower() in content.lower() and path.suffix.lower() == '.md':
                self._run_search(point.term, True)
        return True

    def _try_open_file(self, value):
        """Handle OPEN-mode input using the same paths, numbers, and bookmarks as /open."""
        if not value.strip():
            return
        # Use the same argument parsing as /open.
        self._command_open(value.strip())

    # Workspace commands.

    def _command_workspace(self, argument):
        if not argument:
            self.presentation.notice('[!] ' + self._t('usage') + ' /workspace <folder|here>', 'warning')
            return
        path = self.current_dir if argument == 'here' else Path(argument.strip('"'))
        if path is None or not path.is_dir():
            self.presentation.notice('[ERR] ' + self._t('not_directory') + ' ' + str(path), 'error')
            return
        path = path.resolve()
        try:
            self.storage.files.list_directory(path)
        except StorageError as error:
            self._report_storage_error(error)
            return
        self._clear_mode_stack()
        self.navigation.clear()
        self.workspace = self.current_dir = path
        self._persist_workspace(path)
        self.presentation.directory(path)
        self.presentation.notice('[OK] ' + self._t('workspace_set') + ' ' + str(path), 'success')


    def _command_bookmark(self, argument):
        """List, add, or remove named workspace directory bookmarks."""
        if self._needs_workspace():
            return
        action, _, value = argument.partition(" ")
        action = action.lower()
        bookmarks = self._bookmarks()
        if action in ("", "list"):
            rows = ["@%s  %s" % (name, path) for name, path in sorted(bookmarks.items())]
            self.presentation.console(self._t("bookmarks"), rows or [self._t("no_results")])
            return
        name, _, path_text = value.partition(" ")
        name = name.lower()
        if not re.fullmatch(r"[a-z0-9_-]+", name):
            self.presentation.notice("[!] " + self._t("usage") + " /bookmark add name [folder]", "warning")
            return
        if action == "remove":
            if name in bookmarks:
                del bookmarks[name]
                self._save_bookmarks(bookmarks)
                self.presentation.notice("[OK] " + self._t("bookmark_removed") + name, "success")
            else:
                self.presentation.notice("[!] " + self._t("bookmark_not_found") + "@" + name, "warning")
            return
        if action == "add":
            path = self._resolve_path(path_text) if path_text else self.current_dir
            if not path or not path.is_dir():
                self.presentation.notice("[!] " + self._t("usage") + " /bookmark add name [folder]", "warning")
                return
            bookmarks[name] = str(path)
            self._save_bookmarks(bookmarks)
            self.presentation.notice("[OK] " + self._t("bookmark_saved") + name, "success")
            return
        self.presentation.notice("[!] " + self._t("usage") + " /bookmark add|list|remove", "warning")

    def _command_pwd(self, _argument):
        none = self._t("none")
        self.presentation.console(self._t("current_directory"), [str(self.current_dir or none), "workspace: " + str(self.workspace or none)])

    def _command_status(self, _argument):
        none = self._t("none")
        self.presentation.console("STATUS", [
            "workspace: " + str(self.workspace or none), "directory: " + str(self.current_dir or none),
            "note: " + str(self.current_file or none), "language: " + self.language,
        ])

    def _command_ls(self, argument):
        path = self._resolve_path(argument) if argument else self.current_dir
        if path:
            self.presentation.directory(path, False)

    def _command_cd(self, argument):
        path = self._resolve_path(argument) if argument else None
        if path:
            self.presentation.directory(path, True)

    def _command_up(self, _argument):
        if self.current_dir:
            self.presentation.directory(self.current_dir.parent, True)
        else:
            self._needs_workspace()

    def _command_tree(self, _argument):
        if self.current_dir:
            self._show_tree()
        else:
            self._needs_workspace()

    def _command_back(self, _argument):
        point = self.navigation.search if self.current_file else None
        if point and point.workspace == self.workspace and point.directory.is_dir():
            if not self.presentation.directory(point.directory):
                return
            self.navigation.clear()
            self._clear_mode_stack()
            self._push_mode('find')
            self.find_term = point.term
            self.find_file_hits = set(point.hits)
            self._find_rows = point.rows
            self.console_history = list(point.history)
            self.listed_items = dict(point.listed)
            self.presentation.search_return(point)
            if point.pending:
                self._command_find(point.term)
                if self._find_future is None:
                    self.presentation.restore_scroll(point.scroll)
                else:
                    self._find_return_scroll = point.scroll
            return
        self._clear_mode_stack()
        self.navigation.clear()
        if self.current_dir:
            self.presentation.directory(self.current_dir)
        else:
            self.presentation.home()

    def _command_reload(self, _argument):
        if self.current_file:
            self.presentation.document(self.current_file)
        elif self.current_dir:
            self.presentation.directory(self.current_dir)
        else:
            self.presentation.home()

    def _command_home(self, _argument):
        self.navigation.clear()
        self._clear_mode_stack()
        self.presentation.home()

    def _command_new(self, title):
        if self._needs_workspace() or not title:
            if not title:
                self.presentation.notice("[!] " + self._t("usage") + " /new Title", "warning")
            return
        safe = self._safe_name(title)
        if not safe:
            self.presentation.notice("[!] " + self._t("invalid_name"), "warning")
            return
        target = self.workspace / (safe + ".md")
        if target.exists():
            # Ask before overwriting an existing note.
            self.presentation.overwrite(target, lambda: self._create_new_file(target, title))
            return
        self._create_new_file(target, title)

    def _create_new_file(self, target, title):
        """Create and open a note after any overwrite confirmation."""
        if not self._write_file(target, "# " + title + "\n\n"):
            return
        self.presentation.document(target, loaded_text="# " + title + "\n\n")

    def _command_jot(self, title):
        """Create a note and enter append mode once creation succeeds."""
        if self._needs_workspace() or not title:
            if not title:
                self.presentation.notice("[!] " + self._t("usage") + " " + self._t("jot_usage"), "warning")
            return
        safe = self._safe_name(title)
        if not safe:
            self.presentation.notice("[!] " + self._t("invalid_name"), "warning")
            return
        target = self.workspace / (safe + ".md")
        if target.exists():
            self.presentation.overwrite(target, lambda: self._create_jot_file(target, title))
            return
        self._create_jot_file(target, title)

    def _create_jot_file(self, target, title):
        """Open the new note and start continuous capture."""
        if not self._write_file(target, "# " + title + "\n\n"):
            return
        self.presentation.document(target, loaded_text="# " + title + "\n\n")
        self._set_append_mode(True)
        self.presentation.notice("[OK] " + self._t("jot_on"), "success")

    def _command_preview(self, _argument):
        if self._require_note(allow_text=True):
            self.presentation.document(self.current_file)

    def _command_source(self, _argument):
        """Show the literal Markdown source with line numbers."""
        if self._require_note(allow_text=True):
            self.presentation.source(self.current_file)

    def _command_view(self, _argument):
        """Toggle Markdown preview and source view."""
        if not self._require_note(allow_text=True):
            return
        if self.presentation.view == "source":
            self.presentation.document(self.current_file)
        else:
            self.presentation.source(self.current_file)

    def _command_search(self, argument):
        fuzzy = False
        if argument == '-i' or argument.startswith('-i '):
            fuzzy, argument = True, argument[2:].strip()
        elif argument == '--ignore-case' or argument.startswith('--ignore-case '):
            fuzzy, argument = True, argument[len('--ignore-case'):].strip()
        elif argument.startswith('-- '):
            argument = argument[3:]
        elif argument.startswith('-'):
            self.presentation.notice('[!] ' + self._t('usage') + ' /search [-i] [text]', 'warning')
            return
        self._run_search(argument, fuzzy)


    def _run_search(self, argument, fuzzy):
        """Search the current editing copy and show matching source lines.

        A query with no hits stays in search mode so the next query can be entered
        directly.
        """
        if not self._require_note():
            return
        if len(argument.split()) >= 2:
            self.presentation.notice("[!] " + self._t("search_danger"), "warning")
            return
        self._set_search_mode(True)
        self.search.query.begin(argument, fuzzy)
        self.presentation.source(self.current_file)   # Source view keeps search offsets aligned with the buffer.
        if not self.search_term:
            return
        count = self.presentation.highlights()
        if count:
            numbers = self._hit_lines()
            report = "[OK] %d %s %s · %s %s" % (
                count, self._t("search_hits"), self.search_term,
                self._t("search_lines"), self._format_hit_lines(numbers))
            self.presentation.notice(report, "success")
            # Append the report while keeping the first match in view.
            self.presentation.source(self.current_file, scroll_to=numbers[0])
        else:
            missed = self.search_term
            self.search_term = None
            self.presentation.clear_highlights()
            self.presentation.notice("[!] " + self._t("search_not_found") + missed, "warning")
            self.presentation.source(self.current_file)   # Make the no-results notice visible without resetting the viewport.

    def _scoped_replace(self, replacement):
        if not self.search.query.term or not self._ensure_buffer_for_current():
            return None
        return self.search.query.replace(self.buffer, replacement)

    def _scoped_edit(self, replacement, replace):
        """Replace hits in the current note or line scope, then refresh source view.

        Require a search term, keep the existing query, and recalculate highlights from
        the edited buffer.
        """
        if not self._require_note():
            return
        if not self.search_mode or not self.search_term:
            self.presentation.notice("[!] " + self._t("search_required"), "warning")
            if self.presentation.view == "source" and self.current_file:
                self.presentation.source(self.current_file)   # Refresh source view so the edit result appears in the feedback log.
            return
        count = self._scoped_replace(replacement)
        if count is None:
            return
        if count == 0:
            self.presentation.notice("[!] " + self._t("search_scope_empty"), "warning")
        elif replace:
            self.presentation.notice("[OK] %d %s%s → %s" % (
                count, self._t("search_replaced"), self.search_term, replacement), "success")
        else:
            self.presentation.notice("[OK] %d %s%s" % (
                count, self._t("search_deleted"), self.search_term), "success")
        scroll_to = self.search_scope_line if self.search_scope == "line" else None
        self.presentation.source(self.current_file, scroll_to=scroll_to)

    def _command_replace(self, argument):
        """Replace all search hits in the current scope."""
        self._scoped_edit(argument, replace=True)

    def _command_delete(self, _argument):
        """Remove all search hits in the current scope."""
        self._scoped_edit("", replace=False)

    def _command_save(self, _argument):
        if not self._require_note():
            return
        if not self.buffer_dirty:
            self.presentation.notice("[!] " + self._t("no_changes"), "warning")
            return
        if not self._flush_buffer():
            return
        self._refresh_document()
        self.presentation.notice("[OK] " + self._t("saved") + " " + self.current_file.name, "success")

    def _command_saveas(self, argument):
        """Save the editing copy under a new workspace filename.

        Keep the old file and heading; switch to the new, clean copy after saving.
        """
        if not self._require_note() or self._needs_workspace():
            return
        name = argument.strip().strip('"')
        if not name:
            self.presentation.notice("[!] " + self._t("usage") + " " + self._t("saveas_usage"), "warning")
            return
        if name.lower().endswith(".md"):
            name = name[:-3]
        safe = self._safe_name(name)
        if not safe:
            self.presentation.notice("[!] " + self._t("invalid_name"), "warning")
            return
        target = self.workspace / (safe + ".md")
        if target.exists():
            self.presentation.overwrite(target, lambda: self._do_saveas(target))
            return
        self._do_saveas(target)

    def _do_saveas(self, target):
        if not self._ensure_buffer_for_current():
            return
        content = self.buffer_text
        if not self._write_file(target, content):
            return
        self.current_file = target
        self._set_buffer(target, content, dirty_lines=None, dirty=False)
        self.presentation.document(target)
        self.presentation.notice("[OK] " + self._t("saved_as") + " " + target.name, "success")

    def _command_append(self, text):
        if self.search_mode:
            self.presentation.error('append_search_blocked', self._t('append_search_blocked'))
            return
        if not self._require_note():
            return
        if text:
            self._append_content(text)
        elif self._set_append_mode(True):
            self.presentation.notice('[OK] ' + self._t('append_on'), 'success')

    def _command_end(self, _argument):
        """Leave one business level; never save, undo, or close the document."""
        frame = self._pop_top_mode()
        if frame:
            self.presentation.notice('[OK] ' + self._t('state_ended') + frame.kind.upper(), 'success')

    def _append_content(self, text):
        """Append one line or pasted text to the editing copy; leave disk writes to /save."""
        if self.search_mode:
            self.presentation.error('append_search_blocked', self._t('append_search_blocked'))
            return
        if not self._require_note() or not text:
            return
        if not self._ensure_buffer_for_current():
            return
        # Scroll to the first newly appended line.
        first_new = len(self.buffer_text.splitlines()) + 1 if self.buffer_text is not None else 1
        # The buffer tracks dirty lines using physical source line numbers.
        if not self.buffer.append(text):
            return
        self.presentation.document(self.current_file, scroll_to=first_new)
        self.presentation.notice("[OK] " + self._t("unsaved_pending"), "success")
        # Pasted text can bypass command dispatch, so sync recovery here too.
        self._recovery_sync()

    def _command_line(self, argument):
        """Navigate to a line or replace it; during search, edit only that line's hits."""
        if argument.startswith('delete '):
            self._delete_line(argument[7:].strip())
            return
        if argument == 'delete':
            self.presentation.notice('[!] ' + self._t('usage') + ' /line delete N', 'warning')
            return
        if not self._require_note():
            return
        content = self._read_file(self.current_file)
        if content is None:
            return
        number, _, replacement = argument.partition(" ")
        lines = content.splitlines(True)
        if not number.isdigit() or not 1 <= int(number) <= len(lines):
            self.presentation.notice("[!] " + self._t("usage") + " /line 12 replacement text", "warning")
            return
        target = int(number)
        if self.search_mode:
            # In search mode, /line N narrows the scope and optional text replaces its hits.
            # Share the scoped-edit path with /replace.
            self._set_line_scope(target)
            if replacement:
                self._command_replace(replacement)
            else:
                self.presentation.source(self.current_file, scroll_to=target)
            return
        if not replacement:
            # A line number alone navigates without editing.
            # Scroll an existing document view directly to avoid a redundant redraw.
            if self.presentation.view in ("read", "source"):
                self.presentation.scroll(target)
            else:
                self.presentation.document(self.current_file, scroll_to=target)
            return
        if not self._ensure_buffer_for_current():
            return
        if not self.buffer.replace_line(target, replacement):
            return
        self.presentation.document(self.current_file, scroll_to=target)
        self.presentation.notice("[OK] " + self._t("line_word") + " " + number + " · " + self._t("unsaved_pending"), "success")

    def _delete_line(self, argument):
        """Delete a whole line normally, or only its matched text during search."""
        if not self._require_note():
            return
        number = argument.strip()
        if not number.isdigit():
            self.presentation.notice("[!] " + self._t("usage") + " /linedel 5", "warning")
            return
        content = self._read_file(self.current_file)
        if content is None:
            return
        total = len(content.splitlines(True))
        target = int(number)
        if not 1 <= target <= total:
            self.presentation.notice("[!] " + self._t("usage") + " /linedel 1-" + str(total), "warning")
            return
        if self.search_mode:
            if not self.search_term:
                self.presentation.notice('[!] ' + self._t('search_required'), 'warning')
                return
            # During search, remove only the hits on this line.
            self._set_line_scope(target)
            self._command_delete("")
            return
        if not self._ensure_buffer_for_current():
            return
        if not self.buffer.delete_line(target):
            return
        # Deleting the last line leaves its old number out of range.
        # Clamp the target to the remaining document.
        new_total = total - 1
        scroll_to = max(1, min(target, new_total)) if new_total >= 1 else None
        self.presentation.document(self.current_file, scroll_to=scroll_to)
        self.presentation.notice("[OK] " + self._t("line_deleted") + " " + number + " · " + self._t("unsaved_pending"), "success")

    def _command_undo(self, _argument):
        """Restore the previous editing copy without writing to disk."""
        if not self._require_note():
            return
        if not self.buffer.undo():
            self.presentation.notice("[!] " + self._t("nothing_undo"), "warning")
            return
        self._refresh_document()
        self.presentation.notice("[OK] " + self._t("undone"), "success")

    def _command_redo(self, _argument):
        """Restore the edit most recently undone."""
        if not self._require_note():
            return
        if not self.buffer.redo():
            self.presentation.notice("[!] " + self._t("nothing_redo"), "warning")
            return
        self._refresh_document()
        self.presentation.notice("[OK] " + self._t("redone"), "success")

    def _command_external(self, argument):
        if not self._require_note():
            return
        action, _, value = argument.partition(' ')
        if action in ('', 'file'):
            if value:
                self.presentation.notice('[!] /external file', 'warning')
                return
            try:
                system_open(self.current_file)
            except OSError as error:
                self.presentation.notice('[!] ' + self._t('ext_open_failed') + str(error), 'warning')
        elif action == 'links' and not value:
            self._external_links('')
        elif action == 'link' and value and value.split()[0].isdigit():
            self._external_links(value)
        elif action == 'open' and value:
            self._ext_open(value)
        else:
            self.presentation.notice('[!] ' + self._t('usage') + ' /external [file|links|link N [index]|open target]', 'warning')

    def _command_title(self, title):
        """Change the first top-level heading, or insert one if absent.

        The filename stays unchanged; this is an undoable edit saved by /save.
        """
        if not self._require_note():
            return
        if not title:
            self.presentation.notice("[!] " + self._t("usage") + " " + self._t("title_usage"), "warning")
            return
        if not self._ensure_buffer_for_current():
            return
        heading = "# " + title.strip()
        lines = self.buffer_text.splitlines(True)
        number = next((index for index, line in enumerate(lines, start=1) if line.startswith("# ")), None)
        if number is not None:
            self.buffer.replace_line(number, heading)
        else:
            new_text = heading + "\n\n" + self.buffer_text
            self.buffer.mutate(new_text, set(range(1, len(new_text.splitlines()) + 1)))
        if self.presentation.view == "source":
            self.presentation.source(self.current_file)
        else:
            self.presentation.document(self.current_file)
        self.presentation.notice("[OK] " + self._t("title_updated") + " " + title.strip(), "success")

    def _command_find(self, term):
        if self.current_file is not None:
            self.presentation.notice('[!] ' + self._t('find_doc_reject'), 'warning')
            return
        if self._needs_workspace():
            return
        term = term.strip()
        if not term:
            self.presentation.notice('[!] ' + self._t('usage') + ' /find <text>', 'warning')
            return
        self._cancel_find()
        if self.states.active == 'open' and self.find_mode:
            self.states.pop()
        if not self.find_mode:
            self._clear_mode_stack()
            self._push_mode('find')
        self.presentation.prompt()
        workspace = self.workspace.resolve()
        update = self.search.start_find(workspace, term, self.background_search)
        if update.status == 'complete':
            self._finish_find(term, update.result)
        else:
            self.presentation.notice('[!] ' + self._t('find_running'), 'muted')
            self._poll_find(term, workspace, update.future)

    def _cancel_find(self):
        self.search.cancel()
        if self._find_after is not None:
            self.presentation.cancel_later(self._find_after)
        self._find_after = None

    def _poll_find(self, term, workspace, future):
        self._find_after = None
        update = self.search.poll(future)
        if update.status == 'stale':
            return
        if update.status == 'error':
            self.presentation.notice('[!] ' + self._t('find_failed') + str(update.error), 'warning')
        elif update.status == 'complete':
            if self.workspace is not None and self.workspace.resolve() == workspace and self.find_term == term and self.find_mode:
                self._finish_find(term, update.result)
        else:
            self.presentation.header(self._t('find_progress') % update.progress)
            self._find_after = self.presentation.later(30, lambda: self._poll_find(term, workspace, future))

    def _finish_find(self, term, result):
        if result is None:
            return
        rows, hits, skipped = result
        self.find_file_hits = hits
        self.presentation.data(query=term, results=[{'path': str(workspace_path), 'matching_lines': count}
                           for workspace_path, count in rows], skipped=skipped)
        self._find_rows = tuple(rows)
        self._render_find_results(term, rows, sum(count for _path, count in rows))
        if self.current_dir and self.current_dir.is_dir():
            self.presentation.directory(self.current_dir, change_directory=False)
        if skipped:
            self.presentation.notice("[!] " + self._t("find_skipped") % skipped, "warning")
        self._restore_find_scroll()

    def _restore_find_scroll(self):
        if self._find_return_scroll is not None:
            self.presentation.restore_scroll(self._find_return_scroll)
            self._find_return_scroll = None

    def _render_find_results(self, term, per_file, total_hits):
        """List matching resource names and hit counts in a terminal box."""
        title = 'FIND  "%s"  ·  %d %s  ·  %d %s' % (
            term, len(per_file), self._t("find_files"), total_hits, self._t("find_hits"))
        if not per_file:
            self.presentation.console(title, [self._t("no_results")])
            return
        lines = ["%s  (%d)" % (rel, count) for rel, count in per_file]
        self.presentation.console(title, lines)

    def _command_recent(self, argument):
        paths = [path for path in self.recent_files if path.is_file() and argument.casefold() in str(path).casefold()]
        self._show_file_choices(self._t("recent"), paths)

    def _show_file_choices(self, title, paths, root=None):
        self._cancel_find()
        self.listed_items = dict(enumerate(paths, 1))
        rows = ["%02d  %s" % (number, path.relative_to(root) if root else path)
                for number, path in self.listed_items.items()]
        self.presentation.console(title, rows or [self._t("no_results")])
        if paths:
            self._set_open_mode(True)

    def _command_files(self, argument):
        root = self.workspace or self.current_dir
        if root is None:
            self._command_recent(argument)
            return
        root = root.resolve()
        self._cancel_find()
        update = self.search.start_files(root, argument, self.background_search)
        if update.status == 'complete':
            self._show_file_choices(self._t('files'), update.result, root)
        else:
            self.presentation.notice('[!] ' + self._t('find_running'), 'muted')
            self._poll_files(root, update.future)

    def _poll_files(self, root, future):
        self._find_after = None
        update = self.search.poll(future)
        if update.status == 'stale':
            return
        if update.status == 'error':
            self.presentation.notice('[!] ' + self._t('find_failed') + str(update.error), 'warning')
        elif update.status == 'complete':
            if update.result is not None:
                self._show_file_choices(self._t('files'), update.result, root)
        else:
            self._find_after = self.presentation.later(30, lambda: self._poll_files(root, future))

    def _command_outline(self, argument):
        if not self._require_note():
            return
        headings, fence = [], False
        for number, line in enumerate(self.buffer_text.splitlines(), 1):
            if line.startswith(("```", "~~~")):
                fence = not fence
            match = re.match(r"^(#{1,6})\s+(.+)", line) if not fence else None
            if match:
                headings.append((number, len(match[1]), match[2]))
        self.presentation.data(headings=[{'number': i, 'line': line, 'level': level, 'text': text}
                           for i, (line, level, text) in enumerate(headings, 1)])
        if argument.isdigit() and 1 <= int(argument) <= len(headings):
            self.presentation.document(self.current_file, scroll_to=headings[int(argument) - 1][0])
        else:
            rows = ["%02d  %s%s  [%d]" % (index, "  " * (level - 1), text, line)
                    for index, (line, level, text) in enumerate(headings, 1)]
            self.presentation.console(self._t("outline"), rows or [self._t("no_results")])

    def _navigate_hit(self, direction):
        hits = self._hit_lines()
        if not hits:
            return
        if direction > 0:
            target = next((line for line in hits if line > self.presentation.line), hits[0])
        else:
            target = next((line for line in reversed(hits) if line < self.presentation.line), hits[-1])
        if self.presentation.view == "source":
            self.presentation.scroll(target)
        else:
            self.presentation.source(self.current_file, scroll_to=target)

    def _command_next(self, _argument):
        self._navigate_hit(1)

    def _command_prev(self, _argument):
        self._navigate_hit(-1)

    def _command_animation(self, argument):
        if argument and argument not in ("on", "off"):
            self.presentation.notice("[!] " + self._t("usage") + " /animation on|off", "warning")
            return
        if argument in ("on", "off"):
            self.animations = argument == "on"
            config = self._load_config()
            config["animations"] = self.animations
            self._save_config(config)
        self.presentation.notice("[OK] " + self._t("animation") + ("on" if self.animations else "off"), "success")

    def _command_tasks(self, _argument):
        if self._needs_workspace():
            return
        rows, tasks = [], []
        for path in self._workspace_files():
            content = self._read_file(path)
            if content is None:
                continue
            for number, line in enumerate(content.splitlines(), 1):
                match = re.match(r"\s*- \[ \] (.+)", line)
                if match:
                    rows.append(path.relative_to(self.workspace).as_posix() + "  |  " + match.group(1))
                    tasks.append({'path': str(path), 'line': number, 'text': match.group(1)})
        self.presentation.data(tasks=tasks)
        self.presentation.console(self._t("tasks"), rows or [self._t("no_results")])

    def _command_check(self, argument):
        if not self._require_note() or not argument.isdigit():
            return
        if not self._ensure_buffer_for_current():
            return
        content = self._read_file(self.current_file)
        if content is None:
            return
        index, seen, lines = int(argument), 0, content.splitlines(True)
        for position, line in enumerate(lines):
            if re.match(r"\s*- \[[ x]\] ", line):
                seen += 1
                if seen == index:
                    lines[position] = line.replace("[ ]", "[x]", 1) if "[ ]" in line else line.replace("[x]", "[ ]", 1)
                    dirty = set(self.dirty_lines) | {position + 1}
                    self.buffer.mutate("".join(lines), dirty)
                    self._refresh_document(scroll_to=position + 1)
                    self.presentation.notice("[OK] " + self._t("unsaved_pending"), "success")
                    return
        self.presentation.notice("[!] " + self._t("task_not_found"), "warning")

    def _command_tag(self, argument):
        action, _, value = argument.partition(" ")
        if action == "find" and value:
            self._show_tagged(value)
        elif not self._require_note():
            return
        elif action == "add" and value:
            if not self._ensure_buffer_for_current():
                return
            content = self._read_file(self.current_file)
            if content is None:
                return
            tags = sorted(set(self._tags_in(content) + self._split_tags(value)))
            had_tags = bool(re.search(r"^<!-- markprompt-tags: .*? -->", content, flags=re.MULTILINE))
            stripped = re.sub(r"^<!-- markprompt-tags: .*? -->\n?", "", content, flags=re.MULTILINE)
            new_text = "<!-- markprompt-tags: " + ", ".join(tags) + " -->\n" + stripped
            # Inserting the first tag line shifts every existing dirty line by one.
            shift = 0 if had_tags else 1
            dirty = {n + shift for n in self.dirty_lines}
            self.buffer.mutate(new_text, dirty)
            self._refresh_document()
            self.presentation.notice("[OK] tags: " + ", ".join(tags) + " · " + self._t("unsaved_pending"), "success")
        else:
            content = self._read_file(self.current_file)
            if content is not None:
                self.presentation.console(self._t("tags") + "  " + self.current_file.name, [", ".join(self._tags_in(content)) or self._t("none")])

    def _command_tags(self, _argument):
        if self._needs_workspace():
            return
        counts = {}
        for path in self._workspace_files():
            content = self._read_file(path)
            if content is None:
                continue
            for tag in self._tags_in(content):
                counts[tag] = counts.get(tag, 0) + 1
        rows = [tag + "  " + str(count) for tag, count in sorted(counts.items())]
        self.presentation.data(tags=[{'name': name, 'count': count} for name, count in sorted(counts.items())])
        self.presentation.console(self._t("tags"), rows or [self._t("no_results")])

    def _command_archive(self, _argument):
        self._move_current("archive", self._t("archived"))

    def _command_trash(self, _argument):
        self._move_current("trash", self._t("trashed"))

    def _command_restore(self, name):
        if self._needs_workspace() or not name:
            return
        try:
            target = self.storage.files.restore(self.workspace, name)
        except StorageError as error:
            self._report_storage_error(error)
            return
        self.presentation.document(target)
        self.presentation.notice('[OK] ' + self._t('restored') + ' ' + target.name, 'success')

    def _command_reveal(self, _argument):
        if self._require_note():
            try:
                system_open(self.current_file.parent)
            except OSError as e:
                self.presentation.notice("[ERR] " + self._t("open_dir_failed") + str(e), "error")

    # External links and files.

    def _scan_links(self):
        """Collect Markdown link and image targets from the editing copy.

        Group nonempty targets by source line, preserving their order within each line.
        """
        text = self.buffer_text
        if not text:
            return []
        scanned = []
        for lineno, line in enumerate(text.splitlines(), start=1):
            targets = [m.group(1).strip() for m in EXT_LINK_RE.finditer(line)]
            targets = [t for t in targets if t]
            if targets:
                scanned.append((lineno, targets))
        return scanned

    def _ext_resolve(self, target):
        raw = target.strip().strip('"')
        if not raw:
            return None
        if EXT_URL_RE.match(raw):
            return raw
        try:
            return self.storage.paths.external_file(raw, self.workspace, self.storage.paths.platform_limit)
        except StorageError as error:
            self._report_storage_error(error)
            return None

    def _ext_open(self, target):
        resolved = self._ext_resolve(target)
        if resolved is None:
            return
        try:
            system_open(resolved)
        except OSError as e:
            self.presentation.notice("[ERR] " + self._t("ext_open_failed") + str(e), "error")

    def _render_ext_list(self, scanned):
        """List document links grouped by source line."""
        title = self._t("ext_links") + " (" + self.current_file.name + ")"
        if not scanned:
            self.presentation.console(title, [self._t("ext_no_links")])
            return
        digits = max(3, len(str(len(self.buffer_text.splitlines()))))
        lines = []
        for lineno, targets in scanned:
            for index, target in enumerate(targets, start=1):
                lines.append("[%0*d] %d) %s" % (digits, lineno, index, target))
        self.presentation.console(title, lines)

    def _render_ext_line_list(self, lineno, targets):
        """Number the links on a source line so the user can choose one."""
        title = (self._t("ext_line_title") % lineno) + " (%d)" % len(targets)
        lines = ["  %d) %s" % (index, target) for index, target in enumerate(targets, start=1)]
        self.presentation.console(title, lines)

    def _external_links(self, argument):
        """Handle legacy /ext arguments: list links, open a numbered link, or open a target."""
        if not self._require_note():
            return
        scanned = self._scan_links()
        arg = argument.strip()
        if not arg:
            self._render_ext_list(scanned)
            return
        first, _, rest = arg.partition(" ")
        rest = rest.strip()
        if first.isdigit():
            targets = dict(scanned).get(int(first), [])
            if not targets:
                self.presentation.notice("[!] " + (self._t("ext_no_link") % int(first)), "warning")
                return
            if not rest:
                if len(targets) == 1:
                    self._ext_open(targets[0])
                else:
                    self._render_ext_line_list(int(first), targets)
                return
            if not rest.isdigit():
                self.presentation.notice("[!] " + self._t("usage") + " /ext <line> <index>", "warning")
                return
            index = int(rest)
            if index < 1 or index > len(targets):
                self.presentation.notice("[!] " + self._t("ext_link_index_range"), "warning")
                return
            self._ext_open(targets[index - 1])
            return
        # Treat the full argument as one path, including spaces.
        self._ext_open(arg)

    def _command_import(self, argument):
        if self._needs_workspace() or not argument:
            return
        try:
            target = self.storage.files.import_note(Path(argument.strip('"')), self.workspace)
        except StorageError as error:
            self._report_storage_error(error)
            return
        self.presentation.document(target)
        self.presentation.notice('[OK] ' + self._t('imported') + ' ' + target.name, 'success')

    def _command_export(self, argument):
        if not self._require_note() or argument.lower() != 'txt':
            self.presentation.notice('[!] ' + self._t('usage') + ' /export txt', 'warning')
            return
        content = self._read_file(self.current_file)
        if content is None:
            return
        try:
            document = self.storage.export_text(self.current_file.with_suffix('.txt'), self._plain_text(content))
        except StorageError as error:
            self._report_storage_error(error)
            return
        self.presentation.data(path=str(document.path))
        self.presentation.notice('[OK] ' + self._t('exported') + ' ' + document.path.name, 'success')

    def _command_clear(self, _argument):
        self.presentation.clear()

    def _command_quit(self, _argument):
        # Use the same unsaved-changes check as the window close button.
        self.presentation.close()

    def _command_lang(self, argument):
        if argument in TEXT:
            self.language = argument
            self.presentation.apply_theme(self.presentation.theme)
            self.presentation.prompt()
        else:
            self.presentation.console('LANGUAGE', ['en', 'zh'])

    def _command_theme(self, argument):
        argument = argument.strip().lower()
        if argument in THEMES:
            self.presentation.apply_theme(argument)
            self.presentation.notice("[OK] " + (self._t("theme_switched") % argument), "success")
            return
        if argument:
            self.presentation.notice("[!] " + (self._t("theme_invalid") % argument), "warning")
        lines = [("* " if name == self.presentation.theme else "  ") + name for name in THEMES]
        self.presentation.console(self._t("theme_current") % self.presentation.theme, lines)

    def _command_dark(self, _argument):
        self._command_theme("dark")

    def _command_light(self, _argument):
        self._command_theme("light")

    def _command_help(self, _argument):
        self._show_help()


    def _move_current(self, folder, label):
        if not self._require_note() or self._needs_workspace():
            return
        if not self._flush_buffer():
            return
        try:
            target = self.storage.files.move_to(self.current_file, self.workspace, folder)
        except StorageError as error:
            self._report_storage_error(error)
            return
        self.current_file = None
        self._set_buffer(None, None, dirty_lines=None, dirty=False)
        self._clear_mode_stack()
        self.navigation.clear()
        self.presentation.directory(self.current_dir)
        self.presentation.data(path=str(target))
        self.presentation.notice('[OK] ' + label + ' ' + target.name, 'success')

    def _show_tagged(self, tag):
        if self._needs_workspace():
            return
        rows = []
        for path in self._workspace_files():
            content = self._read_file(path)
            if content is None:
                continue
            if tag in self._tags_in(content):
                rows.append(str(path.relative_to(self.workspace)))
        self.presentation.console(self._t("tagged") + "  " + tag, rows or [self._t("no_results")])

    def _show_tree(self):
        """List at most two directory levels and cap the number of children shown."""
        lines = []
        try:
            for child in self.storage.files.list_directory(self.current_dir):
                lines.append(("[D] " if child.is_dir() else "[M] " if child.suffix.lower() == ".md" else "[F] ") + child.name)
                if child.is_dir():
                    for grandchild in self.storage.files.list_directory(child)[:TREE_MAX_CHILDREN]:
                        prefix = "└─ [D] " if grandchild.is_dir() else "└─ [M] " if grandchild.suffix.lower() == ".md" else "└─ [F] "
                        lines.append("  " + prefix + grandchild.name)
        except StorageError as error:
            lines.append("[ERR] " + str(error))
        self.presentation.console("TREE  " + str(self.current_dir), lines or [self._t("empty_folder")])

    def _show_help(self):
        rows = ['/%s %s  ·  %s' % (spec.name, spec.usage, spec.description(self.language))
                for spec in REGISTRY.specs.values()]
        self.presentation.console(self._t('commands'), rows)
