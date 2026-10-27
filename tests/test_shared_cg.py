"""Shared-animation recognition contract; no APP/device connection.

Actor/controller/state identities come from serialized game references.
The 0.6 observer payload below is synthetic until the user's live re-test.
"""
from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest

from sinisistar_dglab.cg_playback import CgRegistry, REGISTRY, describe_game_cg
from sinisistar_dglab.pulse import PulsePlanner
from sinisistar_dglab.ovc_plan import OvcPlanner
from sinisistar_dglab.backend import WAVES
from sinisistar_dglab.simulation import initial_profile, VIBRATION_WAVES

ROOT=Path(__file__).resolve().parents[1]
ACTOR='Root/Character/Pig_Continue/Root'


def shared_state(state='Continue_Breast'):
    s=deepcopy(json.loads((ROOT/'tests/fixtures/cg-realplay-0.5.1.json').read_text(encoding='utf-8'))[0]['state'])
    s.update(sampled_at=10,scene_id=166,scene='Road_2_2_Livestock',hp=None,player=0,valid=False,
             loading=False,paused=False,bound=False,gacha=dict(active=False),event_playing=True)
    s['cg_playback']=dict(schema=1,available=True,shared_animation_schema=1,
        event=dict(object=777,type='HierarchyEventPlayer',path='Root/Event/UnlistedRealGameEntry/Main',playing=True),
        shared_animators=[dict(object=888,available=True,active=True,source='active_event_receiver',owner_event_object=777,
            receiver_object=999,controller='Continue',path=ACTOR,layer=0,matched_names=[state],normalized_time=.4,length=2.)])
    return s


class SharedCg(unittest.TestCase):
    def test_extracted_gallery_actor_and_state_are_shared_across_unlisted_game_entries(self):
        for name in ('Continue_Idle','Continue_Idle2','Continue_Breast','Continue_Breast2','Continue_Hold','Continue_Hold_Breast2'):
            s=shared_state(name);info=describe_game_cg(s,10)
            self.assertTrue(info['recognized'],name)
            self.assertEqual(info['kind'],'SharedAnimator')
            self.assertEqual(info['evidence'],'shared_actor_controller_state')
            self.assertFalse(info['hp_used'])
            self.assertTrue(all(166 in REGISTRY.rows[key]['scene_ids'] for key in info['ids']))

    def test_current_pigpen_branches_no_longer_require_matching_the_gallery_entry_path(self):
        for branch,name in (('StartGacha','Continue_Idle'),('Failed Breast','Continue_Breast'),
                            ('Failed SuperBreast','Continue_Breast2'),('ToGoScene','Continue_Idle2')):
            s=shared_state(name)
            s['cg_playback']['event']['path']='Root/Event/BossBattle/Continue/Boot/'+branch
            self.assertTrue(describe_game_cg(s,10)['recognized'],branch)

    def test_four_channels_use_the_cg_policy_without_hp_or_struggle(self):
        p=initial_profile();p['cg_detection_mode']='playback_only'
        for hp in (None,0,1,100):
            s=shared_state();s['hp']=None if hp is None else dict(current=hp,max=100)
            for cls,route,waves in ((PulsePlanner,'pulse',WAVES),(OvcPlanner,'vibration',VIBRATION_WAVES)):
                out=cls().update(s,p,waves,now=10,enabled=True)
                self.assertTrue(all(out[route+'_stream'].values()),(hp,route,out['reason']))
                self.assertFalse(out['hp_used'])
                self.assertEqual(len(out['active']),1)  # Matching several takes never multiplies strength.

    def test_actor_controller_state_layer_and_current_event_ownership_are_required(self):
        changes=[('controller','Other'),('path','Root/Character/Other/Root'),('matched_names',['Walk']),
                 ('layer',1),('owner_event_object',123),('source','cached'),('available',False),
                 ('active',False),('object',0),('normalized_time',float('nan')),('length',0)]
        for field,value in changes:
            s=shared_state();s['cg_playback']['shared_animators'][0][field]=value
            self.assertFalse(describe_game_cg(s,10)['recognized'],field)

    def test_stopped_loading_stale_foreign_scene_and_missing_schema_never_authorize(self):
        for case in ('event_stopped','manager_stopped','loading','stale','scene','schema','fingerprint'):
            s=shared_state()
            if case=='event_stopped':s['cg_playback']['event']['playing']=False
            if case=='manager_stopped':s['event_playing']=False
            if case=='loading':s['loading']=True
            if case=='stale':s['sampled_at']=9
            if case=='scene':s.update(scene_id=43,scene='Monastery_Tutorial1')
            if case=='schema':s['cg_playback']['shared_animation_schema']=0
            if case=='fingerprint':s['fingerprint']='other'
            self.assertFalse(describe_game_cg(s,10)['recognized'],case)

    def test_ordinary_pose_in_a_dialogue_is_not_enough_even_if_present_in_a_cg(self):
        registry=CgRegistry(dict(takes=[dict(id='test',take='TestCG',scene_ids=[166],scene_names=['Road_2_2_Livestock'],
            events=[],queue=[],shared_animations=[dict(controller='Continue',path=ACTOR,layer=0,states=['Idle','Walk','Attack_2','CG_Hold'])])]))
        for name in ('Idle','Walk','Attack_2'):
            self.assertFalse(describe_game_cg(shared_state(name),10,registry)['recognized'],name)
        self.assertTrue(describe_game_cg(shared_state('CG_Hold'),10,registry)['recognized'])

    def test_explicit_any_layer_command_still_requires_a_real_active_layer(self):
        registry=CgRegistry(dict(takes=[dict(id='any-layer',take='Hold',scene_ids=[166],scene_names=['Road_2_2_Livestock'],events=[],
            shared_animations=[dict(controller='Continue',path=ACTOR,layer=-1,states=['Continue_Hold'])])]))
        s=shared_state('Continue_Hold');s['cg_playback']['shared_animators'][0]['layer']=2
        self.assertTrue(describe_game_cg(s,10,registry)['recognized'])
        s['cg_playback']['shared_animators'][0]['layer']=-1
        self.assertFalse(describe_game_cg(s,10,registry)['recognized'])

    def test_playback_end_and_pause_stop_both_routes_without_holding_an_old_animation(self):
        p=initial_profile();p['cg_detection_mode']='playback_only'
        for cls,route,waves in ((PulsePlanner,'pulse',WAVES),(OvcPlanner,'vibration',VIBRATION_WAVES)):
            planner=cls();s=shared_state()
            self.assertTrue(any(planner.update(s,p,waves,now=10,enabled=True)[route+'_stream'].values()))
            s['sampled_at']=10.1;s['paused']=True
            self.assertFalse(any(planner.update(s,p,waves,now=10.1,enabled=True)[route+'_stream'].values()))
            s['sampled_at']=10.2;s['paused']=False;s['cg_playback']['event']['playing']=False
            self.assertFalse(any(planner.update(s,p,waves,now=10.2,enabled=True)[route+'_stream'].values()))

    def test_shared_evidence_is_preferred_but_old_explicit_cg_references_still_work(self):
        s=shared_state();row=next(r for r in REGISTRY.rows.values() if r['take']=='Continue_Breast' and 166 in r['scene_ids'])
        event=next(e for e in row['events'] if e['role']=='main')
        s['cg_playback']['event'].update(type=event['type'],path=event['path'])
        self.assertEqual(describe_game_cg(s,10)['kind'],'SharedAnimator')
        s['cg_playback'].pop('shared_animators')
        self.assertEqual(describe_game_cg(s,10)['kind'],'EventPlayer')

    def test_shared_detection_never_overrides_disabled_feedback_or_emergency(self):
        p=initial_profile();p['cg_detection_mode']='playback_only';p['rules']['defeat_hold']['enabled']=False
        for cls,route,waves in ((PulsePlanner,'pulse',WAVES),(OvcPlanner,'vibration',VIBRATION_WAVES)):
            self.assertFalse(any(cls().update(shared_state(),p,waves,now=10,enabled=True)[route+'_stream'].values()))
            p['rules']['defeat_hold']['enabled']=True
            self.assertFalse(any(cls().update(shared_state(),p,waves,now=10,enabled=True,emergency=True)[route+'_stream'].values()))
            p['rules']['defeat_hold']['enabled']=False

    def test_hybrid_ordinary_hp_loss_remains_a_short_damage_burst_not_cg(self):
        p=initial_profile();p['cg_detection_mode']='hybrid'
        p['rules']['hp_loss'].update(enabled=True,duration=1.5,pulse_enabled=True,vibration_enabled=True)
        for cls,route,waves in ((PulsePlanner,'pulse',WAVES),(OvcPlanner,'vibration',VIBRATION_WAVES)):
            for remaining in (80,1):
                planner=cls();s=shared_state()
                s.update(valid=True,player=123,event_playing=False,flow={},hp=dict(current=100,max=100))
                # Even leftover CG Animator fields cannot authorize without a live event.
                planner.update(s,p,waves,now=10,enabled=True)
                s.update(sampled_at=10.1,sample_id=101,hp=dict(current=remaining,max=100))
                self.assertFalse(describe_game_cg(s,10.1)['recognized'])
                out=planner.update(s,p,waves,now=10.1,enabled=True)
                self.assertEqual([r['key'] for r in out['active']],['hp_loss'])
                self.assertNotIn('cg_age',out)
                s.update(sampled_at=11.7,sample_id=102)
                ended=planner.update(s,p,waves,now=11.7,enabled=True)
                self.assertFalse(any(ended[route+'_stream'].values()))

    def test_real_test_launcher_preserves_settings_and_never_selects_a_mock_backend(self):
        from sinisistar_dglab.cg_test_profile import prepare_live
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as tmp:
            root=Path(tmp);(root/'artifacts').mkdir();profile=initial_profile()
            profile['pulse_cap_a']=37;profile['cg']['routes']['pulse']['A']['ramp_seconds']=83
            original=json.dumps(dict(simulation=profile,connections=dict(pulse_backend='v4',v4_port=9997,auto_enable=False),custom_waves=[dict(key='my_wave')]))
            source=root/'artifacts/settings.json';source.write_text(original,encoding='utf-8')
            target,backend=prepare_live(root);data=json.loads(target.read_text(encoding='utf-8'))
            self.assertEqual(backend,'v4');self.assertEqual(data['connections']['v4_port'],9997)
            self.assertFalse(data['connections']['auto_enable']);self.assertEqual(data['simulation']['pulse_cap_a'],37)
            self.assertEqual(data['simulation']['cg']['routes']['pulse']['A']['ramp_seconds'],83)
            self.assertEqual(data['custom_waves'],[dict(key='my_wave')])
            self.assertEqual(data['simulation']['cg_detection_mode'],'playback_only')
            self.assertEqual(source.read_text(encoding='utf-8'),original)

    def test_live_launcher_uses_the_last_real_session_but_rejects_an_outside_pointer(self):
        from sinisistar_dglab.cg_test_profile import prepare_live
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as tmp:
            root=Path(tmp);previous=root/'artifacts/previous';previous.mkdir(parents=True)
            profile=initial_profile();profile['vibration_cap_a']=47
            (previous/'settings.json').write_text(json.dumps(dict(simulation=profile,connections=dict(pulse_backend='v3'))),encoding='utf-8')
            (root/'artifacts/cg-realplay-current.json').write_text(json.dumps(dict(directory=str(previous))),encoding='utf-8')
            target,backend=prepare_live(root)
            self.assertEqual(backend,'v3');self.assertEqual(json.loads(target.read_text(encoding='utf-8'))['simulation']['vibration_cap_a'],47)
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as tmp:
            root=Path(tmp);(root/'artifacts').mkdir()
            (root/'artifacts/cg-realplay-current.json').write_text(json.dumps(dict(directory=str(ROOT/'artifacts'))),encoding='utf-8')
            target,backend=prepare_live(root)
            self.assertEqual(backend,'v4');self.assertEqual(json.loads(target.read_text(encoding='utf-8'))['simulation']['cg_detection_mode'],'playback_only')


if __name__=='__main__':unittest.main()
