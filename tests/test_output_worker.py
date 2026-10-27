"""Independent planner and actual loopback APP; never opens a hardware route."""
import json,queue,tempfile,time,unittest
from pathlib import Path
from copy import deepcopy
from PySide6.QtGui import QGuiApplication
from sinisistar_dglab.backend import Backend,ROOT
from sinisistar_dglab.output_worker import OutputWorker
from test_v4_backend import Game
from test_gallery_output import state,profile,WAVES


class Sink:
    def __init__(self):self.frames=[];self.allowed=False;self.latched=False
    def snapshot(self):return dict(connected=True,feedback_known=True,limit_a=90,limit_b=90,local_only=True)
    def set_output_permission(self,allowed,*args,**kwargs):self.allowed=bool(allowed and not self.latched);return self.allowed
    def submit_plan(self,frames,generated_at=None):self.frames.append((generated_at,deepcopy(frames)))
    def emergency_zero(self):self.allowed=False
    def latch_emergency_stop(self):self.latched=True;self.allowed=False
    def clear_emergency_stop(self):self.latched=False


class OutputWorkerTests(unittest.TestCase):
    def test_fresh_observer_and_callbacks_not_ui_history(self):
        game=Game();game.s=state(time.monotonic());game.output_events=queue.Queue()
        pulse=Sink();ovc=Sink();w=OutputWorker();p=profile()
        w.configure(p,WAVES,WAVES,[dict(key=c,limit=50) for c in 'AB'],dict(A=90,B=90))
        w.controls(observer=game,service=pulse,ovc_service=ovc,armed=True,ovc_armed=True,emergency=False,
            sim_running=False,sim_source='live',connection={'pulse_backend':'mock'},pulse_channels=dict(A=True,B=True),ovc_channels=dict(A=True,B=True))
        w.step();w.step();self.assertTrue(all(pulse.frames[-1][1].values()));self.assertTrue(all(ovc.frames[-1][1].values()))
        game.stale=True;w.step();self.assertFalse(pulse.allowed or ovc.allowed)
        game.stale=False;game.s['paused']=True;w.step();self.assertFalse(pulse.allowed or ovc.allowed)
        game.s['paused']=False;w.step();w.step();self.assertTrue(pulse.allowed and ovc.allowed)
        w.invalidate(ovc=False);self.assertFalse(pulse.allowed);self.assertTrue(ovc.allowed)
        before=len(pulse.frames);w.step();self.assertEqual(len(pulse.frames),before)
        w.close()

    def test_independent_hotkey_latches_before_gui_receives_stop(self):
        keys=set();notifications=[];w=OutputWorker(key_down=lambda k:k in keys,on_panic=lambda:notifications.append(True))
        pulse=Sink();w.controls(observer=None,service=pulse,ovc_service=None,armed=True,ovc_armed=False,emergency=False,
            sim_running=False,sim_source='live',connection={'pulse_backend':'mock'},pulse_channels=dict(A=True,B=True),ovc_channels=dict(A=True,B=True),
            shortcut=dict(vk=123,modifiers=2),hotkey_active=True)
        keys.add(123);w._check_hotkey();self.assertFalse(pulse.latched)
        keys.add(17);w._check_hotkey();self.assertTrue(pulse.latched);self.assertEqual(len(notifications),1)
        w._check_hotkey();self.assertEqual(len(notifications),1)
        w.unlock();self.assertFalse(w.c._armed);w.close()


class OutputWorkerLoopback(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.qt=QGuiApplication.instance() or QGuiApplication([])

    def test_cg_switch_gui_stall_four_channels_panic_resume_and_stale_stop(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as folder:
            b=Backend(offline=True,settings=Path(folder)/'settings.json');b._timer.stop();game=Game();game.s=state(time.monotonic());b._observer=game
            p=profile();b._sim_profile=p;b._waves.extend(WAVES);b._vibration_custom.extend(WAVES)
            b._channels=[dict(key=c,limit=50,frequency=30) for c in 'AB'];b._ovc_limits=dict(A=90,B=90)
            b._connection['auto_enable']=False;b.offline=False;b._start_output_worker();report={}
            def until(fn,seconds=4,pump=True):
                end=time.monotonic()+seconds
                while time.monotonic()<end:
                    if pump:b.tick()
                    if fn():return
                    time.sleep(.025)
                self.fail('Loopback did not settle: '+str(b._output_worker.snapshot()))
            def counts():return {c:b._mock_session.snapshot().get(c,0) for c in ('pulsesA','pulsesB','ovcPulsesA','ovcPulsesB')}
            try:
                b.startMockBoth();session=b._mock_session
                until(lambda:all(v>=3 for v in counts().values()))
                before=counts();time.sleep(.7);after=counts()
                self.assertTrue(all(after[k]-v>=3 for k,v in before.items()),(before,after))
                report['gui_stall_seconds']=.7;report['received_during_stall']={k:after[k]-v for k,v in before.items()}
                aged=b._output_worker.snapshot()['pulse']['gallery_age'];self.assertGreater(aged,.5)
                game.s=state(time.monotonic(),4)
                until(lambda:0<b._output_worker.snapshot()['pulse'].get('gallery_age',99)<aged,seconds=.4,pump=False)
                report['switch_reset_age']=b._output_worker.snapshot()['pulse'].get('gallery_age')
                b.emergencyStop();self.assertTrue(b._emergency);time.sleep(.2);stopped=counts();time.sleep(.25);self.assertEqual(stopped,counts())
                self.assertFalse(b._service._allowed or b._ovc_service._allowed)
                # Repeated panic must retain the original resume selection.
                b.emergencyStop();b.resumeAfterEmergency();self.assertFalse(b._emergency);self.assertTrue(b._armed and b._ovc_armed)
                until(lambda:all(v>stopped[k] for k,v in counts().items()),pump=False)
                self.assertFalse(b._service.route._global_emergency_stop.is_set())
                game.stale=True;time.sleep(.3);stopped=counts();time.sleep(.25);self.assertEqual(stopped,counts())
                self.assertFalse(b._service._allowed or b._ovc_service._allowed)
                game.stale=False;until(lambda:all(v>stopped[k] for k,v in counts().items()),pump=False)
                # A disconnected/replaced slot must never inherit resume authority.
                b.emergencyStop();b._emergency_resume['pulse']=('different-device',);b.resumeAfterEmergency()
                self.assertFalse(b._armed);self.assertTrue(b._ovc_armed)
                report.update(passed=True,hardware_connected=False,worker=b._output_worker.snapshot()['max_ms'],panic_resume=True,stale_stop=True)
            finally:
                b.shutdown()
                out=ROOT/'artifacts/performance';out.mkdir(exist_ok=True)
                (out/'independent-output-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
