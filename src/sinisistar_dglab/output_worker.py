"""Fresh-state planning independent of the Qt event loop and journal writes.

The worker owns its clocks/evidence. Configuration is copied only on edits;
controls and revocations share the same lock as plan submission. Transport
leases remain unchanged and no missed frames are replayed.
"""
from copy import deepcopy
import queue
import threading
import time
import sys
from types import SimpleNamespace
from .events import EventDetector
from .locked_hp import LockedHpEvidence
from .same_hp import SameHpFlowEvidence
from .pulse import PulsePlanner
from .ovc_plan import OvcPlanner
from .output_runtime import plan_outputs


class OutputWorker:
    INTERVAL = .08

    def __init__(self,on_panic=None,key_down=None):
        self._lock=threading.RLock();self._stop=threading.Event();self._thread=None
        self._observer=None;self._panic=False;self._error='';self._ticks=0;self._max_ms=0.
        self._on_panic=on_panic;self._shortcut={};self._hotkey_active=False;self._key_held=False
        if key_down is None and sys.platform=='win32':
            import ctypes
            user=ctypes.WinDLL('user32',use_last_error=True)
            key_down=lambda vk:bool(user.GetAsyncKeyState(vk)&0x8000)
        self._key_down=key_down
        self._locked_hp=LockedHpEvidence();self._same_hp=SameHpFlowEvidence()
        self.c=SimpleNamespace(_pulse_planner=PulsePlanner(),_ovc_planner=OvcPlanner(),_detector=EventDetector(),
            _warm=0,_stamp=None,_identity=None,_ovc_warm=0,_ovc_stamp=None,_ovc_identity=None,
            _service=None,_ovc_service=None,_armed=False,_ovc_armed=False,_emergency=False,
            _sim_running=False,_sim_source='live',_reason='输出已暂停')
        self.c._pulse_plan=self.c._pulse_planner.engine.blank('Pulse 已暂停')
        self.c._ovc_plan=self.c._ovc_planner.engine.blank('负鼠已暂停')

    def configure(self,profile,waves,vibration_custom,channels,ovc_limits):
        values=deepcopy((profile,waves,vibration_custom,channels,ovc_limits))
        with self._lock:
            c=self.c
            c._sim_profile,c._waves,c._vibration_custom,c._channels,c._ovc_limits=values

    def controls(self,*,observer,service,ovc_service,armed,ovc_armed,emergency,sim_running,sim_source,connection,pulse_channels,ovc_channels,shortcut=None,hotkey_active=False):
        with self._lock:
            self._shortcut=dict(shortcut or {});self._hotkey_active=hotkey_active
            c=self.c
            if observer is not self._observer:
                self._observer=observer;self._locked_hp=LockedHpEvidence();self._same_hp=SameHpFlowEvidence()
                c._identity=c._ovc_identity=None
            for key,value in dict(_service=service,_ovc_service=ovc_service,_armed=armed,_ovc_armed=ovc_armed,
                    _emergency=emergency or self._panic,_sim_running=sim_running,_sim_source=sim_source,
                    _connection=dict(connection),_pulse_channels=dict(pulse_channels),_ovc_channels=dict(ovc_channels)).items():
                old=getattr(c,key,None)
                if key in ('_service','_ovc_service') and old is not value and old:
                    old.set_output_permission(False,'输出连接已更换')
                if key in ('_armed','_ovc_armed') and old and not value:
                    self._revoke('pulse' if key=='_armed' else 'ovc')
                setattr(c,key,value)

    def _revoke(self,role):
        c=self.c;ovc=role=='ovc';service=c._ovc_service if ovc else c._service
        planner=c._ovc_planner if ovc else c._pulse_planner;planner.reset()
        if ovc:c._ovc_warm=0;c._ovc_stamp=None;c._ovc_plan=planner.engine.blank('负鼠已暂停')
        else:c._warm=0;c._stamp=None;c._pulse_plan=planner.engine.blank('Pulse 已暂停')
        if service:service.set_output_permission(False,'配置或运行状态变化')

    def invalidate(self,*,ovc=True):
        with self._lock:
            self.c._armed=False;self._revoke('pulse')
            if ovc:self.c._ovc_armed=False;self._revoke('ovc')

    def panic(self):
        with self._lock:
            self._panic=True;self.c._emergency=True;self.invalidate()
            for service in (self.c._service,self.c._ovc_service):
                if service:
                    (service.latch_emergency_stop if hasattr(service,'latch_emergency_stop') else service.emergency_zero)()

    def unlock(self):
        with self._lock:
            self.invalidate();self._panic=False;self.c._emergency=False

    def step(self):
        with self._lock:
            c=self.c
            if not hasattr(c,'_sim_profile'):return
            measured=time.perf_counter();start=time.monotonic();s=self._observer.snapshot() if self._observer else {}
            callbacks=[];events=getattr(self._observer,'output_events',None)
            if events:
                for _ in range(100):
                    try:callbacks.append(events.get_nowait())
                    except queue.Empty:break
            s=self._locked_hp.update(s,callbacks,now=start)
            s=self._same_hp.update(s,callbacks,now=start)
            s.setdefault('feedback_evidence',{})['same_hp_timeout']=(c._sim_profile.get('cg') or {}).get('same_hp_timeout',3.)
            plan_outputs(c,s,start)
            self._ticks+=1;self._max_ms=max(self._max_ms,(time.perf_counter()-measured)*1000)

    def snapshot(self):
        with self._lock:
            return dict(pulse=self.c._pulse_plan,ovc=self.c._ovc_plan,reason=self._error or self.c._reason,
                        ticks=self._ticks,max_ms=round(self._max_ms,3),error=self._error)

    def start(self):
        if self._thread and self._thread.is_alive():return
        self._stop.clear();self._thread=threading.Thread(target=self._run,name='GameFeedbackPlanner',daemon=True);self._thread.start()

    def _check_hotkey(self):
        # Poll only the configured emergency chord, including during a Qt stall.
        # Recording the shortcut suspends this path, just like RegisterHotKey.
        with self._lock:
            key=self._shortcut;down=self._key_down
            held=bool(self._hotkey_active and down and key.get('vk') and down(key['vk']))
            if held:
                mods=(2 if down(0x11) else 0)|(4 if down(0x10) else 0)|(1 if down(0x12) else 0)|(8 if down(0x5b) or down(0x5c) else 0)
                held=mods==key.get('modifiers',0)
            pressed=held and not self._key_held;self._key_held=held
            if pressed:self.panic()
        if pressed and self._on_panic:self._on_panic()

    def _run(self):
        next_plan=0.
        while not self._stop.is_set():
            try:
                self._check_hotkey()
                if time.monotonic()>=next_plan:
                    self.step();next_plan=time.monotonic()+self.INTERVAL
            except Exception as error:
                with self._lock:
                    self._error='输出线程已停止：'+str(error);self.panic()
                if self._on_panic:self._on_panic()
                return
            self._stop.wait(.01)

    def close(self):
        self._stop.set();self.invalidate()
        if self._thread:self._thread.join(2)
