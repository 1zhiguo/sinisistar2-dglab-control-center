"""Close the native main window with auxiliary windows open; loopback only."""
import argparse,asyncio,json,queue,socket,sys,tempfile,threading,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from PySide6.QtCore import QTimer,QUrl
from PySide6.QtGui import QGuiApplication,QFont
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from sinisistar_dglab.backend import Backend
from sinisistar_dglab.v4 import V4ConnectionService
from sinisistar_dglab.mock_v4 import MockV4App

parser=argparse.ArgumentParser();parser.add_argument('--output',default='exit');args=parser.parse_args()
app=QGuiApplication([]);app.setFont(QFont('Microsoft YaHei UI',10))
temp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp')
b=Backend(offline=True,settings=Path(temp.name)/'settings.json');b._timer.stop()
hub=V4ConnectionService(port=0,host='127.0.0.1',lan_ip='127.0.0.1');hub.start()
b._v4=hub;b._service=hub.channel('pulse');b._ovc_service=hub.channel('ovc')
engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',b)
engine.load(QUrl.fromLocalFile(str(ROOT/'src/sinisistar_dglab/qml/ControlCenter.qml')))
w=engine.rootObjects()[0]
engine.load(QUrl.fromLocalFile(str(ROOT/'src/sinisistar_dglab/qml/Monitor.qml')))
hud=engine.rootObjects()[1];hud.setVisible(True);b.openEventDetector()
app.aboutToQuit.connect(b.shutdown);app.aboutToQuit.connect(lambda:hud.setVisible(False))
b.exitRequested.connect(lambda:app.exit(0))
stop=threading.Event();ready=threading.Event();records=[];phones=[];thread_errors=[];port=0;closed=False;blocked=False;steps=[];close_cursor=0
async def client():
    phone=None
    try:
        end=time.monotonic()+3
        while not hub.snapshot().get('server_ready') and time.monotonic()<end:await asyncio.sleep(.01)
        state=hub.snapshot()
        steps.append(('server',state['port']))
        phone=await MockV4App().connect(f"ws://127.0.0.1:{state['port']}/?tid={state['controller_id']}")
        phones.append(phone)
        while len(hub.devices_snapshot())<2 and time.monotonic()<end:await asyncio.sleep(.01)
        for role,slot in (('pulse','coyote'),('ovc','ovc')):hub.select_device(role,phone.client_id,slot)
        while not all(hub.channel(r).snapshot()['connected'] for r in ('pulse','ovc')) and time.monotonic()<end:await asyncio.sleep(.01)
        ready.set()
        steps.append(('paired',len(phone.records)))
        while not stop.is_set():await asyncio.sleep(.01)
    except Exception:thread_errors.append(traceback.format_exc());ready.set()
    finally:
        if phone:records.extend(phone.records);await phone.close()
thread=threading.Thread(target=lambda:asyncio.run(client()),daemon=True);thread.start()
started=time.monotonic()
def close_main():
    global port,closed,blocked
    if not ready.is_set():QTimer.singleShot(20,close_main);return
    if thread_errors:print(thread_errors);app.exit(2);return
    steps.append(('close_main',time.monotonic()-started))
    port=hub.snapshot()['port']
    # Installation must keep the main window and service alive.
    b._install_state.update(busy=True,phase='install');b.installChanged.emit();w.close();blocked=w.isVisible() and hub.snapshot()['server_ready']
    b._install_state.update(busy=False,phase='idle');b.installChanged.emit()
    for role in ('pulse','ovc'):
        route=hub.channel(role);assert route.set_output_permission(True,hard_limits=dict(A=50,B=50))
        route.submit_plan({c:dict(peak=10 if role=='pulse' else 30,samples=[10 if role=='pulse' else 30]*4,frequencies=[30]*4) for c in 'AB'})
    def accepted_close():
        global close_cursor
        close_cursor=len(phones[0].records)
        steps.append(('accepted_close',b.installState['busy'],w.isVisible()));w.close();steps.append(('closed',w.isVisible()))
    QTimer.singleShot(120,accepted_close)
def timed_out():
    global closed
    closed=True;app.exit(1)
QTimer.singleShot(250,close_main);QTimer.singleShot(5500,timed_out)
code=app.exec();elapsed=time.monotonic()-started
stop.set();thread.join(2)
probe=socket.socket();probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
try:probe.bind(('127.0.0.1',port));port_reusable=True
except OSError:port_reusable=False
finally:probe.close()
zeros={slot:{r['data'].get('c') for r in records[close_cursor:] if r.get('m')=='device.op' and r['data'].get('s')==slot and r['data'].get('t')==7 and r['data'].get('v')==0} for slot in ('coyote','ovc')}
report=dict(passed=code==0 and not closed and blocked and port_reusable and not hub._hub._thread.is_alive() and all(v=={0,1} for v in zeros.values()),
    exited_without_timeout=not closed,install_close_blocked=blocked,elapsed_seconds=round(elapsed,2),
    listener_stopped=not hub.snapshot()['server_ready'],port_reusable=port_reusable,thread_stopped=not hub._hub._thread.is_alive(),
    zero_channels={k:sorted(v) for k,v in zeros.items()},errors=thread_errors,steps=steps,ready=ready.is_set(),hardware_connected=False)
out=ROOT/'artifacts/shutdown-validation';out.mkdir(parents=True,exist_ok=True)
(out/(args.output+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
(out/(args.output+'-requests.json')).write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(report))
b.shutdown();temp.cleanup();raise SystemExit(0 if report['passed'] else 1)
