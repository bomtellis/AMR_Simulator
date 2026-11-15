"""Independent navigation, linking, pagination and asynchronous ownership checks."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThreadPool
from amr_route_analysis import compare_runs, load_analysis
from tests import test_route_analysis as fixtures
from tests.test_route_analysis import forced_rows, segment, complete, analysis_config
from visualiser.route_analysis_panel import RouteAnalysisPanel, PagedTable


class AnalysisUiTests(unittest.TestCase):
    log = fixtures.RouteAnalysisTests.log

    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.panel=RouteAnalysisPanel()
        self.a=load_analysis(self.log(forced_rows()),drawings=False)
        self.b=load_analysis(self.log([segment('corridor','A','B',0),complete(2)],config=analysis_config(False),name='b.csv'),drawings=False)
        self.panel.runs.update(A=self.a,B=self.b)
        self.panel.populate_filters()
        self.panel.result=compare_runs(self.a,self.b)
        self.panel.render()

    def tearDown(self):
        self.panel.shutdown()
        QThreadPool.globalInstance().waitForDone(10000)
        self.panel.close();self.panel.deleteLater();self.app.processEvents()
        self.temp.cleanup()

    def test_two_runs_and_independent_journey_selections(self):
        self.assertEqual(5,self.panel.tabs.count())
        self.panel.select_leg('A',self.a.legs[0])
        self.assertIsNone(self.panel.selected_legs['B'])
        self.panel.select_leg('B',self.b.legs[0])
        self.assertEqual(self.a.legs[0],self.panel.maps['A'].leg)
        self.assertEqual(self.b.legs[0],self.panel.maps['B'].leg)
        self.assertEqual(5,len(self.panel.evidence.records))

    def test_group_selection_reveals_individual_paths(self):
        item=self.panel.route_tree.topLevelItem(0)
        self.assertGreater(item.childCount(),0)
        self.panel.select_group(item.child(0))
        self.assertEqual(1,len(self.panel.trips['A'].records))
        self.assertEqual(0,len(self.panel.trips['B'].records))

    def test_stale_load_cannot_replace_current_run(self):
        self.panel.tokens['A']=4
        self.panel._finished('A',3,self.b,'')
        self.assertIs(self.a,self.panel.runs['A'])

    def test_failed_load_retains_previous_result(self):
        self.panel._finished('A',0,None,'Invalid saved evidence')
        self.assertIs(self.a,self.panel.runs['A'])
        self.assertIn('retained',self.panel.status.text())

    def test_pagination_keeps_every_record(self):
        table=PagedTable('test',['Value'])
        rows=list(range(751));table.set_records(rows,[[r] for r in rows])
        self.assertEqual(250,table.model.rowCount())
        table.change_page(3)
        self.assertEqual([[750]],table.model.rows)
        self.assertEqual(751,len(table.records))
        table.deleteLater()

    def test_chart_selection_updates_shared_filter(self):
        with patch.object(self.panel,'refresh_comparison') as refresh:
            self.panel.select_pair(0,2)
            self.assertEqual(2,self.panel.filter_value().lift_destination_floor)
            refresh.assert_called_once()
        with patch.object(self.panel,'refresh_comparison'):
            self.panel.select_lift('L')
            self.assertEqual('L',self.panel.filter_value().lift)

    def test_route_map_uses_recorded_geometry_without_recomputing(self):
        self.panel.select_leg('A',self.a.legs[0])
        self.assertGreater(len(self.panel.maps['A'].view.scene().items()),0)
        self.assertGreater(len(self.panel.maps['A'].sequence.scene().items()),0)
        self.assertIn('Satisfied',self.panel.maps['A'].notes.text())

    def test_workspace_fits_smaller_window_with_scrollable_views(self):
        self.panel.resize(1100,750)
        self.panel.show();self.app.processEvents()
        self.assertLessEqual(self.panel.height(),750)
        self.assertLessEqual(self.panel.width(),1100)

    def test_manually_typed_source_takes_priority_over_old_combo_data(self):
        choice=self.panel.sources['A'];choice.addItem('Saved run','old-path')
        choice.setCurrentIndex(choice.count()-1);choice.setEditText('new-path')
        self.assertEqual('new-path',self.panel.selected_source('A'))

    def test_heatmaps_share_floor_axes_and_colour_scale(self):
        left,right=self.panel.heatmaps['A'],self.panel.heatmaps['B']
        self.assertEqual(left.floors,right.floors)
        self.assertEqual(left.rowCount(),right.rowCount())


class WorkspaceIntegrationTests(unittest.TestCase):
    from tests.test_corridor_editing import CorridorEditingUiTests
    setUpClass = CorridorEditingUiTests.__dict__['setUpClass']
    setUp = CorridorEditingUiTests.setUp
    tearDown = CorridorEditingUiTests.tearDown

    def test_main_navigation_opens_independent_workspace(self):
        self.editor.workspace.activate('route_analysis')
        self.assertEqual('route_analysis',self.editor.workspace.stage)
        self.assertIs(self.editor.route_analysis_panel,self.editor.workspace.stack.currentWidget())
        self.assertEqual('Lift & Route Analysis',self.editor.workspace.items['route_analysis'].text(0))
        self.assertFalse(hasattr(self.editor,'report_panel'))
