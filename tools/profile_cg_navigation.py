"""Measure CG rendering and page changes offline, without transport services."""
import argparse,cProfile,io,json,pstats,queue,sys,tempfile,time
from copy import deepcopy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from PySide6.QtCore import QTimer,QUrl,qInstallMessageHandler
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest
from sinisistar_dglab.backend import Backend

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='cg-navigation');parser.add_argument('--worker',action='store_true');args=parser.parse_args()
    app=QGuiApplication([]);messages=[];qInstallMessageHandler(lambda kind,ctx,msg:messages.append(msg))
    temp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp')
    b=Backend(offline=True,settings=Path(temp.name)/'settings.json');b._timer.stop();b._connection['auto_enable']=False
    fixture=json.loads((ROOT/'tests/fixtures/gallery-0.4.2.json').read_text(encoding='utf-8'))[2]
    b._sim_profile['gallery']['rule']['enabled']=True
    class Game:
        events=queue.Queue()
        sequence=0
        def snapshot(self):
            self.sequence+=1;s=deepcopy(fixture);s.update(sampled_at=time.monotonic(),sample_id=self.sequence,live=True);return s
        def recent_events(self,session):return []
        def stop(self):pass
    class ViewOnly:
        events=queue.Queue()
        def snapshot(self):return dict(connected=True,feedback_known=True,limit_a=90,limit_b=90,local_only=True)
        def set_output_permission(self,*args,**kwargs):return False
        def emergency_zero(self):pass
        def stop(self):pass
    b._observer=Game();b._service=ViewOnly();b._ovc_service=ViewOnly();b._armed=b._ovc_armed=True
    if args.worker:b._start_output_worker()
    engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',b)
    engine.load(QUrl.fromLocalFile(str(ROOT/'src/sinisistar_dglab/qml/ControlCenter.qml')))
    w=engine.rootObjects()[0];results=[];profiler=cProfile.Profile()
    def run():
        try:
            for page in (7,3,2,1,7,5,0,7):
                profiler.enable();start=time.perf_counter();w.setProperty('pageIndex',page);app.processEvents()
                load=(time.perf_counter()-start)*1000;profiler.disable();QTest.qWait(450)
                durations=[];profiler.enable()
                for _ in range(15):
                    start=time.perf_counter();b.tick();app.processEvents();durations.append((time.perf_counter()-start)*1000)
                profiler.disable()
                results.append(dict(page=page,load_ms=round(load,2),mean_tick_ms=round(sum(durations)/len(durations),2),max_tick_ms=round(max(durations),2)))
            out=ROOT/'artifacts/performance';out.mkdir(exist_ok=True)
            report=dict(cases=results,hardware_connected=False,device_services_started=False,qml_errors=messages,
                worker={k:v for k,v in b._output_worker.snapshot().items() if k not in ('pulse','ovc')} if b._output_worker else {})
            (out/(args.output+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            stream=io.StringIO();pstats.Stats(profiler,stream=stream).strip_dirs().sort_stats('cumulative').print_stats(40)
            (out/(args.output+'.txt')).write_text(stream.getvalue(),encoding='utf-8');print(json.dumps(report,ensure_ascii=False));app.exit(0)
        except Exception:
            import traceback;traceback.print_exc();app.exit(1)
    QTimer.singleShot(400,run);code=app.exec();b.shutdown();engine.deleteLater();app.processEvents();temp.cleanup();return code

if __name__=='__main__':raise SystemExit(main())
