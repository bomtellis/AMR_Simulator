"""Equivalent bay encodings must agree on storage, charging and effective size."""
import copy
import os
from pathlib import Path
import sys
import unittest

from simulator import Simulation
from tests.test_engineering_reference import reference_config
from visualiser.models import JsonStore
from visualiser.project_checks import check_project


def bay_config(marker):
    cfg = reference_config()
    cfg['amrs'][0]['height_m'] = .5
    cfg['locations'][0]['inventory_spaces'] = [dict(name='Parking', length_m=2,
        width_m=2, height_m=2, has_charger=False, **marker)]
    return cfg


class InventoryClassificationTests(unittest.TestCase):
    def test_all_amr_markers_prevent_legacy_charging_fallback(self):
        markers = [dict(stores_amr=True), dict(space_type=' AMR '), dict(amr_type='R'),
                   dict(payload_slots=[dict(slot_type='amr')]),
                   dict(payload_slots=[dict(amr_type='R')]),
                   dict(payload_slots=[dict(slot_type='amr', amr='R')])]
        for marker in markers:
            cfg = bay_config(marker)
            for data in (cfg, JsonStore(cfg).data):
                with self.subTest(marker=marker, imported=data is not cfg):
                    sim = Simulation(data)
                    bay, = sim.inventory_spaces_by_location['A']
                    self.assertTrue(sim._space_is_amr_only(bay))
                    self.assertFalse(sim._inventory_space_can_fit_payload(bay, sim.payloads['Box']))
                    self.assertFalse(sim._amr_is_at_operational_charger(sim.amrs[0]))
                    self.assertEqual(0, sim._configured_charger_counts()['A'])

    def test_legacy_amr_alias_does_not_allow_other_types(self):
        cfg = bay_config(dict(payload_slots=[dict(slot_type='amr', amr='R')]))
        cfg['amrs'].append(dict(cfg['amrs'][0], id='Other'))
        for data in (cfg, JsonStore(cfg).data):
            sim = Simulation(data)
            bay, = sim.inventory_spaces_by_location['A']
            self.assertTrue(sim._inventory_space_accepts_amr(bay, sim.amrs[0]))
            self.assertFalse(sim._inventory_space_accepts_amr(bay, sim.amrs[1]))

    def test_editor_and_runtime_agree_on_parent_instance_and_union_restrictions(self):
        for marker in (dict(amr_type='R'), dict(amr_type='R-1'),
                       dict(payload_slots=[dict(amr_type='Other'), dict(amr_type='R')])):
            cfg = bay_config(marker)
            cfg['amrs'].append(dict(cfg['amrs'][0], id='Other'))
            store = JsonStore(cfg)
            sim = Simulation(cfg)
            bay, = sim.inventory_spaces_by_location['A']
            for index, robot_type in enumerate(cfg['amrs']):
                self.assertEqual(sim._inventory_space_accepts_amr(bay, sim.amrs[index]),
                    store._inventory_space_accepts_amr_type(store.get_location('A'),
                        store.get_location_inventory_spaces('A')[0], robot_type))

    def test_unknown_alias_and_type_tags_reject_instead_of_changing_class(self):
        for marker in (dict(space_type='amrr'), dict(payload_slots=[dict(slot_type='robot')]),
                       dict(payload_slots=[dict(slot_type='amr', amr='Typo')])):
            cfg = bay_config(marker)
            with self.subTest(marker=marker), self.assertRaises(ValueError):
                Simulation(cfg)
            self.assertTrue(any(f.severity == 'error' and f.code == 'INVENTORY_INPUT'
                                for f in check_project(cfg).findings))

    def test_modern_slot_reference_overrides_legacy_alias(self):
        cfg = bay_config(dict(payload_slots=[dict(slot_type='amr', amr_type='R', amr='Other')]))
        cfg['amrs'].append(dict(cfg['amrs'][0], id='Other'))
        sim = Simulation(cfg)
        bay, = sim.inventory_spaces_by_location['A']
        self.assertTrue(sim._inventory_space_accepts_amr(bay, sim.amrs[0]))
        self.assertFalse(sim._inventory_space_accepts_amr(bay, sim.amrs[1]))

    def test_zero_dimensions_infer_consistently_including_numeric_strings(self):
        for zero in (0, '0'):
            cfg = reference_config()
            cfg['locations'][1]['inventory_spaces'] = [dict(name='Bay', length_m=zero,
                width_m=zero, height_m=zero, points=[dict(dx=0,dy=0),dict(dx=2,dy=3)],
                payload_slots=[dict(payload='Box')])]
            for data in (cfg, JsonStore(cfg).data):
                sim = Simulation(data)
                bay, = sim.inventory_spaces_by_location['B']
                self.assertEqual((2,3,1), tuple(bay[k] for k in ('length_m','width_m','height_m')))
                report = check_project(data)
                self.assertFalse(any(f.severity == 'error' for f in report.findings))

    def test_zero_fallback_keeps_modern_precedence_and_other_dimensions_strict(self):
        cfg = reference_config()
        cfg['locations'][1]['inventory_spaces'] = [dict(name='Bay', length_m=0, length=99,
            width_m=0, width=99, height_m=1, points=[dict(dx=0,dy=0),dict(dx=2,dy=3)])]
        bay, = Simulation(cfg).inventory_spaces_by_location['B']
        self.assertEqual((2,3), (bay['length_m'], bay['width_m']))
        cfg['payloads'][0]['length_m'] = 0
        self.assertTrue(any(f.path == '/payloads/0/length_m' and f.severity == 'error'
                            for f in check_project(cfg).findings))
        with self.assertRaises(ValueError):
            Simulation(cfg)

    def test_editor_classifiers_share_case_and_legacy_alias_rules(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'visualiser'))
        from inventory_spaces_manager import is_amr_space
        from amr_inventory_inputs import inventory_space_is_amr
        for marker in (dict(space_type=' AMR '), dict(amr_type='R'),
                       dict(payload_slots=[dict(amr='R')])):
            self.assertTrue(is_amr_space(marker))
            self.assertTrue(inventory_space_is_amr(marker))

    def test_charger_flag_alone_does_not_convert_payload_bay(self):
        cfg = bay_config({})
        cfg['locations'][0]['inventory_spaces'][0]['has_charger'] = True
        sim = Simulation(cfg)
        bay, = sim.inventory_spaces_by_location['A']
        self.assertFalse(sim._space_is_amr_only(bay))
        self.assertTrue(sim._inventory_space_can_fit_payload(bay, sim.payloads['Box']))
        # The existing location-level legacy charger remains; the payload bay did not add one.
        self.assertEqual(1, sim._configured_charger_counts()['A'])
        self.assertTrue(any(f.code == 'INVENTORY_CHARGER_SCOPE' for f in check_project(cfg).findings))

    def test_zero_robot_quantity_needs_no_charging_bay(self):
        cfg = bay_config(dict(amr_type='R'))
        cfg['amrs'][0]['quantity'] = 0
        self.assertEqual([], JsonStore(cfg)._amr_charge_space_validation_errors())

    def test_finite_points_cannot_overflow_to_an_infinite_bay(self):
        cfg = reference_config()
        cfg['locations'][1]['inventory_spaces'] = [dict(name='Overflow',
            points=[dict(dx=-1e308,dy=0), dict(dx=1e308,dy=1)])]
        for consumer in (JsonStore, Simulation):
            with self.assertRaisesRegex(ValueError, 'resolved bay envelope'):
                consumer(cfg)

    def test_unresolved_plan_size_and_unbounded_height_are_visible_constraints(self):
        cfg = reference_config()
        cfg['locations'][1]['inventory_spaces'] = [dict(name='Unspecified')]
        before = copy.deepcopy(cfg)
        report = check_project(cfg)
        self.assertEqual(before, cfg)
        self.assertFalse(any(f.severity == 'error' for f in report.findings))
        self.assertTrue(any(f.code == 'INVENTORY_ENVELOPE' and f.severity == 'warning' for f in report.findings))
        self.assertTrue(any(f.code == 'INVENTORY_HEIGHT_SCOPE' for f in report.findings))
        report.acknowledge_warnings()
        self.assertTrue(report.can_run(cfg))
        bay, = Simulation(cfg).inventory_spaces_by_location['B']
        self.assertEqual((0,0,999999), tuple(bay[k] for k in ('length_m','width_m','height_m')))

    def test_mixed_markers_are_amr_only_with_an_explanation(self):
        cfg = bay_config(dict(stores_amr=True, payload_slots=[dict(payload='Box')]))
        sim = Simulation(cfg)
        bay, = sim.inventory_spaces_by_location['A']
        self.assertFalse(sim._inventory_space_can_fit_payload(bay, sim.payloads['Box']))
        self.assertTrue(any(f.code == 'INVENTORY_CLASSIFICATION' for f in check_project(cfg).findings))


if __name__ == '__main__':
    unittest.main()
