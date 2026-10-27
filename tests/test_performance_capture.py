"""A quantized initial CPU tick must not become a false performance spike."""
import importlib.util,sys,unittest
from pathlib import Path
from types import SimpleNamespace

@unittest.skipUnless(sys.platform=='win32','Windows collector')
class CpuSampling(unittest.TestCase):
    def test_sub_millisecond_interval_is_omitted_then_normal_interval_is_valid(self):
        path=Path(__file__).resolve().parents[1]/'tools/capture_live_performance.py'
        spec=importlib.util.spec_from_file_location('performance_capture',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        p=module.Process.__new__(module.Process);p.pid=1;p.handle=1;p.last=(0.,0.,0,0);ticks=[156250]
        def times(handle,*files):files[2]._obj.dwLowDateTime=ticks[0];return True
        p.k=SimpleNamespace(GetProcessTimes=times,GetProcessIoCounters=lambda *a:True,GetProcessHandleCount=lambda *a:True)
        p.p=SimpleNamespace(GetProcessMemoryInfo=lambda *a:False);p.u=SimpleNamespace(GetGuiResources=lambda *a:0)
        first=p.sample(.0005);self.assertNotIn('cpu_one_core_percent',first)
        ticks[0]+=156250;second=p.sample(1.0005)
        self.assertAlmostEqual(second['cpu_one_core_percent'],1.5625)
