import copy
import unittest

from amr_contingency_inputs import default_settings, initial_settings, validate_settings
from tests.test_generation_reference import grouped_config


class ContingencyPrefillTests(unittest.TestCase):
    def test_native_group_overrides_supply_payloads_and_base(self):
        c=grouped_config()
        c['payloads'].append(dict(name='Return box',weight_kg=3,length_m=.4,width_m=.3,height_m=.2))
        group=c['task_generation']['categories']['stores']['department_groups'][0]['payload']
        group.update(pickup_location='B',return_payload='Return box',return_enabled=True)
        c['task_generation']['staff_config']=dict(walking_speed_m_per_sec=.9,default_handling_minutes=7,
            shift_patterns={'none':dict(start_time='22:00',end_time='06:00',days_active=['mon','tue'])})
        c['building']['load_unload_time_sec']=12
        before=copy.deepcopy(c)
        s=default_settings(c);p=s['profiles']['stores']
        self.assertEqual(['Box','Return box'],p['payloads'])
        self.assertEqual('B',p['base']);self.assertEqual('B',s['shifts']['shared_base'])
        self.assertEqual(2,p['capacity_count']);self.assertEqual(20,p['capacity_kg'])
        self.assertAlmostEqual(2.6,p['length_m'])
        self.assertEqual(.9,p['loaded_speed_mps']);self.assertEqual(7,p['handling_minutes'])
        self.assertEqual(12,p['pickup_seconds']);self.assertEqual(12,p['unload_seconds'])
        self.assertEqual([8],s['shifts']['lengths_hours']);self.assertEqual(['mon','tue'],s['shifts']['days'])
        s['shifts']['confirmed']=True
        validate_settings(c,s)
        self.assertEqual(before,c)

    def test_disabled_service_is_inspectable_but_not_selected(self):
        c=grouped_config()
        c['task_generation']['categories']['ssd']=dict(enabled=False,payload='')
        s=default_settings(c)
        self.assertIn('ssd',s['profiles']);self.assertEqual(['stores'],s['services'])

    def test_legacy_blank_profile_is_filled_without_changing_saved_project(self):
        c=grouped_config();saved=default_settings(c)
        saved['profiles']['stores'].update(capacity_count=0,capacity_kg=0,length_m=0,width_m=0,height_m=0,
            base='',pickup_seconds=0,unload_seconds=0)
        saved['shifts']['shared_base']=''
        c['human_contingency']=dict(settings=saved)
        before=copy.deepcopy(c);result=initial_settings(c)
        self.assertEqual(2,result['profiles']['stores']['capacity_count'])
        self.assertEqual('A',result['profiles']['stores']['base'])
        self.assertEqual('A',result['shifts']['shared_base'])
        self.assertEqual(before,c)

    def test_completed_saved_edits_are_retained(self):
        c=grouped_config();saved=default_settings(c)
        saved['profiles']['stores'].update(capacity_count=3,capacity_kg=85,length_m=2,width_m=.8,
            height_m=1.7,base='B',pickup_seconds=0,unload_seconds=0)
        saved['shifts']['confirmed']=True
        c['human_contingency']=dict(settings=saved)
        self.assertEqual(saved,initial_settings(c))


if __name__=='__main__':unittest.main()
