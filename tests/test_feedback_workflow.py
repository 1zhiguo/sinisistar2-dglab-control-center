"""User-facing queue, automatic custom saves and independent channel filters."""
from copy import deepcopy
from pathlib import Path
import json,tempfile,unittest
from PySide6.QtGui import QGuiApplication
from sinisistar_dglab.backend import Backend,WAVES,ROOT
from sinisistar_dglab.cg_policy import progressive_queue,queue_scale,select_wave
from sinisistar_dglab.quick_policy import current_values,edit_current
from sinisistar_dglab.simulation import initial_profile,sanitize_profile,VIBRATION_WAVES,wave_samples
from sinisistar_dglab.pulse import PulsePlanner
from sinisistar_dglab.ovc_plan import OvcPlanner
from sinisistar_dglab.cg_policy import make_cg

def state(t=10,**changes):
    s=dict(source='bepinex',live=True,valid=False,player=0,pid=1,session='workflow',scene_id=4,scene='Road_2_1_GO',
        sampled_at=t,sample_id=int(t*100),paused=False,loading=False,time_scale=1,event_playing=True,hp=dict(current=1,max=110),abnormals=[],
        flow=dict(valid=True,playing=True,paused=False,name='Main',group='Event',type='HierarchyEventPlayer'))
    s.update(changes);return s

def profile():
    p=initial_profile();p['cg']=make_cg(p['rules']['defeat_hold'],inherit=False)
    p['cg']['rule'].update(pulse_channel='AB',vibration_channel='AB')
    return p

class FeedbackWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.qt=QGuiApplication.instance() or QGuiApplication([])

    def test_five_existing_waves_exact_minute_increasing_mean_amplitude_and_loop(self):
        p=profile()
        for route,catalog in [('pulse',WAVES),('vibration',VIBRATION_WAVES)]:
            q=progressive_queue(route,catalog);o=p['cg']['routes'][route];o.update(mode='sequence',queue=q)
            self.assertEqual(sum(x['seconds'] for x in q),60);self.assertEqual(len(set(x['wave'] for x in q)),5)
            means=[];waves={w['key']:w for w in catalog}
            for i,item in enumerate(q):
                self.assertEqual(select_wave(o,p['cg']['rule'],route,12*i,'seed')[0],item['wave'])
                means.append(sum(wave_samples(waves[item['wave']],j*.025,item['period'],30)[0][0] for j in range(480))/480*item['scale'])
            self.assertEqual(means,sorted(means));self.assertEqual(queue_scale(o,route,60,'seed'),.35)

    def test_queue_scale_applies_to_all_four_wire_samples_including_boundary(self):
        p=profile();p['cg']['rule'].update(pulse_strength_a=40,pulse_start_strength_a=40)
        p['cg']['routes']['pulse'].update(mode='sequence',ramp_mode='constant',queue=[dict(wave='flat',seconds=.15,period=1,scale=.25),dict(wave='flat',seconds=1,period=1,scale=.75)])
        waves=WAVES+[dict(key='flat',points=[1]*16)]
        planner=PulsePlanner();planner.update(state(),p,waves,now=10,enabled=True)
        out=planner.update(state(10.125),p,waves,now=10.125,enabled=True)
        self.assertEqual(out['pulse_stream']['A']['samples'],[10,30,30,30])
        self.assertEqual(sanitize_profile(p)['cg']['routes']['pulse']['A']['queue'][0]['scale'],.25)

    def test_each_route_channel_filters_cg_and_normal_zero_hp(self):
        for route,planner,catalog in [('pulse',PulsePlanner,WAVES),('vibration',OvcPlanner,VIBRATION_WAVES)]:
            p=profile();p['channel_feedback']={r:{'A':'both','B':'both'} for r in ('pulse','vibration')}
            p['channel_feedback'][route]={'A':'damage','B':'cg'}
            out=planner().update(state(),p,catalog,now=10,enabled=True)
            self.assertIsNone(out[route+'_stream']['A']);self.assertIsNotNone(out[route+'_stream']['B'])
            normal=state(valid=True,player=2,scene_id=3,scene='Road_2_1',hp=dict(current=0,max=110),flow={},event_playing=False)
            out=planner().update(normal,p,catalog,now=10,enabled=True)
            self.assertIsNone(out[route+'_stream']['A']);self.assertIsNotNone(out[route+'_stream']['B'])

    def test_damage_side_filters_grabbing_damage_and_status_without_enabling_rules(self):
        p=initial_profile();p['channel_feedback']['pulse']={'A':'cg','B':'damage'}
        p['rules']['grab_hold']['pulse_channel']='AB';p['abnormals']['Poison'].update(enabled=True,pulse_channel='AB')
        s=state(valid=True,player=2,scene='Road_2_1',hp=dict(current=60,max=100),flow={},event_playing=False,bound=True,binder='Zombie',abnormals=[dict(name='Poison',level=1)])
        planner=PulsePlanner();out=planner.update(s,p,WAVES,now=10,enabled=True)
        self.assertIsNone(out['pulse_stream']['A']);self.assertIsNotNone(out['pulse_stream']['B'])
        p['rules']['grab_hold']['enabled']=False;p['abnormals']['Poison']['enabled']=False
        out=planner.update(state(10.1,**{k:v for k,v in s.items() if k not in ('sampled_at','sample_id')}),p,WAVES,now=10.1,enabled=True)
        self.assertIsNone(out['pulse_stream']['A']);self.assertIsNone(out['pulse_stream']['B'])

    def test_legacy_migration_preserves_output_and_rejects_invalid_scope_and_scale(self):
        p=sanitize_profile({'channel_feedback':{'pulse':{'A':'invalid','B':'cg'}},'cg':{'routes':{'pulse':{'queue':[dict(wave='pulse',scale=float('nan')),dict(wave='pulse',scale=99)]}}}})
        self.assertEqual(p['channel_feedback']['pulse'],{'A':'both','B':'cg'})
        self.assertEqual([x['scale'] for x in p['cg']['routes']['pulse']['A']['queue']],[1,1])

    def test_edit_current_changes_only_targeted_parameters_and_preserves_tiers(self):
        p=initial_profile();p['rules']['break']['vibration_wave']='ovc_beat';p['cg']['inherit_death']=False
        before=deepcopy(p);q=edit_current(p,{'pulse_damage':27})
        self.assertEqual(q['rules']['hp_loss']['pulse_strength'],27);self.assertEqual(q['rules']['grab_hp_loss']['pulse_strength'],27)
        self.assertEqual(q['cg'],before['cg']);self.assertEqual(q['rules']['break'],before['rules']['break'])
        self.assertEqual(q['quick_presets'],before['quick_presets']);self.assertEqual(q['quick_active_preset'],'')
        self.assertEqual(current_values(q)['pulse_damage'],27)

    def test_auto_save_reload_custom_ranges_limits_and_channel_scope(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as tmp:
            b=Backend(offline=True,settings=Path(tmp)/'settings.json');b._timer.stop()
            try:
                tiers=deepcopy(b.quickPolicy['presets']);b._armed=b._ovc_armed=True
                b.editQuickValue('pulse_cap',43);b.editQuickRange('pulse_death',12,39);b.editQuickValue('death_mode','timed')
                b.setChannelFeedback('vibration','B','cg')
                self.assertFalse(b._armed);self.assertFalse(b._ovc_armed);self.assertEqual(b.quickPolicy['active'],'')
                self.assertEqual([c['limit'] for c in b.channels],[43,43]);self.assertEqual(b.quickPolicy['presets'],tiers)
                self.assertEqual(json.loads(b.settings.read_text(encoding='utf-8'))['simulation']['quick_active_preset'],'')
                other=Backend(offline=True,settings=b.settings);other._timer.stop()
                try:
                    self.assertEqual(other.quickPolicy['current']['pulse_death_b'],39)
                    self.assertEqual(other.quickPolicy['current']['pulse_death_start_b'],12)
                    self.assertEqual(other.quickPolicy['current']['death_mode'],'timed')
                    self.assertEqual(other.simulationSettings['channel_feedback']['vibration']['B'],'cg')
                    other.applyQuickPreset('low');self.assertEqual(other.quickPolicy['current']['pulse_cap'],30)
                    self.assertEqual(other.simulationSettings['channel_feedback']['vibration']['B'],'cg')
                finally:other.shutdown()
            finally:b.shutdown()

    def test_loading_progressive_queue_keeps_ranges_caps_and_death_but_disarms(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as tmp:
            b=Backend(offline=True,settings=Path(tmp)/'settings.json');b._timer.stop()
            try:
                before=deepcopy(b._sim_profile);b._armed=b._ovc_armed=True;b.applyProgressiveCgQueue('both')
                self.assertFalse(b._armed);self.assertFalse(b._ovc_armed)
                self.assertEqual(b._sim_profile['rules'],before['rules']);self.assertEqual(b.channels[0]['limit'],60)
                for route in ('pulse','vibration'):
                    self.assertEqual(b.cgSettings['rule'][route+'_strength_a'],before['rules']['defeat_hold'][route+'_strength_a'])
                    self.assertEqual(b.cgSettings['rule'][route+'_ramp_seconds'],60)
                    self.assertEqual(sum(x['seconds'] for x in b.cgSettings['routes'][route]['A']['queue']),60)
            finally:b.shutdown()

    def test_unrelated_quick_edits_preserve_independently_lowered_device_limits(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as tmp:
            b=Backend(offline=True,settings=Path(tmp)/'settings.json');b._timer.stop()
            try:
                for channel in b._channels:channel['limit']=13
                b._ovc_limits={'A':20,'B':30};b.editQuickValue('pulse_damage',22)
                self.assertEqual([c['limit'] for c in b.channels],[13,13]);self.assertEqual(b.ovcLimits,{'A':20,'B':30})
                b.editQuickValue('pulse_cap',40)
                self.assertEqual([c['limit'] for c in b.channels],[40,40]);self.assertEqual(b.ovcLimits,{'A':20,'B':30})
            finally:b.shutdown()
