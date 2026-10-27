"""Fresh native dialogue callbacks affect HUD visibility, never device output."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from pathlib import Path
import queue,tempfile,time,unittest
from unittest.mock import patch

from PySide6.QtGui import QGuiApplication
from sinisistar_dglab.backend import Backend

ROOT=Path(__file__).resolve().parents[1]

def event(sequence=1,kind='flow_request_callback',age=0,**changes):
    row=dict(sequence=sequence,event_type=kind,session='hud-test',pid=123,player=456,
             utc=(datetime.now(timezone.utc)-timedelta(seconds=age)).isoformat(),name='Sequence_Talk')
    row.update(changes);return row

class Observer:
    def __init__(self):
        self.events=queue.Queue();self.history=[];self.stale=False
        self.state=dict(source='bepinex',live=True,valid=True,session='hud-test',pid=123,player=456,
                        scene_id=43,scene='Monastery_Tutorial1',hp={'current':100,'max':100},mp={'current':100,'max':100},
                        sample_id=1,sampled_at=time.monotonic(),paused=False,loading=False,bound=False,
                        event_playing=False,time_scale=1,flow={},abnormals=[])
    def snapshot(self):
        self.state['sampled_at']=time.monotonic()-(2 if self.stale else 0);self.state['sample_id']+=1
        return deepcopy(self.state)
    def recent_events(self,session):return deepcopy(self.history)
    def stop(self):pass

class DialogueCallbacks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QGuiApplication.instance() or QGuiApplication([])
    def setUp(self):
        directory=ROOT/'artifacts/test-temp';directory.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=directory)
        # Keep these isolated read-only callback tests out of the live user's
        # diagnostic event file and avoid constructing any network service.
        self.log_patch=patch.object(Backend,'log',lambda *args,**kwargs:None);self.log_patch.start()
        self.backend=Backend(offline=True,settings=Path(self.temp.name)/'settings.json');self.backend._timer.stop()
        self.observer=Observer();self.backend._observer=self.observer
    def tearDown(self):
        self.backend.shutdown();self.log_patch.stop();self.temp.cleanup()
    def test_new_queued_request_also_in_startup_history_still_hides(self):
        request=event();self.observer.history=[request];self.observer.events.put(deepcopy(request))
        self.backend.tick()
        self.assertTrue(self.backend.state['hudDialogueActive'])
        self.assertEqual(self.backend._monitor.counts['flow_request'],1)
        self.assertTrue(self.backend._monitor.rows[0]['history'])
        self.assertIsNone(self.backend._service);self.assertIsNone(self.backend._ovc_service)
    def test_fresh_history_without_new_callback_never_hides(self):
        self.observer.history=[event(age=.1)];self.backend.tick()
        self.assertFalse(self.backend.state['hudDialogueActive'])
    def test_stale_other_player_other_session_future_and_invalid_requests_are_ignored(self):
        requests=[event(1,age=2),event(2,player=999),event(3,session='old-session'),
                  event(4,age=-2),event(5,utc='invalid')]
        for request in requests:
            with self.subTest(request=request):
                self.observer.events.put(request);self.backend.tick()
                self.assertFalse(self.backend.state['hudDialogueActive'])
    def test_only_matching_fresh_stop_clears_pending_request(self):
        self.observer.events.put(event());self.backend.tick()
        self.assertTrue(self.backend.state['hudDialogueActive'])
        for stop in [event(2,'flow_stop_callback',age=2),event(3,'flow_stop_callback',player=999),
                     event(4,'flow_stop_callback',session='old-session')]:
            self.observer.events.put(stop);self.backend.tick()
            self.assertTrue(self.backend.state['hudDialogueActive'])
        self.observer.events.put(event(5,'flow_stop_callback'));self.backend.tick()
        self.assertFalse(self.backend.state['hudDialogueActive'])
    def test_rebind_and_stale_source_clear_pending_dialogue(self):
        self.observer.events.put(event());self.backend.tick()
        self.observer.state['player']=999;self.backend.tick()
        self.assertFalse(self.backend.state['hudDialogueActive'])
        self.observer.events.put(event(2,player=999));self.backend.tick()
        self.assertTrue(self.backend.state['hudDialogueActive'])
        self.observer.stale=True;self.backend.tick()
        self.assertFalse(self.backend.state['hudDialogueActive'])
    def test_zero_hp_and_confirmed_defeat_do_not_hide_the_hud(self):
        self.observer.state['hp']['current']=0;self.observer.events.put(event());self.backend.tick()
        self.assertFalse(self.backend.state['hudDialogueActive'])
        self.observer.state.update(hp={'current':100,'max':100},flow={'playing':True,'defeat_confirmed':True})
        self.backend.tick();self.assertFalse(self.backend.state['hudDialogueActive'])
