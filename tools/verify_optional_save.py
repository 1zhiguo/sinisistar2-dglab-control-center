"""Exercise optional save import using disposable fixtures, never real saves."""
from pathlib import Path
import json,os,sys,tempfile,time,zipfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from PySide6.QtCore import QObject,QMetaObject,QTimer,QUrl,qInstallMessageHandler
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from sinisistar_dglab.backend import Backend
from sinisistar_dglab.save_import import SaveImporter,PAYLOAD,PAYLOAD_SHA256,decode,encode,digest

def main():
    out=ROOT/'artifacts/save-feature-validation';out.mkdir(parents=True,exist_ok=True)
    checks=[]
    with tempfile.TemporaryDirectory(prefix='save-check-',dir=ROOT/'artifacts/test-temp') as td:
        folder=Path(td);root=folder/'SaveData';root.mkdir();m=SaveImporter(root,process_checker=lambda:False)
        with zipfile.ZipFile(PAYLOAD) as z:system=decode(z.read('System'))
        system['m_KeyConfigText']='personal keys';system['m_SoundSetting']['m_BgmVolume']=3
        system['m_SaveFlagAndVariable']['m_FlagByteArrays'][1]['m_ByteArray'][19]=128
        for name in ('System','SystemSpare'):(root/name).write_bytes(encode(system))
        (root/'File01').write_bytes(b'original character');(root/'FileAuto').write_bytes(b'original auto')
        snapshot=lambda:{p.name:p.read_bytes() for p in root.iterdir() if p.is_file()}
        assert digest(PAYLOAD.read_bytes())==PAYLOAD_SHA256
        before=snapshot();result=m.import_save();assert result['slot']=='File02'
        assert decode((root/'System').read_bytes())==system
        for name,data in before.items():assert (Path(result['backup'])/name).read_bytes()==data
        checks+=['payload integrity','empty-slot selection','preferences and unlocks preserved','verified backups']
        m.restore();assert snapshot()==before;checks+=['byte-exact undo']
        m.process_checker=lambda:True
        try:m.import_save();raise AssertionError('running game accepted')
        except ValueError:pass
        assert snapshot()==before;checks+=['running game blocked'];m.process_checker=lambda:False
        count=[0]
        def fail(src,dst):
            count[0]+=1
            if count[0]==2:raise OSError('fixture disk failure')
            os.replace(src,dst)
        m.replace=fail
        try:m.import_save();raise AssertionError('disk error accepted')
        except OSError:pass
        assert snapshot()==before;checks+=['partial write rollback'];m.replace=os.replace
        m.import_save();first=snapshot();m.import_save();m.restore();assert snapshot()==first
        m.restore();assert snapshot()==before;checks+=['reverse-order undo']
        answers=iter([False,True]);m.process_checker=lambda:next(answers)
        try:m.import_save();raise AssertionError('late launch accepted')
        except ValueError:pass
        assert snapshot()==before;m.process_checker=lambda:False;checks+=['second process check before commit']
        m.import_save();(root/'System').write_bytes(b'new progress');after=snapshot()
        try:m.restore();raise AssertionError('new progress accepted')
        except ValueError:pass
        assert snapshot()==after;checks+=['new progress protected']
        # A separate clean directory is used for the production UI workflow.
        m=SaveImporter(folder/'ui/SaveData',process_checker=lambda:False)
        app=QGuiApplication([]);messages=[];qInstallMessageHandler(lambda k,c,text:messages.append(text))
        b=Backend(offline=True,settings=folder/'settings.json');b._timer.stop();b._tutorial['seen']=True;b._save_importer=m
        engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',b)
        engine.load(QUrl.fromLocalFile(str(ROOT/'src/sinisistar_dglab/qml/ControlCenter.qml')));assert engine.rootObjects();window=engine.rootObjects()[0]
        def find(name):
            obj=window.findChild(QObject,name)
            if obj:return obj
            todo=[window.contentItem()]
            while todo:
                obj=todo.pop()
                if obj.objectName()==name:return obj
                todo.extend(obj.childItems())
            raise LookupError(name)
        def click(name):assert QMetaObject.invokeMethod(find(name),'clicked');app.processEvents()
        def verify():
            try:
                assert not b.developerTools
                click('openAppSettings');assert not find('openGameAssistance').property('visible')
                click('settingsMoreOptions');assert find('openGameAssistance').property('visible')
                click('openGameAssistance');assert find('gameAssistanceDialog').property('visible')
                assert find('importFullCgSave').property('enabled');click('importFullCgSave');assert find('confirmSaveImport').property('visible')
                assert not m.directory.exists();QMetaObject.invokeMethod(find('confirmSaveImport'),'close');app.processEvents()
                for lang in ('en','ja','zh-CN'):
                    b.setLanguage(lang);app.processEvents();assert window.grabWindow().save(str(out/('assistance-'+lang+'.png')))
                click('importFullCgSave');b.offline=False;b._armed=b._ovc_armed=True;click('confirmImportSaveButton')
                assert not b._armed and not b._ovc_armed
                deadline=time.monotonic()+5
                while b.saveImportState['busy'] and time.monotonic()<deadline:b._poll_installer();app.processEvents();time.sleep(.01)
                assert not b.saveImportState['error'],b.saveImportState
                assert (m.directory/'File01').is_file();assert b.saveImportState['canRestore']
                assert find('restoreImportedSave').property('enabled');click('restoreImportedSave');click('confirmRestoreSaveButton')
                while b.saveImportState['busy'] and time.monotonic()<deadline:b._poll_installer();app.processEvents();time.sleep(.01)
                assert not b.saveImportState['error'];assert not list(m.directory.iterdir())
                errors=[text for text in messages if any(key in text for key in ('ReferenceError','TypeError','Cannot assign','Unable to assign','Binding loop'))]
                assert not errors,errors
                checks.extend(['production folded settings entry','explicit import confirmation','CN EN JA rendering','both outputs paused','UI import and undo','no QML errors'])
                report=dict(passed=True,checks=checks,real_saves_modified=False,hardware_connected=False)
                (out/'optional-save-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report));app.exit(0)
            except Exception:
                import traceback;traceback.print_exc();print(messages);app.exit(1)
        QTimer.singleShot(300,verify);code=app.exec();b.shutdown();return code

if __name__=='__main__':raise SystemExit(main())
