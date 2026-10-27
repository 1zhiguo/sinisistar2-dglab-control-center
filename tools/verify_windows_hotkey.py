"""Actual Windows registration, conflict and WM_HOTKEY dispatch; inert backend."""
from pathlib import Path
import ctypes,json,sys,tempfile,threading,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from PySide6.QtCore import QTimer,Qt
from PySide6.QtGui import QGuiApplication
from sinisistar_dglab.backend import Backend
from sinisistar_dglab.hotkeys import GlobalHotkeys,WindowsApi,shortcut

def main():
    app=QGuiApplication([]);temp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp')
    b=Backend(offline=True,settings=Path(temp.name)/'settings.json');b._timer.stop();m=GlobalHotkeys(app,b)
    candidate=shortcut(Qt.Key_F23,Qt.ControlModifier|Qt.ShiftModifier|Qt.AltModifier)
    report={}
    def probe():
        rows=[]
        def work():
            api=WindowsApi();error=api.register(7777,candidate['modifiers'],candidate['vk']);rows.append(error)
            if not error:api.unregister(7777)
        thread=threading.Thread(target=work);thread.start();thread.join(2);return rows[0]
    def begin():
        try:
            assert m.apply(candidate),m.snapshot();assert probe(),'Registration from another thread unexpectedly succeeded'
            b._armed=b._ovc_armed=True
            tid=ctypes.windll.kernel32.GetCurrentThreadId()
            assert ctypes.windll.user32.PostThreadMessageW(tid,0x312,m.ident,(candidate['vk']<<16)|candidate['modifiers'])
            QTimer.singleShot(100,check)
        except Exception:finish(False)
    def check():
        try:
            assert b._emergency and not b._armed and not b._ovc_armed
            m.close();assert not probe(),'Shortcut was not released'
            finish(True)
        except Exception:finish(False)
    def finish(ok):
        nonlocal report
        report=dict(passed=ok,windows_register_hotkey_tested=True,global_conflict_tested=True,native_message_filter_tested=True,
            emergency_locks_both_routes=b._emergency,release_tested=ok,hardware_connected=False,error='' if ok else traceback.format_exc())
        (ROOT/'artifacts/ui/windows-hotkey-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report));app.exit(0 if ok else 1)
    QTimer.singleShot(0,begin);result=app.exec();b.shutdown();temp.cleanup();return result

if __name__=='__main__':raise SystemExit(main())
