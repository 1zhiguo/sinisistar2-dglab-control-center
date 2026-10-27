"""Native QML navigation + four-channel loopback continuity, isolated settings.

Can load a preserved source tree for a controlled before/after comparison.
Never uses PluginObserver, BLE, hardware routes, or real game commands.
"""
import argparse,json,os,queue,sys,time,threading,statistics,traceback
from pathlib import Path
from copy import deepcopy
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,default=ROOT/'src');parser.add_argument('--out',type=Path,required=True)
parser.add_argument('--seconds',type=float,default=300);args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(args.source));sys.path.insert(1,str(ROOT/'tools'))
from PySide6.QtCore import QTimer,QUrl,Qt,qInstallMessageHandler
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from sinisistar_dglab.backend import Backend
from capture_live_performance import Process,Nvml,GpuCounters,stamp

fixtures=json.loads((ROOT/'tests/fixtures/gallery-0.4.2.json').read_text(encoding='utf-8'))
class Game:
    def __init__(self):self.events=queue.Queue();self.output_events=queue.Queue();self.index=2;self.seq=0;self.lock=threading.Lock();self.stopped=False
    def snapshot(self):
        with self.lock:
            self.seq+=1;s=deepcopy(fixtures[self.index]);s.update(live=True,sampled_at=time.monotonic(),sample_id=self.seq)
            return s
    def recent_events(self,session):return []
    def stop(self):self.stopped=True

def quantile(values,q):
    vals=sorted(values);return vals[int((len(vals)-1)*q)] if vals else None

app=QGuiApplication([]);messages=[];qInstallMessageHandler(lambda k,c,m:messages.append(dict(at=time.perf_counter(),text=m)))
b=Backend(offline=True,settings=args.out/'settings.json');b._connection['auto_enable']=False
original=json.loads((ROOT/'artifacts/settings.json').read_text(encoding='utf-8'))
from sinisistar_dglab.simulation import sanitize_profile
b._sim_profile=sanitize_profile(original['simulation']);b._sim_profile['cg_detection_mode']='playback_only'
g=b._sim_profile['gallery'];g['rule'].update(enabled=True,pulse_enabled=True,vibration_enabled=True,pulse_channel='AB',vibration_channel='AB')
for route in ('pulse','vibration'):b._sim_profile['channel_feedback'][route]={c:'both' for c in 'AB'}
b._channels=[dict(key=c,limit=b._sim_profile['pulse_cap_'+c.lower()],frequency=30) for c in 'AB']
b._ovc_limits={c:b._sim_profile['vibration_cap_'+c.lower()] for c in 'AB'}
game=Game();b._observer=game;b.offline=False;b._start_output_worker();b.beginCgBatch();b.startMockBoth();session=b._mock_session
engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',b)
engine.load(QUrl.fromLocalFile(str(args.source/'sinisistar_dglab/qml/ControlCenter.qml')))
if not engine.rootObjects():raise RuntimeError(str(messages))
w=engine.rootObjects()[0];w.setTitle('SiNiSistar2 · 本机性能与持续发送验证');w.setProperty('pageIndex',7)
w.show();w.raise_();w.requestActivate()
frame_times=[];frame_lock=threading.Lock()
def swapped():
    with frame_lock:frame_times.append(time.perf_counter())
w.frameSwapped.connect(swapped,Qt.DirectConnection)
proc=Process(os.getpid());gpu=Nvml();engines=GpuCounters();resources=[];marks=[];blocks=[];page_times=[];stopped=False;start=None;last_page=-1;last_cg=-1;blocked=set();actions=set()
(args.out/'pid.json').write_text(json.dumps(dict(pid=os.getpid(),source=str(args.source),local_only=True,duration=args.seconds)),encoding='utf-8')
def mark(kind,**fields):marks.append(dict(kind=kind,at=time.perf_counter(),elapsed=time.perf_counter()-start,**fields))
def counts():return {k:session.snapshot().get(k,0) for k in ('pulsesA','pulsesB','ovcPulsesA','ovcPulsesB')}

def finish():
    global stopped
    if stopped:return
    stopped=True;timer.stop();elapsed=time.perf_counter()-start
    receipt=counts();worker=b._output_worker.snapshot();loop_passes={r:b._v4.channel(r)._loop_passes if hasattr(b._v4.channel(r),'_loop_passes') else None for r in ('pulse','ovc')}
    b.shutdown();proc.close();gpu.close();engines.close()
    def expected(a,z):return any(m['at']-1<=z and m['at']+1.3>=a for m in marks if m['kind'] in ('cg_switch','pause','resume','emergency','emergency_resume','intentional_gui_block'))
    records=[json.loads(line) for line in (session.directory/'commands.jsonl').read_text(encoding='utf-8').splitlines()]
    streams={}
    for slot in ('coyote','ovc'):
        for channel in (0,1):
            times=[r['at'] for r in records if r.get('m')=='device.op' and (r.get('data') or {}).get('s')==slot and r['data'].get('t')==0 and r['data'].get('c')==channel]
            gaps=[(y-x)*1000 for x,y in zip(times,times[1:]) if not expected(x,y)]
            streams[slot+('B' if channel else 'A')]=dict(received=len(times),steady_gap_p95_ms=quantile(gaps,.95),steady_gap_max_ms=max(gaps,default=0),steady_gaps_over_250ms=sum(v>250 for v in gaps))
    with frame_lock:frames=list(frame_times)
    frame_gaps=[(z-a)*1000 for a,z in zip(frames,frames[1:]) if not any(m['at']-0.05<=z and m['at']+.9>=a for m in marks if m['kind']=='intentional_gui_block')]
    cpu=[p['cpu_one_core_percent'] for r in resources for p in [r['process']] if r['elapsed']>=.1 and 'cpu_one_core_percent' in p]
    power=[r['board'].get('board_power_w') for r in resources if 'board_power_w' in r['board']]
    errors=[m for m in messages if any(x in m['text'] for x in ('ReferenceError','TypeError','Binding loop','Unable to assign','Cannot assign','is not a type'))]
    report=dict(local_only=True,hardware_connected=False,source=str(args.source),seconds=elapsed,receipts=receipt,streams=streams,loop_passes=loop_passes,
        cpu_one_core_mean=statistics.mean(cpu) if cpu else None,cpu_one_core_p95=quantile(cpu,.95),board_power_mean_w=statistics.mean(power) if power else None,
        frame_gap_p95_ms=quantile(frame_gaps,.95),frame_gap_max_ms=max(frame_gaps,default=0),frames_over_250ms=sum(v>250 for v in frame_gaps),
        frames=len(frames),blocks=blocks,marks=marks,page_creation_ms=page_times,worker={k:v for k,v in worker.items() if k not in ('pulse','ovc')},
        qml_errors=errors,mock_error=session.snapshot()['error'],mock_session=str(session.directory),notes='Steady stream gaps exclude declared CG switch/pause/emergency windows; intentional 700ms GUI blocks must still receive four-channel packets.')
    report['passed']=not errors and not report['mock_error'] and all(v['received']>5 and not v['steady_gaps_over_250ms'] for v in streams.values()) and all(all(x>=3 for x in block['received'].values()) for block in blocks)
    (args.out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (args.out/'resources.json').write_text(json.dumps(resources,ensure_ascii=False),encoding='utf-8')
    (args.out/'frames.json').write_text(json.dumps(frames),encoding='utf-8')
    (args.out/'messages.json').write_text(json.dumps(messages,ensure_ascii=False,indent=2),encoding='utf-8')
    app.exit(0 if report['passed'] else 1)

last_resource=-1
def step():
    global start,last_page,last_cg,last_resource
    if start is None:
        if not all(v>0 for v in counts().values()):return
        start=time.perf_counter();mark('start');proc.sample(start)
        (args.out/'started.json').write_text(json.dumps(dict(utc=stamp(),pid=os.getpid())),encoding='utf-8')
    elapsed=time.perf_counter()-start
    if elapsed>=args.seconds:finish();return
    page=int(elapsed//6)
    if page!=last_page:
        last_page=page;index=(7,2,3,1,5,0)[page%6];t=time.perf_counter();w.setProperty('pageIndex',index);page_times.append(dict(elapsed=elapsed,page=index,setter_ms=(time.perf_counter()-t)*1000));mark('page',page=index)
    cg=int(elapsed//30)
    if cg!=last_cg:last_cg=cg;game.index=2 if cg%2==0 else 4;mark('cg_switch',index=game.index)
    if int(elapsed)!=last_resource:
        last_resource=int(elapsed);now=time.perf_counter();resources.append(dict(utc=stamp(),elapsed=elapsed,process=proc.sample(now),board=gpu.sample(),engines=engines.sample([os.getpid()])))
        (args.out/'progress.json').write_text(json.dumps(dict(elapsed=elapsed,pid=os.getpid(),counts=counts(),worker_ticks=b._output_worker.snapshot()['ticks'])),encoding='utf-8')
    for at in (40,100,160,220,280):
        if elapsed>=at and at not in blocked:
            blocked.add(at);before=counts();mark('intentional_gui_block');time.sleep(.7);after=counts()
            blocks.append(dict(at=at,received={k:after[k]-v for k,v in before.items()}))
    if elapsed>=120 and 'pause' not in actions:
        actions.add('pause');mark('pause');game.index=7
    if elapsed>=121 and 'resume' not in actions:
        actions.add('resume');mark('resume');game.index=2
    if elapsed>=200 and 'emergency' not in actions:
        actions.add('emergency');mark('emergency');b.emergencyStop()
    if elapsed>=201 and 'emergency_resume' not in actions:
        actions.add('emergency_resume');mark('emergency_resume');b.resumeAfterEmergency()

timer=QTimer();timer.setInterval(50);timer.timeout.connect(step);timer.start()
watchdog=QTimer();watchdog.setSingleShot(True)
def failed_start():
    if start is None:
        (args.out/'startup-error.json').write_text(json.dumps(dict(messages=messages,mock=b.mockValidation),ensure_ascii=False,indent=2),encoding='utf-8');b.shutdown();app.exit(2)
watchdog.timeout.connect(failed_start);watchdog.start(15000)
app.aboutToQuit.connect(b.shutdown)
raise SystemExit(app.exec())
