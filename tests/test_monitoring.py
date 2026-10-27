import json, queue, tempfile, time, unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta
from sinisistar_dglab.monitoring import EventMonitor,statuses
from sinisistar_dglab.plugin_bridge import PluginObserver
from sinisistar_dglab.telemetry import TYPES

def snapshot(sample=1,hp=60,**kw):
    s=dict(valid=True,session='run',sample_id=sample,player=22,scene_id=43,hp={'current':hp,'max':100},
           mp={'current':100,'max':100},broken=False,paused=False,time_scale=1,bound=False,abnormals=[])
    s.update(kw);return s

def callback(seq=1,kind='bind_release_callback',**kw):
    e=dict(session='run',sequence=seq,player=22,event_type=kind,utc='2026-10-24T12:00:00.1234567+00:00',binder='Zombie',hp={'current':60,'max':100})
    e.update(kw);return e

class Monitoring(unittest.TestCase):
    def setUp(self):self.m=EventMonitor();self.m.begin_session('run')
    def test_mp_snapshot_changes_do_not_create_events(self):
        self.m.snapshot(snapshot())
        self.assertEqual(self.m.snapshot(snapshot(2,mp={'current':60,'max':100})),[])
        self.assertEqual(self.m.snapshot(snapshot(3,mp={'current':100,'max':100})),[])
        self.assertNotIn('mp',self.m.counts)
    def test_native_nested_release_and_replayed_history_are_one(self):
        self.m.callback(callback(),TYPES['AbnormalType'],history=True)
        self.m.callback(callback(2,binder='',utc='2026-10-24T12:00:00.1235567+00:00'),TYPES['AbnormalType'],history=True)
        self.m.callback(callback(),TYPES['AbnormalType'])
        self.assertEqual(self.m.counts['release'],1);self.assertEqual(self.m.rows[0]['rawCount'],2)
        self.assertTrue(self.m.rows[0]['history'])
    def test_real_second_release_is_not_deduplicated(self):
        self.m.callback(callback(),TYPES['AbnormalType'])
        self.m.callback(callback(2,utc='2026-10-24T12:00:02.1234567+00:00'),TYPES['AbnormalType'])
        self.assertEqual(self.m.counts['release'],2)
    def test_startup_cleanup_and_other_response_not_player_events(self):
        self.assertIsNone(self.m.callback(callback(player=0),TYPES['AbnormalType']))
        self.assertIsNone(self.m.callback(callback(kind='release_reason_callback',is_player_response=False),TYPES['AbnormalType']))
    def test_mp_only_callback_does_not_create_a_damage_event(self):
        row=self.m.callback(callback(kind='damage_callback',before_hp=60,remain_hp=60,spend_hp=-1,spend_mp=10,remain_mp=90),TYPES['AbnormalType'])
        self.assertIsNone(row);self.assertNotIn('damage',self.m.counts);self.assertNotIn('heal',self.m.counts)
    def test_zero_to_zero_damage_is_shown_as_request_not_actual_hp_loss(self):
        row=self.m.callback(callback(kind='damage_callback',before_hp=0,remain_hp=0,spend_hp=10,spend_mp=-1),TYPES['AbnormalType'])
        self.assertIn('零血后受击请求',row['text']);self.assertIn('实际 HP 未再下降',row['text'])
        self.assertNotIn('hp0',self.m.counts);self.assertNotIn('heal',self.m.counts)
    def test_current_abnormal_levels_read_while_paused(self):
        self.m.snapshot(snapshot(paused=True,abnormals=[{'name':'Defilement','level':1}]))
        rows=self.m.snapshot(snapshot(2,paused=True,abnormals=[{'name':'Defilement','level':2}]))
        self.assertEqual(rows[0]['text'],'污秽 Lv.1 → Lv.2')
        self.assertEqual(statuses([{'name':'InfertilityBlessing','level':1}])[0]['label'],'不孕的加护')
    def test_unmapped_status_retains_id_and_name(self):
        row=statuses([{'name':'FutureStatus','type_raw':-7,'level':3}])[0]
        self.assertEqual(row['label'],'FutureStatus');self.assertEqual(row['raw'],-7);self.assertFalse(row['translated'])
    def test_current_status_routes_follow_rules_and_exclude_positive_buff(self):
        from sinisistar_dglab.simulation import default_profile
        p=default_profile();p['abnormals']['Defilement'].update(enabled=True,pulse_channel='B',vibration_enabled=False)
        p['abnormals']['InfertilityBlessing'].update(enabled=True,pulse_enabled=True,vibration_enabled=True)
        positive,negative,unknown=statuses([{'name':'InfertilityBlessing','level':1},{'name':'Defilement','level':2},{'name':'FutureStatus','level':3}],p)
        self.assertFalse(positive['pulse_participates']);self.assertFalse(positive['ovc_participates'])
        self.assertTrue(negative['pulse_participates']);self.assertEqual(negative['pulse_channels'],'B');self.assertFalse(negative['ovc_participates'])
        self.assertFalse(unknown['configured']);self.assertFalse(unknown['pulse_participates'])
    def test_current_status_timer_metadata_and_zero_level_stay_visible(self):
        from sinisistar_dglab.simulation import default_profile
        row=statuses([dict(name='Defilement',level=0,delete_timer=12.5,delete_time=30,max_level=10,remove_on_scene_change=True)],default_profile())[0]
        self.assertEqual(row['timer'],12.5);self.assertEqual(row['delete_time'],30);self.assertEqual(row['max_level'],10)
        self.assertTrue(row['remove_on_scene_change']);self.assertFalse(row['pulse_participates'])
    def test_rebind_and_telemetry_gap_do_not_create_healing_or_break(self):
        self.m.snapshot(snapshot(hp=0))
        self.assertEqual([r['key'] for r in self.m.snapshot(snapshot(2,hp=100,player=23))],['scene'])
        self.m.snapshot(None)
        self.assertEqual(self.m.snapshot(snapshot(3,player=23,broken=True)),[])
    def test_pause_break_and_pause_resume_edges(self):
        self.m.snapshot(snapshot())
        self.assertEqual({r['key'] for r in self.m.snapshot(snapshot(2,paused=True,broken=True))},{'pause','break'})
        self.assertEqual([r['key'] for r in self.m.snapshot(snapshot(3,broken=True))],['pause'])
    def test_dead_release_is_not_success_and_new_session_clears_records(self):
        self.m.snapshot(snapshot());self.m.snapshot(snapshot(2,bound=True,gacha={'value':1,'threshold':10}))
        rows=self.m.snapshot(snapshot(3,hp=0,bound=False,gacha={'value':11,'threshold':10}))
        self.assertNotIn('escape',[r['key'] for r in rows]);self.assertIn('hp0',[r['key'] for r in rows])
        self.m.begin_session('next');self.assertEqual(self.m.rows,[]);self.assertEqual(self.m.counts,{})
    def test_catalog_separates_unobserved_hooks_from_actual_events(self):
        self.m.callback(callback(kind='bind_start_callback'),TYPES['AbnormalType'])
        catalog={r['key']:r for r in self.m.catalog()}
        self.assertEqual(catalog['grab']['count'],1);self.assertEqual(catalog['gameover']['count'],0)
        self.assertEqual(catalog['gameover']['source'],'待验证回调')
    def test_display_history_never_enqueued(self):
        root=Path(__file__).resolve().parents[1]/'artifacts/test-temp';root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory:
            path=Path(directory)/'events.jsonl'
            path.write_text(json.dumps(callback())+'\n'+json.dumps(callback(2,session='old'))+'\n',encoding='utf-8')
            observer=PluginObserver(directory)
            self.assertEqual(len(observer.recent_events('run')),1);self.assertTrue(observer.events.empty())

class BackendMonitor(unittest.TestCase):
    def test_history_display_keeps_output_paused_and_service_closed(self):
        from PySide6.QtGui import QGuiApplication
        from sinisistar_dglab.backend import Backend
        app=QGuiApplication.instance() or QGuiApplication([])
        root=Path(__file__).resolve().parents[1]/'artifacts/test-temp';root.mkdir(parents=True,exist_ok=True)
        class Observer:
            events=queue.Queue()
            def snapshot(self):return snapshot(live=True,sampled_at=time.monotonic(),pid=1,utc=datetime.now(timezone.utc).isoformat())
            def recent_events(self,session):return [callback(utc=datetime.now(timezone.utc).isoformat())]
            def stop(self):pass
        with tempfile.TemporaryDirectory(dir=root) as directory:
            b=Backend(offline=True,settings=Path(directory)/'settings.json');b._observer=Observer()
            try:
                b.tick()
                self.assertTrue(b.monitorEvents[0]['history']);self.assertEqual(b.monitorEvents[0]['key'],'release')
                self.assertFalse(b.state['armed']);self.assertFalse(b.state['serverReady']);self.assertIsNone(b._service)
            finally:b.shutdown()

def enemy_packet(seq=1,kind='enemy_damage_callback',**kw):
    e=callback(seq,kind,enemy_object=888,enemy_life=1,enemy_class='Zombie',source_is_player=True,
               damage_id=3,before_hp=30,remain_hp=10,actual_damage=999,dead_state_before=0,dead_state_after=0)
    e.update(kw);return e

class EnemyCombat(unittest.TestCase):
    def setUp(self):self.m=EventMonitor();self.m.begin_session('run')
    def death(self,seq=2,**kw):
        e=enemy_packet(seq,'enemy_death_callback',hp_current=0,fatal_before_hp=10,fatal_after_hp=0,
                       dead_state_before=0,dead_state_after=1,not_defeat=False)
        e.update(kw);return e
    def test_player_hit_uses_actual_hp_loss(self):
        row=self.m.callback(enemy_packet(),TYPES['AbnormalType'])
        self.assertEqual(row['key'],'enemy_hit');self.assertIn('伤害 20',row['text']);self.assertNotIn('999',row['text'])
        self.assertEqual(self.m.counts.get('enemy_kill',0),0)
    def test_other_or_unknown_attacker_is_not_player_hit(self):
        row=self.m.callback(enemy_packet(source_is_player=False,sender_class='Trap'),TYPES['AbnormalType'])
        self.assertEqual(row['key'],'enemy_damage');self.assertIn('Trap',row['text'])
    def test_hp_zero_without_death_callback_is_not_a_kill(self):
        row=self.m.callback(enemy_packet(remain_hp=0),TYPES['AbnormalType'])
        self.assertEqual(row['key'],'enemy_hit');self.assertEqual(self.m.counts.get('enemy_kill',0),0)
    def test_player_lethal_damage_plus_death_is_one_kill(self):
        self.m.callback(enemy_packet(remain_hp=0),TYPES['AbnormalType'])
        row=self.m.callback(self.death(),TYPES['AbnormalType'])
        self.assertEqual(row['key'],'enemy_kill')
        self.assertIsNone(self.m.callback(self.death(3),TYPES['AbnormalType']))
        self.assertIsNone(self.m.callback(self.death(4,dead_state_before=1,dead_state_after=2),TYPES['AbnormalType']))
        self.assertEqual(self.m.counts['enemy_kill'],1)
    def test_death_before_damage_report_still_shows_correct_kill(self):
        self.assertEqual(self.m.callback(self.death(),TYPES['AbnormalType'])['key'],'enemy_kill')
        self.m.callback(enemy_packet(remain_hp=0),TYPES['AbnormalType'])
        self.assertEqual(self.m.counts['enemy_hit'],1);self.assertEqual(self.m.counts['enemy_kill'],1)
    def test_scene_cleanup_or_uncredited_death_not_player_kill(self):
        self.assertIsNone(self.m.callback(self.death(not_defeat=True),TYPES['AbnormalType']))
        row=self.m.callback(self.death(3,source_is_player=False,damage_id=0),TYPES['AbnormalType'])
        self.assertEqual(row['key'],'enemy_death');self.assertEqual(self.m.counts.get('enemy_kill',0),0)
    def test_missing_lethal_evidence_is_not_credited(self):
        row=self.m.callback(self.death(fatal_before_hp=0),TYPES['AbnormalType'])
        self.assertEqual(row['key'],'enemy_death')
    def test_resurrected_or_pooled_enemy_has_new_life(self):
        self.m.callback(self.death(),TYPES['AbnormalType'])
        self.m.callback(self.death(3,enemy_life=2),TYPES['AbnormalType'])
        self.assertEqual(self.m.counts['enemy_kill'],2)
    def test_zero_damage_and_corpse_hit_are_not_damage_events(self):
        self.assertIsNone(self.m.callback(enemy_packet(remain_hp=30),TYPES['AbnormalType']))
        self.assertIsNone(self.m.callback(enemy_packet(2,before_hp=0,remain_hp=0),TYPES['AbnormalType']))
    def test_new_capabilities_are_pending_until_loaded(self):
        pending={r['key']:r for r in self.m.catalog()}
        self.assertIn('等待 0.2.0',pending['enemy_hit']['status'])
        loaded={r['key']:r for r in self.m.catalog({'damage':True,'death_exists':True})}
        self.assertEqual(loaded['enemy_hit']['status'],'待实机触发')
        self.assertEqual(loaded['enemy_kill']['status'],'待实机触发')

if __name__=='__main__':unittest.main()
