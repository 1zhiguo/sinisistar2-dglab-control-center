"""CLI wrapper for the same verified installer used by the native settings page."""
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from sinisistar_dglab.install_manager import InstallManager,InstallError

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-dir',type=Path,default=ROOT/'SiNiSistar2_v1_3_1/WIN')
    parser.add_argument('--check',action='store_true',help='Read-only inspection; do not install')
    parser.add_argument('--discover',action='store_true',help='Read-only nearby game discovery')
    args=parser.parse_args();manager=InstallManager()
    try:
        result=manager.discover_game_dirs(ROOT) if args.discover else manager.inspect_game(args.game_dir) if args.check else manager.install(args.game_dir,progress=lambda value,message:print(f'{value}% {message}',flush=True))
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except InstallError as error:
        print(json.dumps(dict(error=str(error),code=error.code,details=error.details),ensure_ascii=False,indent=2),file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
