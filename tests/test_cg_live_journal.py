import json,queue,tempfile,time,unittest
from pathlib import Path
from copy import deepcopy
from sinisistar_dglab.cg_live_journal import LiveCgJournal

ROOT=Path(__file__).resolve().parents[1]


class Journal(unittest.TestCase):
    def test_records_without_consuming_events_and_closes_after_source_stops(self):
        class Source:
            def __init__(self):
                self.events=queue.Queue();self.events.put('keep')
                self.data=dict(session='one',sample_id=1,live=True,cg_playback=dict(shared_animators=[]))
            def snapshot(self):return deepcopy(self.data)
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as tmp:
            root=Path(tmp);source=Source();journal=LiveCgJournal(source,root)
            (root/'connection-diagnostics.json').write_text(json.dumps(dict(utc='one',cgDetectionMode='playback_only')),encoding='utf-8')
            journal.start();deadline=time.monotonic()+2
            while journal.samples<1 or journal.controls<1:
                if time.monotonic()>deadline:self.fail('Journal did not record')
                time.sleep(.01)
            source.data.update(sample_id=2,live=False);deadline=time.monotonic()+2
            while journal.samples<2:
                if time.monotonic()>deadline:self.fail('Journal did not record source loss')
                time.sleep(.01)
            journal.close();self.assertFalse(journal._thread.is_alive())
            self.assertEqual(source.events.get_nowait(),'keep')
            states=[json.loads(line) for line in (journal.directory/'states.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertTrue(states[0]['live']);self.assertFalse(states[-1]['live'])
            report=json.loads((journal.directory/'summary.json').read_text(encoding='utf-8'))
            self.assertTrue(report['complete']);self.assertEqual(report['error'],'')
            self.assertFalse(report['device_services_started_by_recorder'])

    def test_io_failure_is_confined_to_the_recorder(self):
        class Source:
            def snapshot(self):raise RuntimeError('read unavailable')
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as tmp:
            journal=LiveCgJournal(Source(),Path(tmp));journal.start();journal._thread.join(2)
            self.assertFalse(journal._thread.is_alive());self.assertIn('read unavailable',journal.error)
            self.assertTrue((journal.directory/'summary.json').exists())
