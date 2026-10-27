"""Verify a copied source distribution without game files or preview caches."""
from pathlib import Path
import json,os,shutil,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[1]
output=ROOT/'artifacts/automatic-preview-validation';output.mkdir(parents=True,exist_ok=True)
child=r'''
from pathlib import Path
import json,sys
from PySide6.QtCore import QTimer,QUrl,qInstallMessageHandler
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem,QQuickWindow
from sinisistar_dglab.backend import Backend
from sinisistar_dglab.telemetry import ROOT
messages=[];qInstallMessageHandler(lambda kind,context,text:messages.append(text))
app=QGuiApplication([]);b=Backend(offline=True,settings=ROOT/'user/settings.json');b._timer.stop()
assert not (ROOT/'SiNiSistar2_v1_3_1').exists() and not (ROOT/'artifacts').exists()
assert b.monsterCatalogSummary['previews']==3571 and b.monsterCatalogSummary['local_previews']==0
assert b._monsters.bundled_complete
assert all(str(ROOT) in row['preview'].replace('file:///','').replace('/',str(chr(92))) for row in b.monsterCatalog if row['preview'])
engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',b)
engine.load(QUrl.fromLocalFile(str(Path(__import__('sinisistar_dglab').__file__).parent/'qml/ControlCenter.qml')))
assert engine.rootObjects(),messages
w=engine.rootObjects()[0];w.setProperty('pageIndex',8)
def finish():
 errors=[m for m in messages if any(k in m for k in ('ReferenceError','TypeError','Cannot open','Error decoding'))]
 report=dict(passed=not errors,copied_distribution=True,no_game=True,no_local_cache=True,previews=b.monsterCatalogSummary['previews'],device_services=False,qml_errors=errors)
 Path(sys.argv[1]).write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report),flush=True)
 assert w.grabWindow().save(sys.argv[2]);app.exit(0 if not errors else 1)
QTimer.singleShot(1500,finish)
result=app.exec();b.shutdown();w.close();engine.deleteLater();app.processEvents();raise SystemExit(result)
'''
with tempfile.TemporaryDirectory(prefix='copied-distribution-',dir=ROOT/'artifacts/test-temp') as directory:
    root=Path(directory).resolve();assert root.is_relative_to((ROOT/'artifacts/test-temp').resolve())
    target=root/'src/sinisistar_dglab'
    shutil.copytree(ROOT/'src/sinisistar_dglab',target,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    script=root/'verify.py';script.write_text(child,encoding='utf8')
    env=dict(os.environ,PYTHONPATH=str(root/'src'),PYTHONIOENCODING='utf8',QT_QPA_PLATFORM='windows')
    result=subprocess.run([sys.executable,str(script),str(output/'copied-distribution-result.json'),str(output/'copied-distribution.png')],cwd=root,env=env,capture_output=True,text=True,encoding='utf8',timeout=60)
    print(result.stdout);print(result.stderr if result.returncode else '');raise SystemExit(result.returncode)
