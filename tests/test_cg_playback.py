from copy import deepcopy
from pathlib import Path
import json,tempfile,unittest
from unittest.mock import patch
from sinisistar_dglab.cg_playback import REGISTRY,CgRegistry,describe_game_cg,valid_animator
from sinisistar_dglab.cg_coverage import CgCoverage
from sinisistar_dglab.gallery import describe_gallery
from sinisistar_dglab.gallery_policy import gallery_gate
from sinisistar_dglab.simulation import initial_profile,sanitize_profile
from sinisistar_dglab.pulse import PulsePlanner
from sinisistar_dglab.ovc_plan import OvcPlanner
from test_gallery_output import profile,state,WAVES
from cg_fixture import event_state,animator,ROW

class CgPlayback(unittest.TestCase):
    def test_recorded_bobel_session_survives_missing_animator_and_global_event_error(self):
        from sinisistar_dglab.backend import WAVES as PULSE_WAVES
        from sinisistar_dglab.simulation import VIBRATION_WAVES
        captured=json.loads((Path(__file__).parent/'fixtures/gallery-0.5.0-bobel-session.json').read_text(encoding='utf-8'))
        captured.update(live=True,sampled_at=10,scene='Gallery');captured['hp']=None
        captured['cg_playback']=dict(available=False,error='Destroyed previous EventPlayer')
        for cls,route,catalog in ((PulsePlanner,'pulse',PULSE_WAVES),(OvcPlanner,'vibration',VIBRATION_WAVES)):
            p=initial_profile();p['cg_detection_mode']='playback_only';planner=cls()
            out=planner.update(captured,p,catalog,now=10,enabled=True)
            self.assertFalse(out['hp_used']);self.assertTrue(all(out[route+'_stream'].values()))
            closed=deepcopy(captured);closed['gallery']['guide_open']=False;closed['sampled_at']=10.2
            self.assertFalse(any(planner.update(closed,p,catalog,now=10.2,enabled=True)[route+'_stream'].values()))

    def test_coverage_waits_for_new_loaded_take_and_maps_prefab_gallery(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'artifacts/test-temp') as tmp:
            journal=CgCoverage(Path(tmp)/'cg.json');s=json.loads((Path(__file__).parent/'fixtures/gallery-0.5.0-bobel-session.json').read_text(encoding='utf-8'))
            s.update(live=True,sampled_at=10,scene='Gallery');journal.observe(s,{}, {},{}, {},'playback_only',10)
            matches=journal.gallery_ids(s['gallery']);self.assertEqual(len(matches),1)
            self.assertTrue(journal.entries[matches[0]]['gallery_recognized'])
            previous_count=len(journal.entries);s['gallery'].update(selected_index_raw=2,take_count=2);s['sampled_at']=10.1
            journal.observe(s,{}, {},{}, {},'playback_only',10.1)
            pending=journal.entries['gallery:61:2'];self.assertFalse(pending.get('gallery_recognized',False))
            self.assertIn('latest_evidence',pending);self.assertGreaterEqual(len(journal.entries),previous_count)
    def game_profile(self):
        p=profile();p['cg']=deepcopy(p['gallery']);p['cg']['rule']['enabled']=True;p['cg_detection_mode']='playback_only';return p
    def test_catalog_is_reference_based_with_both_player_types(self):
        rows=list(REGISTRY.rows.values());self.assertEqual(len(rows),415)
        self.assertEqual(sum(r['play_type']==0 for r in rows),221)
        self.assertTrue(all(not r['runtime_verified'] and not r['errors'] for r in rows))
        catalog=json.loads((Path(__file__).parents[1]/'src/sinisistar_dglab/assets/cg-catalog.json').read_text(encoding='utf-8'))
        self.assertEqual(catalog['scene_inventory_missing'],0)

    def test_recorded_live_boss_sequences_work_without_hp_or_struggle(self):
        captured=json.loads((Path(__file__).parent/'fixtures/cg-realplay-0.5.1.json').read_text(encoding='utf-8'))
        p=self.game_profile()
        for case in captured:
            for hp in (None,0,1,100):
                s=deepcopy(case['state']);s.update(sampled_at=10,sample_id=100,paused=False,bound=False,gacha=dict(active=False))
                s['hp']=None if hp is None else dict(current=hp,max=100)
                self.assertEqual(describe_game_cg(s,10)['recognized'],case['expected'],(case['case'],hp))
                for cls,route in ((PulsePlanner,'pulse'),(OvcPlanner,'vibration')):
                    out=cls().update(s,p,WAVES,now=10,enabled=True)
                    self.assertEqual(any(out[route+'_stream'].values()),case['expected'],(case['case'],hp,route,out['reason']))
                    if case['expected']:self.assertFalse(out['hp_used'])

    def test_new_go_scene_mapping_still_requires_live_exact_player_identity(self):
        captured=json.loads((Path(__file__).parent/'fixtures/cg-realplay-0.5.1.json').read_text(encoding='utf-8'))
        source=next(r['state'] for r in captured if r['case']=='grave_main')
        for mutation in ('stopped','manager_stopped','wrong_type','wrong_path','ordinary_map','stale','loading','missing'):
            s=deepcopy(source);s['sampled_at']=10
            if mutation=='stopped':s['cg_playback']['event']['playing']=False
            if mutation=='manager_stopped':s['event_playing']=False
            if mutation=='wrong_type':s['cg_playback']['event']['type']='PlayableDirectorPlayer'
            if mutation=='wrong_path':s['cg_playback']['event']['path']='Root/Event/Other/Main'
            if mutation=='ordinary_map':s.update(scene_id=43,scene='Monastery_Tutorial1')
            if mutation=='stale':s['sampled_at']=9
            if mutation=='loading':s['loading']=True
            if mutation=='missing':s['cg_playback']['event']={}
            self.assertFalse(describe_game_cg(s,10)['recognized'],mutation)
    def test_both_routes_ignore_all_hp_values_and_player_validity(self):
        p=self.game_profile()
        for cls,route in ((PulsePlanner,'pulse'),(OvcPlanner,'vibration')):
            frames=[]
            for hp in (100,1,0,None):
                s=event_state();s['hp']=None if hp is None else dict(current=hp,max=100)
                out=cls().update(s,p,WAVES,now=10,enabled=True)
                self.assertFalse(out['hp_used']);self.assertTrue(out[route+'_stream']['A']);frames.append(out[route+'_stream'])
            self.assertTrue(all(frame==frames[0] for frame in frames))
    def test_ablation_blocks_hp_zero_one_damage_bound_and_status_without_playback(self):
        p=self.game_profile();p['abnormals']['Poison']['enabled']=True
        for cls,route in ((PulsePlanner,'pulse'),(OvcPlanner,'vibration')):
            engine=cls();s=event_state();engine.update(s,p,WAVES,now=10,enabled=True)
            for hp in (0,1,50):
                s=event_state(10.2);s.update(valid=True,player=2,bound=True,abnormals=[dict(name='Poison',level=5)])
                s['hp']['current']=hp;s['cg_playback']['event']['path']='Root/Event/OrdinaryDialogue/Main'
                s['feedback_evidence']=dict(locked_hp_active=True,same_hp_confirmed=True,same_hp_value=hp,same_hp_last_at=10.2)
                out=engine.update(s,p,WAVES,now=10.2,enabled=True)
                self.assertFalse(any(out[route+'_stream'].values()))
    def test_missing_stale_stopped_loading_wrong_scene_and_same_name_do_not_match(self):
        for change in ('old','stop','loading','scene','path','missing','fingerprint'):
            s=event_state()
            if change=='old':s['sampled_at']=0
            if change=='stop':s['cg_playback']['event']['playing']=False
            if change=='loading':s['loading']=True
            if change=='scene':s['scene_id']=43
            if change=='path':s['cg_playback']['event']['path']='Main'
            if change=='missing':s.pop('cg_playback')
            if change=='fingerprint':s['fingerprint']='other'
            self.assertFalse(describe_game_cg(s,10)['recognized'],change)
    def test_phase_changes_keep_ramp_pause_freezes_end_and_stale_stop(self):
        p=self.game_profile();engine=PulsePlanner();s=event_state()
        self.assertEqual(engine.update(s,p,WAVES,now=10,enabled=True)['cg_age'],0)
        s=event_state(10.4);out=engine.update(s,p,WAVES,now=10.4,enabled=True);self.assertAlmostEqual(out['cg_age'],.4)
        s=event_state(10.6);s['paused']=True;self.assertFalse(any(engine.update(s,p,WAVES,now=10.6,enabled=True)['pulse_stream'].values()))
        s=event_state(11);out=engine.update(s,p,WAVES,now=11,enabled=True);self.assertAlmostEqual(out['cg_age'],.4)
        s['sampled_at']=11.2;s['cg_playback']['event']['playing']=False
        self.assertFalse(any(engine.update(s,p,WAVES,now=11.2,enabled=True)['pulse_stream'].values()))
        self.assertFalse(any(engine.update(event_state(10),p,WAVES,now=12,enabled=True)['pulse_stream'].values()))
    def test_catalog_animator_requires_state_and_context_without_hp(self):
        row=dict(id='anim',take='Hold',scene_ids=[43],scene_names=['Monastery_Tutorial1'],queue=['Hold_Loop'],events=[],animator=dict(path=animator()['path'],controller='Enemy'))
        registry=CgRegistry(dict(takes=[row]));s=event_state();s.update(scene_id=43,scene='Monastery_Tutorial1',hp=None)
        s['cg_playback'].update(event={},animators=[animator()])
        self.assertTrue(describe_game_cg(s,10,registry)['recognized'])
        s['event_playing']=False;self.assertFalse(describe_game_cg(s,10,registry)['recognized'])
        s['bound']=True;self.assertTrue(describe_game_cg(s,10,registry)['recognized'])
        s['cg_playback']['animators'][0]['active']=False;self.assertFalse(describe_game_cg(s,10,registry)['recognized'])
    def test_gallery_animator_without_event_or_hp_uses_declared_state(self):
        p=profile();s=state(10);s.update(hp=None,event_playing=False,flow={})
        s['gallery'].update(play_type_raw=0,animator=animator());view=describe_gallery(s,10)
        self.assertTrue(view['playing']);self.assertEqual(view['playbackEvidence'],'declared_animator_state');self.assertEqual(gallery_gate(s,10,p['gallery']),'')
        for cls,route in ((PulsePlanner,'pulse'),(OvcPlanner,'vibration')):
            out=cls().update(s,p,WAVES,now=10,enabled=True);self.assertTrue(out[route+'_stream']['A'])
        s['gallery']['animator']['matched_names']=[];self.assertTrue(gallery_gate(s,10,p['gallery']))
    def test_take_session_fallback_requires_live_token_loaded_owner_and_selection(self):
        p=profile();s=state(10);s.update(hp=None,event_playing=False,flow={})
        s['gallery'].update(play_type_raw=0,take_object_active=True,take_token_active=True,owner_path='Root')
        self.assertEqual(describe_gallery(s,10)['playbackEvidence'],'loaded_take_session')
        self.assertEqual(gallery_gate(s,10,p['gallery']),'')
        for field,value in (('take_token_active',False),('take_object_active',False),('selected_index_raw',-1),('take_selected',False),('owner_path','')):
            other=deepcopy(s);other['gallery'][field]=value;self.assertTrue(gallery_gate(other,10,p['gallery']),field)
    def test_coverage_never_promotes_gallery_results_to_game_validation(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'artifacts/test-temp') as tmp:
            journal=CgCoverage(Path(tmp)/'cg.json');p=self.game_profile();s=event_state();engine=PulsePlanner()
            out=engine.update(s,p,WAVES,now=10,enabled=True)
            journal.observe(s,out,{},dict(A=dict(active=True,deadline=11)),{},'playback_only',10)
            self.assertFalse(journal.entries[ROW['id']]['sent'])
            s['sampled_at']=10.4;journal.observe(s,out,{},dict(A=dict(active=True,deadline=11)),{},'playback_only',10.4)
            self.assertEqual(journal.entries[ROW['id']]['sent'],['pulseA']);self.assertTrue(journal.save(force=True))
            row=next(r for r in journal.rows() if r['id']==ROW['id']);self.assertEqual(row['game'],'实战已识别');self.assertEqual(row['gallery'],'图鉴待验证')
    def test_detection_mode_persists_with_safe_default(self):
        self.assertEqual(initial_profile()['cg_detection_mode'],'hybrid')
        self.assertEqual(sanitize_profile(dict(cg_detection_mode='playback_only'))['cg_detection_mode'],'playback_only')
        self.assertEqual(sanitize_profile(dict(cg_detection_mode='bad'))['cg_detection_mode'],'hybrid')
    def test_all_catalog_takes_generate_without_hp_using_live_loaded_sessions(self):
        from sinisistar_dglab.backend import WAVES as PULSE_WAVES
        from sinisistar_dglab.simulation import VIBRATION_WAVES
        p=initial_profile();p['cg_detection_mode']='playback_only'
        for row in REGISTRY.rows.values():
            s=state(10);s.update(hp=None,event_playing=False,flow={})
            s['gallery'].update(play_type_raw=row['play_type'],take_name=row['take'],take_object_active=True,take_token_active=True,
                owner_path=row['owner'],target_scene_id=row['scene_ids'][0])
            for cls,route,catalog in ((PulsePlanner,'pulse',PULSE_WAVES),(OvcPlanner,'vibration',VIBRATION_WAVES)):
                out=cls().update(s,p,catalog,now=10,enabled=True)
                self.assertTrue(all(out[route+'_stream'].values()),(row['id'],route,out['reason']))
                self.assertFalse(out['hp_used'])
    def test_test_launcher_uses_current_strengths_without_writing_original_settings(self):
        from sinisistar_dglab.cg_test_profile import prepare
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'artifacts/test-temp') as tmp:
            root=Path(tmp);(root/'artifacts').mkdir();p=initial_profile();p['gallery']['rule']['pulse_strength_a']=37
            source=root/'artifacts/settings.json';original=json.dumps(dict(simulation=p,channels=[dict(key='A',limit=45,frequency=30)]))
            source.write_text(original,encoding='utf-8');target=prepare(root);data=json.loads(target.read_text(encoding='utf-8'))
            self.assertEqual(source.read_text(encoding='utf-8'),original)
            self.assertEqual(data['simulation']['gallery']['rule']['pulse_strength_a'],37)
            self.assertEqual(data['simulation']['channel_feedback']['vibration'],dict(A='both',B='both'))
            self.assertEqual(data['simulation']['cg_detection_mode'],'playback_only');self.assertTrue(data['connections']['auto_enable'])
