"""Callback bursts retain evidence without repeatedly rebuilding the native UI."""
import json,queue,tempfile,time,unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
from PySide6.QtGui import QGuiApplication
from sinisistar_dglab.backend import Backend,ROOT
from sinisistar_dglab.simulation import demo_state

class Game:
    def __init__(self):self.events=queue.Queue();self.sequence=0;self.label='Loop'
    def snapshot(self):
        self.sequence+=1;s=demo_state('idle',0,time.monotonic())
        s.update(source='bepinex',session='refresh-test',pid=123,player=456,sample_id=self.sequence,
            flow=dict(valid=True,playing=True,key='[7,"Event","Main","HierarchyEventPlayer"]',
                      group='Event',name='Main',type='HierarchyEventPlayer',run=1,label=self.label))
        return s
    def recent_events(self,session):return []
    def stop(self):pass

class BackendRefresh(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.qt=QGuiApplication.instance() or QGuiApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp')
        self.b=Backend(offline=True,settings=Path(self.temp.name)/'settings.json');self.b._timer.stop()
        self.game=Game();self.b._observer=self.game;self.b.tick()
    def tearDown(self):self.b.shutdown();self.temp.cleanup()
    def test_burst_is_fully_recorded_with_one_display_update_and_one_append(self):
        updates=[];flows=[];self.b.eventsChanged.connect(lambda:updates.append(1));self.b.flowsChanged.connect(lambda:flows.append(1))
        count=self.b._monitor.counts.get('flow_label',0)
        for i in range(24):
            self.game.events.put(dict(event_type='flow_label_callback',session='refresh-test',player=456,
                sequence=i,utc=datetime.now(timezone.utc).isoformat(),label='Loop',label_type='SendDamageLabel'))
        with patch.object(self.b,'_write_event_lines',wraps=self.b._write_event_lines) as writer:self.b.tick()
        self.assertEqual(writer.call_count,1);self.assertEqual(len(writer.call_args.args[0]),24)
        self.assertEqual(updates,[1]);self.assertEqual(flows,[])
        self.assertEqual(self.b._monitor.counts['flow_label']-count,24)
        lines=[json.loads(x) for x in (Path(self.temp.name)/'events.jsonl').read_text(encoding='utf8').splitlines()]
        self.assertEqual(sum(x['key']=='plugin' for x in lines),24)
        self.assertFalse(self.b._armed);self.assertFalse(self.b._ovc_armed)
    def test_flow_cache_refreshes_on_flow_and_review_changes_only(self):
        with patch.object(self.b._flow_review,'rows',wraps=self.b._flow_review.rows) as build:
            rows=self.b.semanticFlows;self.b.semanticFlows;self.assertEqual(build.call_count,1)
            rows[0]['semantic_title']='external edit'
            self.assertNotEqual(self.b.semanticFlows[0]['semantic_title'],'external edit')
            self.b.log('test','ordinary event');self.b.semanticFlows;self.assertEqual(build.call_count,1)
            self.game.label='Next';self.b.tick();updated=self.b.semanticFlows
            self.assertEqual(build.call_count,2);self.assertIn('Next',updated[0]['labels'])
            key=updated[0]['key'];self.b.reviewFlows([key],'ramp')
            self.assertEqual(next(x for x in self.b.semanticFlows if x['key']==key)['review_decision'],'ramp')
            self.assertEqual(build.call_count,3)
    def test_exception_flushes_records_and_leaves_next_refresh_usable(self):
        updates=[];self.b.eventsChanged.connect(lambda:updates.append(1))
        def fail():
            self.b.log('test','first');self.b.log('test','second');raise RuntimeError('fixture')
        with patch.object(self.b,'_tick',side_effect=fail):
            with self.assertRaises(RuntimeError):self.b.tick()
        self.assertFalse(self.b._event_batch);self.assertEqual(updates,[1])
        self.b.log('test','third');self.assertEqual(updates,[1,1])
        lines=[json.loads(x) for x in (Path(self.temp.name)/'events.jsonl').read_text(encoding='utf8').splitlines()]
        self.assertEqual([x['text'] for x in lines if x['key']=='test'],['first','second','third'])
