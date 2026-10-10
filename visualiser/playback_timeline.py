"""Viewport-sized timeline caching for playback on the editor's GUI thread."""
from bisect import bisect_left, bisect_right
from datetime import timedelta
import math

from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QScrollArea
from amr_sim_visualiser_pyside6 import AmrTimelineWidget


class PlaybackTimelineWidget(AmrTimelineWidget):
    def __init__(self, parent=None):
        self._block_index = []
        self._background_key = None
        self._background = None
        super().__init__(parent)
        self.min_lane_width = 300

    def set_data(self, timeline_data, start_time, end_time, current_time):
        self._block_index = []
        for lane in timeline_data or []:
            blocks = sorted(lane['blocks'], key=lambda b: (b['start'], b['end']))
            starts, ends = [], []
            last_end = float('-inf')
            for block in blocks:
                starts.append((block['start'] - start_time).total_seconds())
                last_end = max(last_end, (block['end'] - start_time).total_seconds())
                ends.append(last_end)
            self._block_index.append((blocks, starts, ends))
        self._background_key = None
        super().set_data(timeline_data, start_time, end_time, current_time)

    def _viewport_rect(self):
        parent = self.parent()
        while parent is not None and not isinstance(parent, QScrollArea):
            parent = parent.parent()
        if parent is None:
            return self.rect()
        origin = self.mapFrom(parent.viewport(), QPoint(0, 0))
        return QRect(origin, parent.viewport().size()).intersected(self.rect())

    def set_current_time(self, value):
        previous = self.current_time
        self.current_time = value
        if value == previous:
            return
        # Repaint only the old/new playhead strips; task bars remain cached.
        for when in (previous, value):
            if when is not None:
                self.update(QRect(int(self._time_to_x(when)) - 3, 0, 7, self.height()))

    def _visible_blocks(self, row, left, right):
        blocks, starts, ends = self._block_index[row]
        pixels_per_second = self._usable_width() / max(1e-9, self._timeline_seconds())
        first = (left - self.left_pad - 3) / pixels_per_second
        last = (right - self.left_pad + 3) / pixels_per_second
        lo = bisect_left(ends, first)
        hi = bisect_right(starts, last)
        for index in range(lo, hi):
            block = blocks[index]
            if (block['end'] - self.start_time).total_seconds() >= first:
                yield block

    def _paint_background(self, painter, visible):
        painter.fillRect(visible, QColor('#101010'))
        painter.setFont(self.font())
        if not self.timeline_data or not self.start_time or not self.end_time or self.end_time <= self.start_time:
            painter.setPen(QColor('#cfcfcf'))
            painter.drawText(visible, Qt.AlignCenter, 'No timeline data')
            return
        axis_y = self.top_pad - 12
        lane_end = int(self.left_pad + self._usable_width())
        left = max(self.left_pad, visible.left())
        right = min(lane_end, visible.right())
        painter.setPen(QColor('#8a8a8a'))
        painter.drawLine(left, axis_y, right, axis_y)
        step = self._nice_tick_seconds()
        first_time = self._x_to_time(max(self.left_pad, left - 70))
        last_time = self._x_to_time(right + 70)
        epoch = math.ceil(first_time.timestamp() / step) * step
        tick = self.start_time.fromtimestamp(epoch, tz=self.start_time.tzinfo)
        while tick <= last_time:
            x = int(self._time_to_x(tick))
            painter.setPen(QColor('#2a2a2a'))
            painter.drawLine(x, axis_y - 4, x, visible.bottom())
            painter.setPen(QColor('#d7d7d7'))
            painter.drawText(x - 42, 22, 84, 30, Qt.AlignCenter, self._format_tick_label(tick, step))
            tick += timedelta(seconds=step)
        first_row = max(0, (visible.top() - self.top_pad) // self.row_height)
        last_row = min(len(self.timeline_data), (visible.bottom() - self.top_pad) // self.row_height + 1)
        metrics = painter.fontMetrics()
        for row in range(first_row, last_row):
            y = self.top_pad + row * self.row_height
            painter.setPen(QColor('#2a2a2a'))
            painter.drawLine(left, y + 22, right, y + 22)
            for block in self._visible_blocks(row, left, right):
                x1 = self._time_to_x(block['start'])
                x2 = max(x1 + 2, self._time_to_x(block['end']))
                rect = QRectF(x1, y + 7, x2 - x1, 16)
                painter.fillRect(rect, QColor(block['color']))
                painter.setPen(QColor('#000000'))
                painter.drawRect(rect)
                label = str(block.get('label', '')).strip()
                if label and rect.width() >= 54:
                    text = metrics.elidedText(label, Qt.ElideRight, max(1, int(rect.width()) - 8))
                    painter.setPen(QColor('#ffffff'))
                    painter.drawText(rect.adjusted(4, 0, -4, 0), Qt.AlignLeft | Qt.AlignVCenter, text)
        # Date boundaries are only drawn within the viewport, including their labels.
        day = first_time.replace(hour=0, minute=0, second=0, microsecond=0)
        if day < self.start_time:
            day += timedelta(days=1)
        while day <= last_time:
            x = int(self._time_to_x(day))
            painter.setPen(QPen(QColor('#555555'), 1))
            painter.drawLine(x, axis_y - 20, x, visible.bottom())
            painter.setPen(QColor('#ffffff'))
            painter.drawText(x + 4, 4, 120, 18, Qt.AlignLeft | Qt.AlignVCenter, day.strftime('%a %d %b'))
            day += timedelta(days=1)
        scroll_x = self._visible_scroll_x()
        painter.fillRect(QRectF(scroll_x, visible.top(), self.label_column_width, visible.height()), QColor('#151515'))
        painter.setPen(QColor('#ffffff'))
        painter.drawText(scroll_x + 8, 22, self.label_column_width - 16, 24, Qt.AlignLeft | Qt.AlignVCenter, 'AMR')
        for row in range(first_row, last_row):
            painter.setPen(QColor('#d7d7d7'))
            painter.drawText(scroll_x + 8, self.top_pad + row * self.row_height + 3,
                             self.label_column_width - 16, 24, Qt.AlignLeft | Qt.AlignVCenter,
                             str(self.timeline_data[row]['amr_id']))

    def paintEvent(self, event):
        visible = self._viewport_rect()
        if visible.isEmpty():
            return
        ratio = self.devicePixelRatioF()
        key = (visible.x(), visible.y(), visible.width(), visible.height(),
               self.seconds_per_pixel, self.width(), self.height(), ratio, self.font().toString())
        if key != self._background_key:
            pixmap = QPixmap(math.ceil(visible.width() * ratio), math.ceil(visible.height() * ratio))
            pixmap.setDevicePixelRatio(ratio)
            painter = QPainter(pixmap)
            try:
                painter.translate(-visible.left(), -visible.top())
                self._paint_background(painter, visible)
            finally:
                painter.end()
            self._background, self._background_key = pixmap, key
        painter = QPainter(self)
        painter.drawPixmap(visible.topLeft(), self._background)
        if self.current_time is not None:
            x = int(self._time_to_x(self.current_time))
            if x > self._visible_scroll_x() + self.label_column_width:
                painter.setPen(QPen(QColor('#ffffff'), 2))
                painter.drawLine(x, self.top_pad - 28, x, self.height() - self.bottom_pad + 4)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        parent = self.parent()
        while parent is not None and not hasattr(parent, 'finish_seek'):
            parent = parent.parent()
        if parent is not None:
            parent.finish_seek()
