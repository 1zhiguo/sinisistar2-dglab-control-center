"""Start a closed local game in batch mode with isolated observer telemetry.

No control center/device service is started. Restore its Bridge configuration and
terminate only the process created by this check. Run against an owned test copy.
"""
import argparse,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from sinisistar_dglab.install_manager import InstallManager,game_is_running
from sinisistar_dglab.plugin_bridge import PluginObserver

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-dir',type=Path,default=ROOT/'SiNiSistar2_v1_3_1/WIN')
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/interface-compat/live-full')
    args=parser.parse_args();root=args.game_dir.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    if game_is_running(None):raise RuntimeError('A game is already running; leave it untouched')
    InstallManager().install(root)
    config=root/'BepInEx/config/local.sinisistar.dglab.observer.cfg';before=config.read_bytes() if config.exists() else None
    config.write_text('[Bridge]\nDirectory = '+str(out)+'\n',encoding='utf-8');process=None
    try:
        process=subprocess.Popen([str(root/'SiNiSistar2.exe'),'-batchmode','-nographics','-logFile',str(out/'unity.log')],cwd=root,creationflags=subprocess.CREATE_NO_WINDOW)
        deadline=time.monotonic()+45;path=out/'compatibility.json';report={};latest=None
        while time.monotonic()<deadline:
            if path.exists():
                report=json.loads(path.read_text(encoding='utf-8'))
                if report.get('pid')==process.pid:
                    if report.get('status')=='incompatible':break
                    try:
                        data=json.loads((out/'latest.json').read_text(encoding='utf-8'))
                        if data.get('pid')==process.pid:latest=PluginObserver.decode(data);break
                    except (OSError,ValueError):pass
            if process.poll() is not None:break
            time.sleep(.25)
        print(json.dumps(report,ensure_ascii=False))
        if report.get('pid')!=process.pid or report.get('status')!='compatible' or latest is None:raise RuntimeError('No compatible current heartbeat; inspect compatibility.json and unity.log')
        result=dict(passed=True,hardware_connected=False,heartbeat_verified=True,**{k:latest.get(k) for k in ('observer_version','scene_id','hook_count','build_profile','valid')})
        assert result['hook_count']==20,result
        (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=8)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        if before is None:config.unlink(missing_ok=True)
        else:config.write_bytes(before)

if __name__=='__main__':main()
