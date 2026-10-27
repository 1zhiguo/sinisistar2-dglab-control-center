"""Real clean-directory select/install/repair integration; no game/device launch.

Copies only the pinned files needed by the installer and thumbnail builder into
an owned temporary game tree. Exercises production QML buttons, then removes
that verified temporary tree. Original game, saves and control settings untouched.
"""
from pathlib import Path
import gzip,json,shutil,sys,tempfile,time,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from PySide6.QtCore import QTimer,QUrl,QMetaObject,QObject,qInstallMessageHandler
from PySide6.QtGui import QGuiApplication,QFont
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow,QQuickItem
from sinisistar_dglab.backend import Backend
from sinisistar_dglab.install_manager import EXPECTED_BUILD
from sinisistar_dglab.resource_preview import PROFILE

output=ROOT/'artifacts/automatic-preview-validation';output.mkdir(parents=True,exist_ok=True)
source=ROOT/'SiNiSistar2_v1_3_1/WIN'
profile=json.loads(gzip.decompress(PROFILE.read_bytes()))
temporary=tempfile.TemporaryDirectory(prefix='fresh-game-',dir=output)
owned=Path(temporary.name).resolve();assert owned.is_relative_to(output.resolve()) and owned.name.startswith('fresh-game-')
target=owned/'全新游戏 with spaces'/'WIN';target.mkdir(parents=True)
files=set(EXPECTED_BUILD) # No game textures are present in this clean fixture.
for relative in files:
    destination=target/relative;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/relative,destination)
save=target/'SaveData/sentinel.dat';save.parent.mkdir();save.write_bytes(b'keep-save-unchanged')
baseline={p:(p.stat().st_size,p.stat().st_mtime_ns) for p in target.rglob('*') if p.is_file()}
settings=owned/'controller settings/settings.json'
app=QGuiApplication([]);app.setFont(QFont('Microsoft YaHei UI',10));messages=[]
qInstallMessageHandler(lambda kind,ctx,text:messages.append(text))
b=Backend(offline=True,settings=settings)
b.chooseGameDirectory(target.as_uri())
engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',b)
engine.load(QUrl.fromLocalFile(str(ROOT/'src/sinisistar_dglab/qml/ControlCenter.qml')))
assert engine.rootObjects(),messages
w=engine.rootObjects()[0];w.setProperty('pageIndex',1)
started=time.monotonic();stage='select';report=dict(original_game_untouched=True,device_services=False,game_launched=False,temporary_game=str(target),source_files=len(files))
def finish(ok):
    timer.stop();report.update(passed=ok,seconds=round(time.monotonic()-started,2),qml_errors=[m for m in messages if any(x in m for x in ('ReferenceError','TypeError','Binding loop','Cannot assign','Unable to assign'))],unitypy_imported='UnityPy' in sys.modules)
    (output/'clean-install-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(report,ensure_ascii=False),flush=True);app.exit(0 if ok else 1)
def click_install():
    button=w.findChild(QObject,'installGamePluginButton');assert button and button.property('enabled')
    assert QMetaObject.invokeMethod(button,'clicked')
def tick():
    global stage
    try:
        if time.monotonic()-started>180:raise TimeoutError('Automatic preview/install integration timed out')
        assert b._service is None and b._v4 is None and b._ovc_service is None
        assert not b._armed and not b._ovc_armed
        if b.installState['busy']:return
        if b.installState.get('error'):raise RuntimeError(b.installState['error'])
        if b.monsterCacheState.get('error'):raise RuntimeError(b.monsterCacheState['error'])
        if stage=='select':
            assert b.monsterCatalogSummary['previews']==3571 and b.monsterCacheState['ready']
            assert not (target/'BepInEx').exists()
            assert b.monsterCacheState['reused']
            report['directory_selection_has_packaged_previews']=True
            report['game_textures_not_required_for_first_view']=True
            report['pig_entries']=[dict(key=r['key'],preview=bool(r['preview']),images=r['image_count']) for r in b.monsterCatalog if r['key'] in ('PigBG','PigParasite','VillagerMiddleMale_A_Pig')]
            assert all(r['preview'] for r in report['pig_entries'])
            print('Directory selection immediately has 3571 packaged previews; starting production install button',flush=True)
            stage='install';click_install()
        elif stage=='install':
            assert b.installState['installedVersion']=='0.4.2' and b.installState['needsRestart']
            assert b.monsterCacheState['reused']
            assert (target/'BepInEx/plugins/SiNiSistarDGLab/SiNiSistarDGLab.Observer.dll').is_file()
            assert not b.installState.get('pluginOnline',False)
            report['production_qml_install_success']=True;report['install_reused_verified_cache']=True
            stage='repair';click_install()
        elif stage=='repair':
            assert b.monsterCacheState['reused'] and b.installState['progress']==100
            assert all(p.is_file() and (p.stat().st_size,p.stat().st_mtime_ns)==stamp for p,stamp in baseline.items())
            assert save.read_bytes()==b'keep-save-unchanged'
            report['repair_success']=True;report['all_original_copied_files_and_save_unchanged']=True
            report['cache_ready']=b.monsterCacheState;report['cache_previews']=b.monsterCatalogSummary['previews']
            w.setProperty('pageIndex',8);stage='screenshot'
        elif stage=='screenshot':
            assert w.grabWindow().save(str(output/'automatic-catalog.png'))
            finish(True)
    except Exception:report['error']=traceback.format_exc();finish(False)
timer=QTimer();timer.setInterval(100);timer.timeout.connect(tick);timer.start()
result=app.exec();b.shutdown();w.close();engine.deleteLater();app.processEvents()
assert owned.is_relative_to(output.resolve()) and owned.name.startswith('fresh-game-')
temporary.cleanup()
raise SystemExit(result)
