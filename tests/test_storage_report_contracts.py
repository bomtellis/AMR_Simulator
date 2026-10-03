"""Independent nominal storage-capacity expectations across report and simulator."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd
from simulator import Simulation
from visualiser.models import JsonStore
from tests.test_engineering_reference import reference_config
from report.amr_report_analysis import (Context, load_location_catalog, load_payload_dimensions,
                                       build_dropoff_zone_peak_occupancy)


class StorageReportContractTests(unittest.TestCase):
    def config(self, bays):
        cfg = reference_config()
        cfg['locations'][1]['inventory_spaces'] = bays
        cfg['departments'] = [dict(id='W', name='Ward', floor=0, task_generation_locations={
            'Stores': {'dropoff_zone_locations': ['B']}})]
        return cfg

    def catalog(self, cfg):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'project.json'
            path.write_text(json.dumps(cfg), encoding='utf-8')
            return load_location_catalog(path), load_payload_dimensions(path)

    def peak(self, cfg, payload_names):
        catalog, payloads = self.catalog(cfg)
        events = pd.DataFrame([dict(_event_time=pd.Timestamp('2026-01-01'),
            _event_text='location_payload_enter', to_location='B', payload=name,
            payload_instance_id=f'P{index}') for index, name in enumerate(payload_names)])
        peaks = pd.DataFrame([dict(location='B', peak_payload_count=len(payload_names),
                                  peak_area_used_m2=0, peak_volume_m3=0)])
        return build_dropoff_zone_peak_occupancy(events, Context(cols={}, has_datetime=True,
            time_col='_event_time'), catalog, peaks, payloads)[0].iloc[0]

    def test_amr_bays_are_excluded_from_payload_capacity_and_area(self):
        bays = [dict(name='Payload', length=2, width=1, height=2,
                     points=[dict(dx=0, dy=0), dict(dx=2, dy=0), dict(dx=2, dy=1), dict(dx=0, dy=1)]),
                dict(name='Robot', length_m=4, width_m=4, height_m=4,
                     payload_slots=[dict(amr='R')],
                     points=[dict(dx=0, dy=0), dict(dx=4, dy=0), dict(dx=4, dy=4), dict(dx=0, dy=4)])]
        cfg = self.config(bays)
        row = self.catalog(cfg)[0].set_index('location').loc['B']
        self.assertEqual(1, row.inventory_spaces_current)
        self.assertEqual(2, row.inventory_area_m2)
        self.assertEqual(['Payload'], [s['name'] for s in row.inventory_space_definitions])
        peak = self.peak(cfg, ['Box', 'Box'])
        self.assertEqual((1, 1), (peak.configured_spaces, peak.space_shortfall_at_peak))

    def test_alias_zero_inference_height_and_default_name_match_runtime(self):
        cfg = self.config([dict(length=99, length_m='0', width=3, height=2,
            points=[dict(dx=0, dy=0), dict(dx=4, dy=0), dict(dx=0, dy=2)])])
        for data in (cfg, JsonStore(cfg).data):
            actual = self.catalog(data)[0].set_index('location').loc['B'].inventory_space_definitions[0]
            expected = Simulation(data).inventory_spaces_by_location['B'][0]
            self.assertEqual('Space 1', actual['name'])
            self.assertEqual((4, 3, 2), tuple(actual[k] for k in ('length_m', 'width_m', 'height_m')))
            self.assertEqual(tuple(expected[k] for k in ('length_m', 'width_m', 'height_m')),
                             tuple(actual[k] for k in ('length_m', 'width_m', 'height_m')))

    def test_mixed_coordinate_bay_has_four_by_three_envelope_everywhere(self):
        # B is at (6,8); absolute (10,8) is local (4,0).
        cfg = self.config([dict(points=[dict(dx=0, dy=0), dict(x=10, y=8), dict(dx=0, dy=3)])])
        for data in (cfg, JsonStore(cfg).data):
            bay = Simulation(data).inventory_spaces_by_location['B'][0]
            self.assertEqual((4, 3), (bay['length_m'], bay['width_m']))
            row = self.catalog(data)[0].set_index('location').loc['B']
            self.assertEqual((4, 3), tuple(row.inventory_space_definitions[0][k] for k in ('length_m', 'width_m')))
            self.assertEqual(6, row.inventory_area_m2)

    def test_payload_size_units_and_inferred_height_match_runtime(self):
        cfg = self.config([dict(length=2, width=2, payload_slots=[dict(payload='Cube')])])
        cfg['payloads'].append(dict(name='Cube', weight_kg=1, size_units=1.5))
        catalog, payloads = self.catalog(cfg)
        cube = payloads.set_index('payload').loc['Cube']
        self.assertEqual((1.5, 1.5, 1.5), (cube.payload_length_m, cube.payload_width_m, cube.payload_height_m))
        self.assertEqual(1.5, catalog.set_index('location').loc['B'].inventory_space_definitions[0]['height_m'])
        self.assertEqual(0, self.peak(cfg, ['Cube']).space_shortfall_at_peak)

    def test_explicit_blank_modern_amr_alias_keeps_payload_bay(self):
        cfg = self.config([dict(length_m=2, width_m=2, payload_slots=[dict(amr='R', amr_type='', payload='Box')])])
        self.assertEqual(1, self.catalog(cfg)[0].set_index('location').loc['B'].inventory_spaces_current)
        self.assertEqual(0, self.peak(cfg, ['Box']).space_shortfall_at_peak)

    def test_fixed_parent_payload_and_flexible_precedence(self):
        cfg = self.config([dict(length_m=2, width_m=2, height_m=2, payload='Other', flexible=False, flexible_payloads=True)])
        cfg['payloads'].append(dict(name='Other', weight_kg=1, size_units=1))
        for flexible, expected in ((False, 1), (True, 0)):
            cfg['locations'][1]['inventory_spaces'][0]['flexible'] = flexible
            self.assertEqual(expected, self.peak(cfg, ['Box']).space_shortfall_at_peak)
            sim = Simulation(cfg)
            self.assertEqual(not expected, sim._inventory_space_can_fit_payload(
                sim.inventory_spaces_by_location['B'][0], sim.payloads['Box']))

    def test_matching_does_not_greedily_waste_only_compatible_bay(self):
        cfg = self.config([dict(length_m=2, width_m=2, height_m=2),
            dict(length_m=1, width_m=.7, height_m=1)])
        cfg['payloads'].append(dict(name='Large', weight_kg=1, size_units=2))
        peak = self.peak(cfg, ['Box', 'Large'])
        self.assertEqual((0, 0), (peak.free_spaces_at_peak, peak.space_shortfall_at_peak))

    def test_all_amr_bays_cannot_fall_back_to_count_only_payload_capacity(self):
        cfg = self.config([dict(stores_amr=True, length_m=5, width_m=5, height_m=5)])
        peak = self.peak(cfg, ['Box'])
        self.assertEqual((0, 1), (peak.configured_spaces, peak.space_shortfall_at_peak))

    def test_missing_dimensions_are_labelled_count_only(self):
        cfg = self.config([dict(length_m=.1, width_m=.1, height_m=.1)])
        known = self.peak(cfg, ['Box'])
        unknown = self.peak(cfg, ['Unrecorded payload'])
        self.assertEqual(1, known.space_shortfall_at_peak)
        self.assertEqual('Nominal compatible dimensions', known.capacity_basis)
        self.assertIn('Count only', unknown.capacity_basis)

    def test_rotated_fit_height_and_tolerance_match_independent_limits(self):
        cfg = self.config([dict(length_m=.7, width_m=1, height_m=1)])
        for width, height, shortfall in ((.7, 1, 0), (.7000005, 1, 0), (.700002, 1, 1), (.7, 1.000002, 1)):
            cfg['payloads'][0].update(width_m=width, height_m=height)
            self.assertEqual(shortfall, self.peak(cfg, ['Box']).space_shortfall_at_peak)
            sim = Simulation(cfg)
            self.assertEqual(not shortfall, sim._inventory_space_can_fit_payload(
                sim.inventory_spaces_by_location['B'][0], sim.payloads['Box']))

    def test_coordinate_conversion_overflow_blocks_raw_and_editor(self):
        cfg = self.config([dict(points=[dict(dx=1e308, dy=0)])])
        cfg['locations'][1]['x'] = 1e308
        before = copy.deepcopy(cfg)
        for consumer in (JsonStore, Simulation):
            with self.assertRaises(ValueError):
                consumer(cfg)
        self.assertEqual(before, cfg)

    def test_shared_bay_dimensions_apply_to_fleet_and_editor_checks(self):
        from amr_fleet_allocation import configured_fleet_bay_plan
        cfg = self.config([dict(stores_amr=True, has_charger=True, height_m=2,
            points=[dict(dx=0, dy=0), dict(x=10, y=8), dict(dx=0, dy=3)])])
        cfg['building']['charge_locations'] = ['B']
        cfg['amrs'][0].update(length_m=5, width_m=4)
        # Correct 4x3 bay cannot fit the 5x4 robot; old mixed coordinates yielded 10x8.
        for data in (cfg, JsonStore(cfg).data):
            self.assertEqual({}, configured_fleet_bay_plan(data)['assignment'])
            store = JsonStore(data)
            self.assertFalse(store._inventory_space_accepts_amr_type(
                data['locations'][1], data['locations'][1]['inventory_spaces'][0], data['amrs'][0]))
