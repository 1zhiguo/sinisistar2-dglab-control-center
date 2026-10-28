"""Export the actual QML HUD as a display-only website animation.

The fixture supplies pixels and numbers only: no Backend, game reader, connection
service or device output is constructed.
"""
from pathlib import Path
import io,json,math,os,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
os.environ.setdefault('QT_QUICK_CONTROLS_STYLE','Basic')
from PySide6.QtCore import QObject,Property,Signal,Slot,QTimer,QUrl,QBuffer,QIODevice,qInstallMessageHandler
from PySide6.QtGui import QGuiApplication,QFont,QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PIL import Image
from sinisistar_dglab.hud_settings import HUD_DEFAULTS
from sinisistar_dglab.simulation import VIBRATION_WAVES

class DisplayFixture(QObject):
    changed=Signal()
    def __init__(self):
        super().__init__();self.at=0.
    @Property(str,constant=True)
    def language(self):return 'zh-CN'
    @Slot(str,str,result=str)
    def translate(self,text,language):return text
    @Property(bool,constant=True)
    def hudAdjusting(self):return False
    @Property('QVariantMap',constant=True)
    def hudSettings(self):return dict(HUD_DEFAULTS,opacity=100,scale=100)
    @Property('QVariantMap',constant=True)
    def simulationSettings(self):return {r+'_cap_'+c:60 for r in ('pulse','vibration') for c in ('a','b')}
    @Property('QVariantList',constant=True)
    def waves(self):return [dict(key='breath',name='烛息 · 呼吸'),dict(key='surge',name='暗潮 · 渐强')]
    @Property('QVariantList',constant=True)
    def vibrationWaves(self):return VIBRATION_WAVES
    @Property('QVariantMap',notify=changed)
    def state(self):return dict(emergency=False,connected=False,ovcConnected=False,outputChannels={},ovcChannels={})
    @staticmethod
    def value(key,t):
        phase=2*math.pi*t/8
        wave={'pulseA':(22,12,4,0),'pulseB':(30,15,2,1.1),
              'vibrationA':(30,20,4,.5),'vibrationB':(40,20,2,math.pi/2)}[key]
        result=wave[0]+wave[1]*math.sin(wave[2]*phase+wave[3])
        return int(result//10)*10 if key.startswith('vibration') else round(result)
    @Property('QVariantMap',notify=changed)
    def simulation(self):
        keys=('pulseA','pulseB','vibrationA','vibrationB')
        amounts={key:self.value(key,self.at) for key in keys}
        return dict(running=True,**amounts,peaks=amounts,
            traces={key:[self.value(key,self.at-(63-i)/20)/100 for i in range(64)] for key in keys},
            selected={key:['A 演示' if key.endswith('A') else 'B 演示'] for key in keys},
            active=[dict(name='A 演示',pulse_wave='breath',vibration_wave='vib_surf'),
                    dict(name='B 演示',pulse_wave='surge',vibration_wave='vib_beat')])

def main():
    out=ROOT/'website/dist/assets';out.mkdir(parents=True,exist_ok=True)
    report_dir=ROOT/'artifacts/website-validation';report_dir.mkdir(parents=True,exist_ok=True)
    app=QGuiApplication([])
    for name in ('msyh.ttc','msyhbd.ttc','msyhui.ttc','georgia.ttf'):
        path=Path(os.environ.get('SystemRoot','C:/Windows'))/'Fonts'/name
        if path.is_file():QFontDatabase.addApplicationFont(str(path))
    app.setFont(QFont('Microsoft YaHei UI',10))
    errors=[];qInstallMessageHandler(lambda k,c,m:errors.append(m))
    fixture=DisplayFixture();engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',fixture)
    engine.load(QUrl.fromLocalFile(str(ROOT/'src/sinisistar_dglab/qml/Monitor.qml')))
    if not engine.rootObjects():raise RuntimeError(errors)
    window=engine.rootObjects()[0];window.setPosition(40,40);window.setVisible(True)
    frames=[];count=100;frame_ms=80;pending=False
    def capture():
        nonlocal pending
        qimage=window.grabWindow()
        if qimage.isNull():raise RuntimeError('HUD capture returned no pixels')
        buffer=QBuffer();buffer.open(QIODevice.WriteOnly);qimage.save(buffer,'PNG')
        frame=Image.open(io.BytesIO(bytes(buffer.data()))).convert('RGBA')
        matte=Image.new('RGBA',frame.size,'#11100e');matte.alpha_composite(frame)
        frames.append(matte.convert('RGB'));pending=False
        if len(frames)==count:timer.stop();window.setVisible(False);app.quit()
    def advance():
        nonlocal pending
        if pending:return
        pending=True;fixture.at=len(frames)*frame_ms/1000;fixture.changed.emit();QTimer.singleShot(35,capture)
    timer=QTimer();timer.setInterval(frame_ms);timer.timeout.connect(advance)
    QTimer.singleShot(250,timer.start);QTimer.singleShot(20000,app.quit);app.exec()
    assert len(frames)==count,len(frames)
    bad=[m for m in errors if any(s in m for s in ('ReferenceError','TypeError','Cannot assign','is not a type','Binding loop'))]
    assert not bad,bad
    palette=frames[0].quantize(colors=256)
    indexed=[frame.quantize(palette=palette,dither=Image.Dither.NONE) for frame in frames]
    target=out/'hud-demo.gif'
    indexed[0].save(target,save_all=True,append_images=indexed[1:],duration=frame_ms,loop=0,optimize=True,disposal=1)
    frames[20].save(out/'hud-demo-poster.png',optimize=True)
    with Image.open(target) as gif:
        assert gif.n_frames==count and gif.size==frames[0].size
        duration=sum((gif.seek(i),gif.info['duration'])[1] for i in range(gif.n_frames))
    report=dict(passed=True,frames=count,duration_ms=duration,size=frames[0].size,bytes=target.stat().st_size,
        source='Actual Monitor.qml / OutputHudWindow.qml with a display-only fixture',
        hardware_connected=False,game_reader_started=False,device_services_started=False,qml_errors=bad,
        per_channel_ranges={key:[min(fixture.value(key,i*.08) for i in range(count)),max(fixture.value(key,i*.08) for i in range(count))] for key in ('pulseA','pulseB','vibrationA','vibrationB')})
    (report_dir/'hud-demo.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
