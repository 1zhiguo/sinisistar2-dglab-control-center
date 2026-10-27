from copy import deepcopy
from pathlib import Path
import json,tempfile,unittest,zipfile
from sinisistar_dglab.cg_batch import CgBatchRecorder,CHANNELS

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=json.loads((Path(__file__).parent/'fixtures/gallery-0.5.0-bobel-session.json').read_text(encoding='utf-8'))
def state(now=10,enemy=61,index=1):
    s=deepcopy(FIXTURE);s.update(live=True,sampled_at=now,scene='Gallery',sample_id=int(now*100),utc='2026-10-27T09:00:00+00:00')
    s['gallery'].update(enemy_id=enemy,selected_index_raw=index,take_count=2);return s
def plan(route):return dict(hp_used=False,reason='CG 播放',**{route+'_stream':{c:dict(peak=20,samples=[10]*4,frequencies=[30]*4) for c in 'AB'}})

class CgBatch(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp');self.root=Path(self.temp.name);self.j=CgBatchRecorder(self.root/'batch')
        self.profile=dict(simulation=dict(cg_detection_mode='playback_only',pulse_cap_a=50,rules={}),connections=dict(lan_ip='SECRET-IP'),game_directory='SECRET-GAME-PATH')
        self.j.ensure(self.profile)
    def tearDown(self):self.j.close();self.temp.cleanup()
    def observe(self,s=None,now=10,pulse=None,ovc=None,mock=None,wire=None):
        self.j.observe(s or state(now),pulse or {},ovc or {},wire or {},wire or {},mock or {},'playback_only',now)
    def test_unrecognized_cg_can_be_marked_no_without_any_feedback(self):
        s=state();s['gallery'].pop('take_token_active');self.observe(s)
        self.assertEqual(self.j.snapshot()['current'],'gallery:61:1');self.assertFalse(self.j.data['cases']['gallery:61:1']['recognized'])
        self.assertTrue(self.j.mark('gallery:61:1','no'));saved=json.loads((self.j.root/self.j.data['id']/'round.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['cases']['gallery:61:1']['verdict'],'no');self.assertEqual(self.j.snapshot()['no'],1)
        self.assertFalse(self.j.mark('gallery:61:2','no'))
    def test_switches_follow_numbered_buttons_without_old_name_or_manual_result(self):
        self.observe();self.j.mark('gallery:61:1','yes')
        s=state(10.1,index=2);self.observe(s,10.1)
        second=self.j.data['cases']['gallery:61:2'];self.assertEqual(second['name'],'');self.assertEqual(second['verdict'],'')
        s=state(10.6,index=2);s['gallery']['take_name']='Different take';self.observe(s,10.6)
        self.assertEqual(second['name'],'Different take');self.assertEqual(self.j.data['cases']['gallery:61:1']['verdict'],'yes')
    def test_return_to_list_keeps_last_case_for_late_mark_and_replay_keeps_history(self):
        self.observe();s=state(10.5);s['gallery']['selected_index_raw']=-1;self.observe(s,10.5)
        self.assertEqual(self.j.snapshot()['current'],'');self.assertEqual(self.j.snapshot()['focus'],'gallery:61:1')
        self.j.mark('gallery:61:1','yes');self.observe(state(11),11)
        self.assertEqual(len(self.j.data['visits']),2);self.assertEqual(self.j.data['visits'][0]['verdict'],'yes')
        self.assertEqual(self.j.data['cases']['gallery:61:1']['verdict'],'')
    def test_identical_take_names_from_different_enemies_are_separate(self):
        self.observe();self.observe(state(11,enemy=59),11)
        self.assertEqual(self.j.snapshot()['observed'],2);self.assertNotEqual(self.j.data['visits'][0]['case_id'],self.j.data['visits'][1]['case_id'])
    def test_short_data_gap_or_window_restart_does_not_erase_the_users_mark(self):
        self.observe();self.j.mark('gallery:61:1','yes')
        stale=state(10.5);stale['sampled_at']=0;self.observe(stale,10.5)
        self.observe(state(11),11)
        self.assertEqual(len(self.j.data['visits']),1);self.assertEqual(self.j.data['cases']['gallery:61:1']['verdict'],'yes')
        self.j.close();self.j=CgBatchRecorder(self.root/'batch');self.j.ensure(self.profile);self.observe(state(12),12)
        self.assertEqual(len(self.j.data['visits']),1);self.assertEqual(self.j.snapshot()['yes'],1)
    def test_human_verdict_is_never_inferred_from_app_receipts(self):
        self.observe(pulse=plan('pulse'),ovc=plan('vibration'))
        mock=dict(connected=True,receipts={c:dict(count=4,at=10.45,frame='0A'*8) for c in CHANNELS})
        wire={c:dict(active=True,deadline=11) for c in 'AB'}
        self.observe(state(10.5),10.5,plan('pulse'),plan('vibration'),mock,wire)
        row=self.j.rows()[0];self.assertEqual(len(row['received']),4);self.assertEqual(row['verdict'],'')
        self.j.mark(row['id'],'no');self.assertEqual(self.j.rows()[0]['manual_label'],'无反馈')
    def test_old_or_disconnected_receipts_do_not_count_as_current_feedback(self):
        mock=dict(connected=True,receipts={c:dict(count=100,at=9) for c in CHANNELS})
        self.observe(pulse=plan('pulse'),ovc=plan('vibration'),mock=mock)
        stale=deepcopy(mock);stale['receipts']['pulseA']['count']=101;stale['receipts']['pulseA']['at']=10.1
        self.observe(state(10.5),10.5,plan('pulse'),plan('vibration'),stale)
        self.assertFalse(self.j.rows()[0]['received'])
        stale['connected']=False;stale['receipts']['pulseA'].update(count=102,at=10.6)
        self.observe(state(10.7),10.7,plan('pulse'),plan('vibration'),stale);self.assertFalse(self.j.rows()[0]['received'])
    def test_pause_does_not_record_other_cg_and_finish_keeps_prior_round(self):
        self.observe();first=self.j.data['id'];self.j.pause();self.observe(state(12,enemy=59),12)
        self.assertEqual(self.j.snapshot()['observed'],1);self.j.resume();self.observe(state(12,enemy=59),12)
        self.assertEqual(self.j.snapshot()['observed'],2);self.j.new(self.profile)
        old=json.loads((self.j.root/first/'round.json').read_text(encoding='utf-8'));self.assertEqual(old['status'],'finished');self.assertNotEqual(first,self.j.data['id'])
    def test_resume_persists_feedback_notes_and_closes_interrupted_visit(self):
        self.observe();self.j.mark('gallery:61:1','yes');self.j.note('gallery:61:1','只有 A 通道');key=self.j.data['id'];self.j.close()
        self.j=CgBatchRecorder(self.root/'batch');self.j.ensure(self.profile)
        self.assertEqual(self.j.data['id'],key);self.assertEqual(self.j.data['cases']['gallery:61:1']['note'],'只有 A 通道')
        self.assertEqual(self.j.snapshot()['yes'],1);self.assertTrue(self.j.data['visits'][0]['end'])
    def test_export_contains_reports_samples_and_no_connection_secrets(self):
        self.observe();self.j.mark('gallery:61:1','no');self.j.note('gallery:61:1','没有反馈');path=self.j.export()
        with zipfile.ZipFile(path) as z:
            self.assertIsNone(z.testzip());self.assertEqual(set(z.namelist()),{'report.json','results.csv','samples.jsonl','READ_ME.txt'})
            report=json.loads(z.read('report.json'));self.assertEqual(report['cases']['gallery:61:1']['verdict'],'no')
            raw=z.read('report.json').decode();self.assertNotIn('SECRET-IP',raw);self.assertNotIn('SECRET-GAME-PATH',raw)
            self.assertTrue(z.read('results.csv').startswith(b'\xef\xbb\xbf'));self.assertIn('没有反馈',z.read('results.csv').decode('utf-8-sig'))
            for line in z.read('samples.jsonl').splitlines():self.assertEqual(json.loads(line)['mode'],'playback_only')
    def test_second_writer_cannot_overwrite_live_round(self):
        self.observe();other=CgBatchRecorder(self.root/'batch');other.ensure(self.profile)
        try:self.assertIn('重复窗口',other.error);self.assertFalse(other.mark('gallery:61:1','no'))
        finally:other.close()
