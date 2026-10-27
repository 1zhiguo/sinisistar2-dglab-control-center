"""PyInstaller entry point with an on-disk startup diagnostic for windowed builds."""
import sys,traceback
from pathlib import Path

def launch():
    try:
        from sinisistar_dglab.app import main
        return main()
    except Exception:
        log=Path(sys.executable).resolve().parent/'artifacts/ui/startup-error.log'
        log.parent.mkdir(parents=True,exist_ok=True);log.write_text(traceback.format_exc(),encoding='utf-8')
        if '--screenshot' not in sys.argv and '--smoke-test' not in sys.argv:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,'Cannot start Control Center. Details:\n'+str(log),'SiNiSistar2 x DG-LAB',0x10)
        return 1

if __name__=='__main__':raise SystemExit(launch())
