"""Local build using project-scoped Roslyn and .NET 6 reference assemblies."""
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]

def main():
    core=ROOT/'.analysis/tools/heatseekar-runtime/BepInEx/core';ref=ROOT/'.analysis/tools/net6ref/ref/net6.0';compiler=ROOT/'.analysis/tools/roslyn411/tasks/netcore/bincore/csc.dll'
    out=ROOT/'observer/bin';out.mkdir(parents=True,exist_ok=True)
    refs=list(ref.glob('*.dll'))+[core/n for n in ['BepInEx.Core.dll','BepInEx.Unity.Common.dll','BepInEx.Unity.IL2CPP.dll','Il2CppInterop.Runtime.dll','MonoMod.RuntimeDetour.dll','MonoMod.Utils.dll']]
    if not compiler.is_file() or not refs:raise RuntimeError('Project compiler dependencies have not been prepared')
    lines=['/nostdlib+','/target:library','/langversion:latest','/nullable:enable','/optimize+','/out:"'+str(out/'SiNiSistarDGLab.Observer.dll')+'"']+['/reference:"'+str(p)+'"' for p in refs]+['"'+str(ROOT/'observer/Plugin.cs')+'"']
    rsp=out/'compile.rsp';rsp.write_text('\n'.join(lines),encoding='utf-8')
    return subprocess.call(['dotnet',str(compiler),'/noconfig','@'+str(rsp)],cwd=ROOT)

if __name__=='__main__':raise SystemExit(main())
