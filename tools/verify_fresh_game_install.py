"""Explicit fresh-game integration check through the production QML install button.

Only run --install for a user-authorized fresh extraction. No device service is
started and this script does not launch the game or alter save data.
"""
from __future__ import annotations
import argparse,json,sys,time,traceback
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-dir',required=True,type=Path)
    parser.add_argument('--install',action='store_true')
    args=parser.parse_args()
    if not args.install:parser.error('Explicit --install is required for this mutating check')
    from PySide6.QtCore import QObject,QMetaObject,QTimer,QUrl,qInstallMessageHandler
    from PySide6.QtGui import QGuiApplication,QFont
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickItem,QQuickWindow
    from sinisistar_dglab.backend import Backend
    from sinisistar_dglab.install_manager import InstallManager
    manager=InstallManager();target=args.game_dir.resolve();inspection=manager.inspect_game(target)
    assert inspection['detected'] and inspection['supported'] and not inspection['running'],inspection
    assert not (target/'BepInEx').exists() and not (target/'winhttp.dll').exists(),'This check requires a fresh extraction'
    baseline={str(p.relative_to(target)):(p.stat().st_size,p.stat().st_mtime_ns) for p in target.rglob('*') if p.is_file()}
    output=ROOT/'artifacts/fresh-game-validation';output.mkdir(parents=True,exist_ok=True)
    report={'checked_utc':datetime.now(timezone.utc).isoformat(),'target':str(target),'before':inspection,'baseline_files':len(baseline),'hardware_connected':False,'output_armed':False}
    messages=[]
    qInstallMessageHandler(lambda kind,context,message:messages.append(message))
    app=QGuiApplication([]);app.setFont(QFont('Microsoft YaHei UI',10))
    backend=Backend(offline=False);app.aboutToQuit.connect(backend.shutdown)
    engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',backend)
    engine.load(QUrl.fromLocalFile(str(ROOT/'src/sinisistar_dglab/qml/ControlCenter.qml')))
    assert engine.rootObjects(),messages
    window=engine.rootObjects()[0];window.resize(1440,940);window.setProperty('pageIndex',1)
    stage={'name':'scan'};started=time.monotonic()
    def finish(ok):
        timer.stop();report.update(passed=ok,qml_messages=messages)
        (output/'installation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'passed':ok,'report':str(output/'installation.json'),'new_files':report.get('new_files'),'error':report.get('error')}),flush=True)
        app.exit(0 if ok else 1)
    def tick():
        try:
            assert backend._service is None and backend._ovc_service is None and backend._v4 is None
            assert not backend._armed and not backend._ovc_armed
            state=backend.installState
            if time.monotonic()-started>120:raise TimeoutError('Fresh installation UI did not finish')
            if state['busy']:return
            if state.get('error'):raise RuntimeError(state['error'])
            if stage['name']=='scan':
                if not backend.gameCandidates:return
                assert Path(state['selectedPath']).resolve()==target,backend.gameCandidates
                assert state['valid'] and state['payloadReady'] and not state['gameRunning'] and not state['installedVersion'],state
                report['automatic_candidates']=backend.gameCandidates;report['automatically_selected']=True
                assert window.grabWindow().save(str(output/'before-install.png'))
                button=window.findChild(QObject,'installGamePluginButton')
                assert button is not None and button.property('enabled')
                stage['name']='install'
                assert QMetaObject.invokeMethod(button,'clicked'),'Could not activate production install button'
                report['qml_button_invoked']=True
                print('Production QML install button activated',flush=True)
            elif stage['name']=='install':
                assert state['needsRestart'] and state['progress']==100 and state['installedVersion']=='0.4.2',state
                assert not state['pluginOnline'],'File installation is not plugin loading'
                assert window.grabWindow().save(str(output/'after-install.png'))
                changed=[name for name,stat in baseline.items() if not (target/name).is_file() or ((target/name).stat().st_size,(target/name).stat().st_mtime_ns)!=stat]
                assert not changed,changed
                manifest=json.loads((target/'BepInEx/plugins/SiNiSistarDGLab/install-manifest.json').read_text(encoding='utf-8'))
                report.update(after=state,original_files_unchanged=True,installed_manifest=manifest,
                              new_files=sum(p.is_file() for p in target.rglob('*'))-len(baseline),
                              telemetry_directory=str(backend._observer.directory))
                assert not [m for m in messages if 'ReferenceError' in m or 'TypeError' in m or 'file:///' in m],messages
                finish(True)
        except Exception:
            report['error']=traceback.format_exc();finish(False)
    timer=QTimer();timer.setInterval(100);timer.timeout.connect(tick);timer.start()
    return app.exec()

if __name__=='__main__':raise SystemExit(main())
