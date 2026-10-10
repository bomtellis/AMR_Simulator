import unittest

from amr_sim_models import Task
from simulator import Simulation
from tests import test_dropoff_zones as fixtures


class LtnHandoffRegressions(unittest.TestCase):
    def test_direct_department_delivery_uses_enabled_out_of_hours_fallback(self):
        sim = Simulation(fixtures.DropoffZoneTests._config())
        task = Task('DIRECT', 'Store', 'Ward', 'Trolley')
        task.requires_staff = True
        task.department_id = 'D1'
        task.staff_use_custom_working_hours = True
        task.staff_working_hours = {
            'mon': {'enabled': True, 'start_time': '06:00', 'end_time': '14:00'}
        }
        task.staff_department_fallback_enabled = True
        assignment = sim._assign_staff_for_handling(task, 60, 180)
        self.assertTrue(assignment.get('department_staff_fallback'))
        self.assertEqual(60, assignment['start_time'])
        self.assertEqual(240, assignment['finish_time'])
        self.assertFalse(assignment['tracked_staff_resource'])

    def test_direct_department_delivery_without_fallback_waits_for_primary_hours(self):
        sim = Simulation(fixtures.DropoffZoneTests._config())
        task = Task('DIRECT', 'Store', 'Ward', 'Trolley')
        task.requires_staff = True
        task.department_id = 'D1'
        task.staff_use_custom_working_hours = True
        task.staff_working_hours = {
            'mon': {'enabled': True, 'start_time': '06:00', 'end_time': '14:00'}
        }
        task.staff_department_fallback_enabled = False
        assignment = sim._assign_staff_for_handling(task, 60, 180)
        self.assertFalse(assignment.get('department_staff_fallback', False))
        self.assertGreaterEqual(assignment['start_time'], 6 * 3600)

    def test_staff_return_preserves_incoming_robot_bay_reservation(self):
        config = fixtures.DropoffZoneTests._config()
        zone = next(loc for loc in config['locations'] if loc['name'] == 'Zone')
        zone['inventory_spaces'].append({
            'name': 'Spare', 'length_m': 2, 'width_m': 2, 'height_m': 2,
        })
        sim = Simulation(config)
        incoming = Task('INCOMING', 'Store', 'Zone', 'Trolley')
        sim.schedule_task_release(incoming)
        spaces = sim.inventory_spaces_by_location['Zone']
        spaces[0]['reserved_by_task'] = incoming.id
        outbound = Task('OUTBOUND', 'Store', 'Zone', 'Trolley')
        outbound.dropoff_zone = 'Zone'
        outbound.final_destination = 'Ward'
        outbound.assigned_inventory_space = spaces[0]['name']
        returning = Task('RETURN', 'Zone', 'Store', 'Empty Trolley')
        sim._complete_dropoff_zone_handoff(outbound, returning, {}, 60)
        self.assertEqual('INCOMING', spaces[0]['reserved_by_task'])
        self.assertFalse(spaces[0]['occupied'])
        self.assertTrue(spaces[1]['occupied'])
        self.assertEqual(returning.payload_instance_id, spaces[1]['payload_instance_id'])


if __name__ == '__main__':
    unittest.main()
