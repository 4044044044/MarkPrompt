"""Read the visible viewport and input state on the Tk thread."""
from tkinter import TclError

from markprompt_core.automation.snapshot import TEXT_LIMIT, excerpt, section


class SnapshotSurface:
    def _snapshot_surface(self):
        dialog = getattr(self, '_snapshot_dialog_kind', None)
        if dialog or self._drop_open_pending:
            pending = {'kind': dialog or 'unsaved_navigation', 'choices': ['save', 'discard', 'cancel'],
                       'id': getattr(self, '_snapshot_dialog_id', None)}
        elif self.confirm_mode:
            pending = {'kind': 'overwrite', 'choices': ['y', 'n'], 'target': self.states.confirmation.payload.get('target'),
                       'id': self.states.confirmation.payload.get('id')}
        else:
            pending = None
        result = {'kind': 'gui', 'pending': pending, 'position_line': self._last_position_line,
                  'viewport': {'available': False}, 'selection': None,
                  'input': excerpt(self.entry.get('1.0', 'end-1c')), 'focus': None,
                  'header': self.header.cget('text'), 'theme_name': self.theme_name,
                  'theme': dict(self.theme), 'fonts': {'mono': self.mono.actual(), 'ui': self.ui_font.actual()},
                  'console': section({'text': str(text)[:1000], 'truncated': len(str(text)) > 1000}
                                     for text, _tag in reversed(self.console_history)),
                  'document_render_complete': bool(self.current_file) and self._rendered_text == self.buffer_text,
                  'rendered_image_instances': len(self.output.image_names())}
        focus = self.focus_get()
        result['focus'] = 'command' if focus == self.entry else 'document' if focus == self.output else 'other' if focus else None
        try:
            ranges = self.output.tag_ranges('sel')
            if ranges:
                first, last = map(str, ranges)
                result['selection'] = {'coordinate_space': 'tk_rendered_text', 'start': first, 'end': last,
                                       'content': excerpt(self.output.get(first, last))}
            width, height = self.output.winfo_width(), self.output.winfo_height()
            if width <= 1 or height <= 1:
                return result
            top, bottom = self.output.index('@0,0'), self.output.index('@%d,%d' % (width - 1, height - 1))
            stop = self.output.index(bottom + '+1c')
            visible = self.output.get(top, stop)
            source_lines = []
            if self.current_file:
                if self.renderer.source_mode:
                    source_lines = list(range(max(1, int(top.split('.')[0])), min(self.renderer.line_count, int(bottom.split('.')[0])) + 1))
                else:
                    mark = self.output.mark_previous(top + '+1c')
                    while mark and not mark.startswith('source-line-'):
                        mark = self.output.mark_previous(mark)
                    if mark and self.output.index(mark).split('.')[0] == top.split('.')[0]:
                        source_lines.append(int(mark[len('source-line-'):]))
                    for _kind, name, _index in self.output.dump(top, stop, mark=True):
                        if name.startswith('source-line-'):
                            source_lines.append(int(name[len('source-line-'):]))
            source_lines = sorted(set(source_lines))
            result.update(position_line=source_lines[0] if source_lines else result['position_line'])
            result['viewport'] = {'available': True, 'mapped': bool(self.output.winfo_ismapped()), 'width': width, 'height': height,
                                  'top_index': top, 'bottom_index': bottom, 'scroll': list(self.output.yview()),
                                  'source_lines': source_lines, 'rendered_text': visible[:TEXT_LIMIT],
                                  'text_truncated': len(visible) > TEXT_LIMIT}
        except TclError as error:
            result['viewport'] = {'available': False, 'reason': str(error)}
        return result
