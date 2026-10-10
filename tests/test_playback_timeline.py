"""Timeline redraw cost depends on the viewport, not the full saved workload."""
from datetime import datetime, timedelta
import unittest
from unittest.mock import patch

from tests import test_corridor_editing as editing
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QScrollArea
from playback_timeline import PlaybackTimelineWidget


class PlaybackTimelineTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)

    def setUp(self):
        self.start = datetime(2026, 1, 5)
        self.end = self.start + timedelta(days=7)
        self.scroll = QScrollArea()
        self.scroll.resize(900, 260)
        self.timeline = PlaybackTimelineWidget()
        self.scroll.setWidget(self.timeline)
        self.lanes = [dict(amr_id=f'R-{row}', blocks=[dict(
            start=self.start + timedelta(seconds=i * 600),
            end=self.start + timedelta(seconds=i * 600 + 60),
            color='#3498db', label=f'Task-{i}') for i in range(1000)]) for row in range(24)]
        self.timeline.set_data(self.lanes, self.start, self.end, self.start)
        self.scroll.show()
        self.app.processEvents()

    def tearDown(self):
        self.scroll.close()
        self.scroll.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_playhead_reuses_background_scroll_zoom_and_data_refresh_it(self):
        with patch.object(self.timeline, '_paint_background', wraps=self.timeline._paint_background) as paint:
            for seconds in range(10, 110, 10):
                self.timeline.set_current_time(self.start + timedelta(seconds=seconds))
                self.timeline.repaint(self.timeline._viewport_rect())
            paint.assert_not_called()
            self.scroll.horizontalScrollBar().setValue(1000)
            self.app.processEvents()
            self.assertGreater(paint.call_count, 0)
            before = paint.call_count
            self.timeline.set_zoom_seconds_per_pixel(8)
            self.app.processEvents()
            self.assertGreater(paint.call_count, before)
            before = paint.call_count
            self.timeline.set_data(self.lanes, self.start, self.end, self.start)
            self.timeline.repaint(self.timeline._viewport_rect())
            self.assertGreater(paint.call_count, before)
        cache = self.timeline._background
        self.assertLessEqual(cache.width(), self.scroll.viewport().width() * cache.devicePixelRatio() + 1)
        self.assertLessEqual(cache.height(), self.scroll.viewport().height() * cache.devicePixelRatio() + 1)

    def test_visible_block_lookup_retains_long_overlaps_and_instant_events(self):
        blocks = [dict(start=self.start, end=self.start + timedelta(seconds=1000), color='red'),
                  dict(start=self.start + timedelta(seconds=10), end=self.start + timedelta(seconds=20), color='blue'),
                  dict(start=self.start + timedelta(seconds=500), end=self.start + timedelta(seconds=500), color='green')]
        self.timeline.set_data([dict(amr_id='R', blocks=blocks)], self.start, self.end, self.start)
        x = self.timeline._time_to_x(self.start + timedelta(seconds=500))
        found = list(self.timeline._visible_blocks(0, x - 1, x + 1))
        self.assertEqual([blocks[0], blocks[2]], found)
        found = list(self.timeline._visible_blocks(0, 150, 1000))
        self.assertEqual(blocks, found)

    def test_zoomed_view_only_visits_a_small_part_of_each_lane(self):
        visible = self.timeline._viewport_rect()
        blocks = list(self.timeline._visible_blocks(0, visible.left(), visible.right()))
        self.assertLess(len(blocks), 10)
        self.assertEqual(1000, len(self.lanes[0]['blocks']))
