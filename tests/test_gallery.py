import json,unittest
from pathlib import Path
from sinisistar_dglab.gallery import GalleryPlayback,describe_gallery
from sinisistar_dglab.simulation import initial_profile,VIBRATION_WAVES
from sinisistar_dglab.backend import WAVES
from sinisistar_dglab.pulse import PulsePlanner
from sinisistar_dglab.ovc_plan import OvcPlanner

def sample(t=10,**changes):
    s=dict(source='bepinex',live=True,session='gallery-test',pid=1,player=0,valid=False,scene_id=10,scene='Gallery',
        sampled_at=t,sample_id=int(t*100),paused=False,loading=False,time_scale=1,event_playing=True,event_paused=False,
        hp=dict(current=120,max=120),abnormals=[],gacha=dict(active=True,value=0,threshold=20),
        flow=dict(valid=True,playing=True,paused=False,name='Main',type='HierarchyEventPlayer',run=1,key='gallery-main'))
    s.update(changes);return s

class GallerySignals(unittest.TestCase):
    def test_dedicated_take_and_stop_are_separate_from_global_flow(self):
        raw=dict(available=True,active=True,guide_available=True,guide_open=True,take_selected=True,enemy_id=28,selected_index_raw=1,
                 take_player=123,take_data=456,take_name='Take1',play_type_raw=0,ui_paused=False,slow=True,dev_mode=True,ui_hidden=False)
        s=sample(gallery=raw,flow={},event_playing=False)
        current=describe_gallery(s,10)
        self.assertTrue(current['dedicatedAvailable']);self.assertTrue(current['takeSelected'])
        self.assertFalse(current['playing']);self.assertEqual(current['playType'],'Animator')
        tracker=GalleryPlayback();keys=[e['key'] for e in tracker.update(s,10)]
        self.assertIn('gallery_take_change',keys);self.assertIn('gallery_controls',keys)
        self.assertNotIn('gallery_play_start',keys)
        self.assertFalse(tracker.update(s,10))
        raw['ui_paused']=True
        self.assertEqual([e['key'] for e in tracker.update(s,10)],['gallery_controls'])
        self.assertEqual(describe_gallery(s,10)['controlLabel'],'Stop 已开启')
        raw['selected_index_raw']=2;raw['take_data']=789
        self.assertEqual([e['key'] for e in tracker.update(s,10)],['gallery_selection_change','gallery_take_change'])
        self.assertFalse(describe_gallery(s,11)['dedicatedAvailable'])
    def test_real_gallery_session_switch_stop_resume_and_list(self):
        frames=json.loads((Path(__file__).parent/'fixtures/gallery-0.4.2.json').read_text(encoding='utf-8'))
        tracker=GalleryPlayback();states=[];events=[]
        for s in frames:
            now=s['sampled_at'];states.append(describe_gallery(s,now));events.append(tracker.update(s,now))
        self.assertEqual(states[0]['phase'],'browsing')
        self.assertEqual(states[1]['phase'],'preview')
        self.assertEqual([states[i]['takeName'] for i in (2,4,6)],['Load_2_0_GO','Continue','Failure'])
        self.assertFalse(states[2]['playerValid']);self.assertTrue(states[2]['playing'])
        # Index 2 arrives while take 1 is still loaded. No fabricated take load.
        self.assertEqual(states[3]['selectedIndexRaw'],2);self.assertEqual(states[3]['takeName'],'Load_2_0_GO')
        self.assertIn('gallery_selection_change',[e['key'] for e in events[3]])
        self.assertNotIn('gallery_take_change',[e['key'] for e in events[3]])
        self.assertEqual(states[7]['phase'],'manual_stop');self.assertTrue(states[7]['manualPauseConfirmed'])
        self.assertNotEqual(states[8]['phase'],'manual_stop')
        self.assertEqual(states[9]['phase'],'browsing');self.assertFalse(states[9]['takeSelected'])
        self.assertFalse(states[9]['playing']);self.assertEqual(states[9]['takeName'],'')
        self.assertTrue(frames[9]['gallery']['take_selected'])
        self.assertIn('gallery_list',[e['key'] for e in events[9]])
        # The game's changing flag stays true throughout; it must not block playback.
        self.assertTrue(states[2]['changing']);self.assertTrue(states[2]['playing'])
        # A residual global player is ignored as soon as the UI is back in the list.
        s=dict(frames[9],flow=frames[8]['flow']);self.assertFalse(describe_gallery(s,s['sampled_at'])['playing'])
    def test_dedicated_read_failure_retains_global_playback(self):
        current=describe_gallery(sample(gallery=dict(available=False,error='missing field')),10)
        self.assertTrue(current['playing']);self.assertFalse(current['dedicatedAvailable'])
        self.assertEqual(current['dedicatedError'],'missing field')
    def test_playback_does_not_require_player_or_zero_hp_and_browsing_never_counts(self):
        s=sample();self.assertTrue(describe_gallery(s,10)['playing'])
        s.update(event_playing=False,flow={})
        state=describe_gallery(s,10);self.assertEqual(state['phase'],'idle');self.assertFalse(state['playing'])
        self.assertTrue(s['gacha']['active'])
    def test_scene_identity_and_freshness_are_required(self):
        for changes in (dict(scene='Monastery'),dict(scene_id=7),dict(scene_id=43,scene=None),dict(source='external'),dict(sampled_at=0),dict(pid=0),dict(session='')):
            self.assertFalse(describe_gallery(sample(**changes),10)['inGallery'])
        for changes in (dict(loading=True),dict(flow={}),dict(flow=dict(valid=True,playing=True,name='Init',type='HierarchyEventPlayer'))):
            self.assertFalse(describe_gallery(sample(**changes),10)['playing'])
    def test_internal_wait_is_not_reported_as_user_pause_and_timeline_is_local(self):
        f=dict(sample()['flow'],paused=True,timeline_time=.516,timeline_duration=.783)
        state=describe_gallery(sample(flow=f,event_paused=True),10)
        self.assertEqual(state['phase'],'event_wait');self.assertTrue(state['playing'])
        self.assertFalse(state['manualPauseConfirmed']);self.assertFalse(state['uniqueCgIdAvailable'])
        self.assertEqual(state['timelineDuration'],.783)
        self.assertEqual(describe_gallery(sample(flow=f,paused=True),10)['phase'],'paused')
    def test_entries_stop_change_leave_and_signal_loss_are_distinct(self):
        monitor=GalleryPlayback();self.assertEqual([e['key'] for e in monitor.update(sample(),10)],['gallery_enter','gallery_play_start'])
        self.assertFalse(monitor.update(sample(10.1),10.1))
        f=dict(sample()['flow'],run=2)
        self.assertEqual([e['key'] for e in monitor.update(sample(10.2,flow=f),10.2)],['gallery_play_end','gallery_play_start'])
        self.assertEqual([e['key'] for e in monitor.update(sample(10.3,flow={}),10.3)],['gallery_play_end'])
        self.assertEqual([e['key'] for e in monitor.update(sample(10.4,scene='Monastery',scene_id=7,flow={}),10.4)],['gallery_leave'])
        monitor.update(sample(10.5),10.5)
        self.assertEqual([e['key'] for e in monitor.update({},11)],['gallery_play_end','gallery_signal_lost'])
    def test_incomplete_gallery_signal_still_cannot_drive_either_output_adapter(self):
        s=sample(player=2,valid=True,hp=dict(current=0,max=120));self.assertTrue(describe_gallery(s,10)['playing'])
        p=initial_profile()
        for planner,catalog,route in ((PulsePlanner(),WAVES,'pulse'),(OvcPlanner(),VIBRATION_WAVES,'vibration')):
            plan=planner.update(s,p,catalog,now=10,enabled=True)
            self.assertFalse(any(plan[route+'_stream'].values()))
            self.assertIn('等待图鉴专用字段',plan['reason'])
            p['gallery']['rule']['enabled']=False
            self.assertIn('回想模式',planner.update(s,p,catalog,now=10,enabled=True)['reason'])
            p['gallery']['rule']['enabled']=True
