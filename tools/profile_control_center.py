"""Offline UI workload with live-shaped callbacks; no transports or game writes."""
import argparse,cProfile,io,json,pstats,queue,sys,tempfile,time
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from PySide6.QtCore import QTimer,QUrl,qInstallMessageHandler
from PySide6.QtGui import QGuiApplication,QFont
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
from sinisistar_dglab.backend import Backend
from sinisistar_dglab.simulation import demo_state

parser=argparse.ArgumentParser();parser.add_argument('--output',default='current');args=parser.parse_args()
app=QGuiApplication([]);app.setFont(QFont('Microsoft YaHei UI',10));messages=[]
qInstallMessageHandler(lambda kind,ctx,msg:messages.append(msg))
temp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp')
b=Backend(offline=True,settings=Path(temp.name)/'settings.json');b._timer.stop()
class Game:
    def __init__(self):self.events=queue.Queue();self.sequence=0
    def snapshot(self):
        self.sequence+=1;s=demo_state('idle',0,time.monotonic())
        s.update(source='bepinex',session='performance-fixture',pid=123,player=456,sample_id=self.sequence,scene_id=289,
                 flow=dict(valid=True,playing=True,key='[289,"Event","Main","HierarchyEventPlayer"]',
                     group='Event',name='Main',type='HierarchyEventPlayer',run=1,label='Go_Loop1'))
        return s
    def recent_events(self,session):return []
    def stop(self):pass
game=Game();b._observer=game
p=ROOT/'artifacts/observed-flows.json'
if p.exists():b._flows.items={x['key']:x for x in json.loads(p.read_text(encoding='utf8'))}
engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',b)
engine.load(QUrl.fromLocalFile(str(ROOT/'src/sinisistar_dglab/qml/ControlCenter.qml')))
w=engine.rootObjects()[0];results=[]
def run():
    profiler=cProfile.Profile()
    try:
        for page in (1,2,5,6):
            w.setProperty('pageIndex',page);QTest.qWait(420);durations=[];notices=[]
            def notice():notices.append(1)
            b.eventsChanged.connect(notice)
            profiler.enable()
            for tick in range(20):
                for i in range(8):
                    game.events.put(dict(event_type='flow_label_callback',session='performance-fixture',pid=123,player=456,
                        sequence=page*10000+tick*8+i,utc=datetime.now(timezone.utc).isoformat(),label='Go_Loop1',label_type='SendDamageLabel'))
                started=time.perf_counter();b.tick();app.processEvents();durations.append((time.perf_counter()-started)*1000)
            profiler.disable();b.eventsChanged.disconnect(notice)
            results.append(dict(page=page,ticks=20,callbacks=160,event_notifications=len(notices),
                mean_ms=round(sum(durations)/len(durations),2),p95_ms=round(sorted(durations)[18],2),max_ms=round(max(durations),2)))
        report=dict(cases=results,hardware_connected=False,device_services_started=False,qml_errors=messages)
        out=ROOT/'artifacts/performance';out.mkdir(parents=True,exist_ok=True)
        (out/(args.output+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
        stream=io.StringIO();pstats.Stats(profiler,stream=stream).strip_dirs().sort_stats('cumulative').print_stats(35)
        (out/(args.output+'.txt')).write_text(stream.getvalue(),encoding='utf8')
        print(json.dumps(report));print(stream.getvalue());app.exit(0)
    except Exception:
        import traceback;traceback.print_exc();app.exit(1)
QTimer.singleShot(500,run)
code=app.exec();b.shutdown();w.close();engine.deleteLater();app.processEvents();temp.cleanup();raise SystemExit(code)
