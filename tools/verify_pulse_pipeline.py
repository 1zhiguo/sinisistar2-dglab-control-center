"""Run the production Pulse pipeline against loopback Mock APPs only."""
from pathlib import Path
import argparse,json,sys,unittest
from collections import Counter
from datetime import datetime,timezone

root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'src'))
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--all',action='store_true');args=parser.parse_args()
suite=unittest.defaultTestLoader.discover(str(root/'tests'),pattern='test_*.py' if args.all else 'test_pulse*.py')
def cases(suite):
    for item in suite:
        if isinstance(item,unittest.TestSuite):yield from cases(item)
        else:yield item
groups=dict(Counter(case.__class__.__module__ for case in cases(suite)))
result=unittest.TextTestRunner(verbosity=2).run(suite)
report=dict(checked_utc=datetime.now(timezone.utc).isoformat(),tests_run=result.testsRun,groups=groups,
            failures=len(result.failures),errors=len(result.errors),passed=result.wasSuccessful(),
            scope='Synthetic game snapshots -> production planners/backend -> V3/V4 Socket -> loopback Mock APPs; native HUD and waveform editing checks',
            hardware_connected=False,named_cg_rules_enabled=False,ovc_socket_tested=args.all,vibration_hardware_sent=False,
            next_validation='User-authorized physical APP/device pairing and real game validation; all output starts paused')
path=root/'artifacts/pulse-validation/summary.json';path.parent.mkdir(parents=True,exist_ok=True)
path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(path)
raise SystemExit(0 if result.wasSuccessful() else 1)
