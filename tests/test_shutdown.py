import tempfile,unittest
from pathlib import Path
from PySide6.QtGui import QGuiApplication
from sinisistar_dglab.backend import Backend,ROOT

class Route:
    def __init__(self,events,name):self.events=events;self.name=name
    def set_output_permission(self,allowed,reason):self.events.append((self.name,'permission',allowed))
    def emergency_zero(self):self.events.append((self.name,'zero'))
    def stop(self):self.events.append((self.name,'stop'))

class Shutdown(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QGuiApplication.instance() or QGuiApplication([])
    def test_shared_hub_stops_once_without_detaching_slots_first(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as temp:
            b=Backend(offline=True,settings=Path(temp)/'settings.json');events=[]
            pulse=Route(events,'pulse');ovc=Route(events,'ovc')
            class Hub:
                def channel(self,role):return pulse if role=='pulse' else ovc
                def stop(self):events.append(('hub','zero-and-stop'))
            b._service=pulse;b._ovc_service=ovc;b._v4=Hub();b._armed=b._ovc_armed=True
            b.shutdown();b.shutdown()
            self.assertEqual(events,[('pulse','permission',False),('ovc','permission',False),('hub','zero-and-stop')])
            self.assertFalse(b._timer.isActive());self.assertFalse(b._armed);self.assertFalse(b._ovc_armed)
            self.assertIsNone(b._service);self.assertIsNone(b._v4)
    def test_v3_failure_does_not_leave_shared_v4_or_observer_running(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as temp:
            b=Backend(offline=True,settings=Path(temp)/'settings.json');events=[]
            class Broken(Route):
                def emergency_zero(self):raise RuntimeError('fixture failed zero')
            v4pulse=Route(events,'v4pulse');ovc=Route(events,'ovc')
            class Hub:
                def channel(self,role):return v4pulse
                def stop(self):events.append(('hub','stop'))
            b._service=Broken(events,'v3');b._ovc_service=ovc;b._v4=Hub();b._observer=Route(events,'observer')
            b.shutdown()
            self.assertIn(('v3','stop'),events);self.assertIn(('hub','stop'),events);self.assertIn(('observer','stop'),events)
            self.assertEqual(len(b._shutdown_errors),1)
