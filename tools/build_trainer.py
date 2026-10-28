"""Build the optional helper separately from the read-only observer."""
from pathlib import Path
import hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[1]

def main():
    core=ROOT/'.analysis/tools/heatseekar-runtime/BepInEx/core'
    interop=ROOT/'SiNiSistar2_v1_3_1/WIN/BepInEx/interop'
    refs=list((ROOT/'.analysis/tools/net6ref/ref/net6.0').glob('*.dll'))
    refs += [core/n for n in ['BepInEx.Core.dll','BepInEx.Unity.Common.dll','BepInEx.Unity.IL2CPP.dll','Il2CppInterop.Runtime.dll','MonoMod.RuntimeDetour.dll','MonoMod.Utils.dll']]
    refs += [interop/'UnityEngine.CoreModule.dll',interop/'Il2Cppmscorlib.dll']
    out=ROOT/'trainer/bin';out.mkdir(parents=True,exist_ok=True)
    dll=out/'SiNiSistarDGLab.Trainer.dll'
    args=['/nostdlib+','/target:library','/langversion:latest','/nullable:enable','/optimize+','/out:"'+str(dll)+'"']
    args+=['/reference:"'+str(p)+'"' for p in refs]
    args+=['"'+str(ROOT/'trainer'/name)+'"' for name in ['Native.cs','AttackSettings.cs','Plugin.cs']]
    args+=['\"'+str(ROOT/'observer/BuildCompatibility.cs')+'\"']
    rsp=out/'compile.rsp';rsp.write_text('\n'.join(args),encoding='utf-8')
    code=subprocess.call(['dotnet',str(ROOT/'.analysis/tools/roslyn411/tasks/netcore/bincore/csc.dll'),'/noconfig','@'+str(rsp)],cwd=ROOT)
    if code:return code
    target=ROOT/'installer_payload'/dll.name;target.write_bytes(dll.read_bytes())
    manifest=dict(version='0.2.2',file=dll.name,sha256=hashlib.sha256(dll.read_bytes()).hexdigest(),
                  fingerprint='b869493305bbe587598c8709e7fe271f00d79d37803c6a8241946d6a6297499d')
    (ROOT/'installer_payload/trainer-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(manifest));return 0

if __name__=='__main__':raise SystemExit(main())
