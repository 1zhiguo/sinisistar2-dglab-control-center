"""Execute the real C# interface validator against API and ABI mutations."""
from pathlib import Path
import json,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]

def main():
    with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as temp:
        folder=Path(temp);dll=folder/'InterfaceChecks.dll'
        refs=list((ROOT/'.analysis/tools/net6ref/ref/net6.0').glob('*.dll'))
        args=['/nostdlib+','/target:exe','/langversion:latest','/nullable:enable','/out:"'+str(dll)+'"']
        args+=['/reference:"'+str(p)+'"' for p in refs]
        args+=['"'+str(ROOT/p)+'"' for p in ('observer/RuntimeInterface.cs','tests/native/InterfaceChecks.cs')]
        args+=['/resource:"'+str(ROOT/'src/sinisistar_dglab/assets/runtime-interface-v1.json')+'",runtime-interface-v1.json']
        rsp=folder/'compile.rsp';rsp.write_text('\n'.join(args),encoding='utf-8')
        build=subprocess.run(['dotnet',str(ROOT/'.analysis/tools/roslyn411/tasks/netcore/bincore/csc.dll'),'/noconfig','@'+str(rsp)],capture_output=True,text=True,timeout=30)
        if build.returncode:raise RuntimeError(build.stdout+build.stderr)
        dll.with_suffix('.runtimeconfig.json').write_text(json.dumps({'runtimeOptions':{'tfm':'net6.0','framework':{'name':'Microsoft.NETCore.App','version':'6.0.0'}}}),encoding='utf-8')
        run=subprocess.run(['dotnet',str(dll)],capture_output=True,text=True,timeout=30)
        if run.returncode:raise RuntimeError(run.stdout+run.stderr)
        report=json.loads(run.stdout.strip());out=ROOT/'artifacts/interface-compat';out.mkdir(exist_ok=True)
        (out/'native-validator.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))

if __name__=='__main__':main()
