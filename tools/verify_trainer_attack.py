"""Compile and run the helper's real attack settings code against temp files."""
from pathlib import Path
import json,shutil,subprocess,tempfile

ROOT=Path(__file__).resolve().parents[1]

def main():
    with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as temp:
        folder=Path(temp);dll=folder/'Checks.dll'
        core=ROOT/'.analysis/tools/heatseekar-runtime/BepInEx/core/BepInEx.Core.dll'
        refs=list((ROOT/'.analysis/tools/net6ref/ref/net6.0').glob('*.dll'))+[core]
        args=['/nostdlib+','/target:exe','/langversion:latest','/nullable:enable','/out:"'+str(dll)+'"']
        args+=['/reference:"'+str(p)+'"' for p in refs]
        args+=['"'+str(ROOT/'trainer'/name)+'"' for name in ('AttackSettings.cs','tests/AttackSettingsChecks.cs')]
        rsp=folder/'compile.rsp';rsp.write_text('\n'.join(args),encoding='utf-8')
        subprocess.run(['dotnet',str(ROOT/'.analysis/tools/roslyn411/tasks/netcore/bincore/csc.dll'),'/noconfig','@'+str(rsp)],check=True,capture_output=True,text=True,timeout=30)
        shutil.copy2(core,folder/core.name)
        shutil.copy2(core.parent/'SemanticVersioning.dll',folder/'SemanticVersioning.dll')
        dll.with_suffix('.runtimeconfig.json').write_text(json.dumps({'runtimeOptions':{'tfm':'net6.0','framework':{'name':'Microsoft.NETCore.App','version':'6.0.0'}}}),encoding='utf-8')
        result=subprocess.run(['dotnet',str(dll),str(folder)],capture_output=True,text=True,timeout=20)
        if result.returncode:raise RuntimeError(result.stderr or result.stdout)
        report=json.loads(result.stdout.strip());report['scope']='Actual helper settings and damage code; temp config reloads, legacy migration, original upgrade damage preservation'
        (ROOT/'artifacts/trainer-validation/attack-persistence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report));return 0

if __name__=='__main__':raise SystemExit(main())
