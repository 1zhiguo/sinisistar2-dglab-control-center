"""Transactional BepInEx/observer installation with runtime interface probing.

No game launch, memory access, feature plugins, patchers or save-data edits.
The payload is project-local and can be copied with the control center.
Installation success is not proof that the plugin loaded in the game.
"""
from __future__ import annotations

import ctypes,hashlib,json,os,shutil,sys,uuid,zipfile
from pathlib import Path,PurePosixPath
from datetime import datetime,timezone
from contextlib import contextmanager
from .telemetry import ROOT,BUILD,METADATA
from .game_builds import PROFILES,candidate_checks

OWNER='SiNiSistar2-x-DGlab'
EXE='SiNiSistar2.exe'
PLUGIN='BepInEx/plugins/SiNiSistarDGLab/SiNiSistarDGLab.Observer.dll'
MANIFEST='BepInEx/plugins/SiNiSistarDGLab/install-manifest.json'
CONFIG='BepInEx/config/BepInEx.cfg'
CACHE='BepInEx/unity-libs/2022.3.62.zip'
SOURCE_HASH='437a0ea8f52f7a9aacfda5eb4718d5422db4f9b048eea7bef296f5c7a5fae10b'
PINNED_PAYLOAD={
    'bepinex-runtime.zip':'f32c41efaf2e21308b58dd92f68ce422cde237e1ec2985a6294242381556442e',
    'unity-2022.3.62.zip':'dd9e3e8171c2f378893d1a5df0029929c13e47f4838357c1b143b5df02aacf1f',
    'SiNiSistarDGLab.Observer.dll':'6040a1760cb098c21181885fd7c1e72c137478fbef2dfa0a2a3cdc18ee1a09df'}
EXPECTED_BUILD={EXE:'14aa8540d92597f0e7482bf2c11d63a9cd202bb3accbaed7bf0a12a141e259a7',
                'GameAssembly.dll':BUILD,'UnityPlayer.dll':'43fb0aea1b80c74963dae88ec7fc1c3c1993d893ce94d12972000fcc9b653ad1',
                'SiNiSistar2_Data/il2cpp_data/Metadata/global-metadata.dat':METADATA}
KNOWN_OLD_OBSERVERS=frozenset(('6ac941fe44722e50929313feadc8b50138f80f7d1d5d0f629c361dd50051e741','3f7cc88b1eca87168bfd3bbb7e2ed2bcfb07cf94317c9859ca037af22af183fa','f987b6fb0bda74c674e424b97e488349668d23cd73b18352d178a6001c8213bb','ea5e0c05c0ce4ecf8424955a44c6938414a401b3ab985d7e68992e4c12aced7f','bfb2101c02f8664098fc83129d0d9e026d1656f9c43d3e658fb14757b21cadde','c79e4e1af33aced68ab998220668b732240a08f51982c53f2493fb381d3507c9','5b095139249fd2256d64d61f9937b7691b3a9ef3eee95476f2522dc3ffdd6ccf','73535003a763274fcbca68a6c5fa5cbd2c72fce23a6801a0b809048d93543f9f','2c5c5f6c1f64e2cf03ad22aafcdc4cf1dedc702d104595b768f0feef6cccad1d','2ffaafc92e59b57664f68be9f385df0675e58c3b3b73f9d60385157981e2a299','6f254d948a0923b67d9c1817469cc2a9b92c5c6dfe5e0dd112a4b45540b447a5','5c82ab9eb915f1a7b923afec98bebcd8a17065e68cf7d1bf1ae75841e8782326','34aca47401f565f2ec1fcf0d16ea17eaada101bcef8ef9d59256fcef2a445c8a',
                              'f7c4b1a554194fcbb3910e0526d09fc60c988476876a4bdd07e03d573744cdf6'))
SKIP_DIRS=frozenset(('.git','.analysis','.venv','venv','node_modules','__pycache__','BepInEx','dotnet','SaveData','installer_payload','artifacts','src','tests'))
CONFIG_BYTES=b'[Logging.Console]\nEnabled = false\n\n[IL2CPP]\nUnityBaseLibrariesSource = 2022.3.62.zip\n'

class InstallError(RuntimeError):
    def __init__(self,code,message,details=None):
        super().__init__(message);self.code=code;self.details=details or {}

def sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda:handle.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()

def _relative(value):
    text=str(value).replace('\\','/');path=PurePosixPath(text)
    if not text or path.is_absolute() or ':' in text or any(p in ('','..') for p in path.parts):
        raise InstallError('unsafe_path','安装清单包含不安全的相对路径',{'path':text})
    return path.as_posix()

def _reparse(path):
    try:return path.is_symlink() or bool(getattr(path.lstat(),'st_file_attributes',0)&0x400)
    except OSError:return False

def _target(root,relative):
    relative=_relative(relative);target=root.joinpath(*PurePosixPath(relative).parts)
    probe=root
    for part in PurePosixPath(relative).parts:
        probe=probe/part
        if probe.exists() and _reparse(probe):raise InstallError('unsafe_path','安装路径包含链接或重解析目录',{'path':str(probe)})
    if not target.resolve(strict=False).is_relative_to(root):raise InstallError('unsafe_path','安装路径越出所选游戏目录')
    return target

def game_is_running(executable):
    """Read-only process check; None matches any copy sharing LocalLow saves."""
    if sys.platform!='win32':return False
    from ctypes import wintypes
    class Entry(ctypes.Structure):
        _fields_=[('dwSize',wintypes.DWORD),('cntUsage',wintypes.DWORD),('th32ProcessID',wintypes.DWORD),
                  ('th32DefaultHeapID',ctypes.c_size_t),('th32ModuleID',wintypes.DWORD),('cntThreads',wintypes.DWORD),
                  ('th32ParentProcessID',wintypes.DWORD),('pcPriClassBase',wintypes.LONG),('dwFlags',wintypes.DWORD),('szExeFile',wintypes.WCHAR*260)]
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.CreateToolhelp32Snapshot.argtypes=[wintypes.DWORD,wintypes.DWORD];api.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
    api.Process32FirstW.argtypes=[wintypes.HANDLE,ctypes.POINTER(Entry)];api.Process32NextW.argtypes=api.Process32FirstW.argtypes
    api.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];api.OpenProcess.restype=wintypes.HANDLE
    api.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    api.CloseHandle.argtypes=[wintypes.HANDLE]
    snapshot=api.CreateToolhelp32Snapshot(2,0)
    if snapshot==ctypes.c_void_p(-1).value:raise InstallError('process_check_failed','无法核对游戏进程，请稍后重试')
    wanted=str(Path(executable).resolve()).casefold() if executable else None;entry=Entry();entry.dwSize=ctypes.sizeof(entry)
    try:
        exists=api.Process32FirstW(snapshot,ctypes.byref(entry))
        while exists:
            if entry.szExeFile.casefold()==EXE.casefold():
                if wanted is None:return True
                handle=api.OpenProcess(0x1000,False,entry.th32ProcessID)
                if not handle:raise InstallError('process_check_failed','有同名游戏进程，无法确认其路径；请先退出游戏')
                try:
                    length=wintypes.DWORD(32768);buffer=ctypes.create_unicode_buffer(length.value)
                    if not api.QueryFullProcessImageNameW(handle,0,buffer,ctypes.byref(length)):
                        raise InstallError('process_check_failed','无法读取同名游戏进程路径；请先退出游戏')
                    if str(Path(buffer.value).resolve()).casefold()==wanted:return True
                finally:api.CloseHandle(handle)
            exists=api.Process32NextW(snapshot,ctypes.byref(entry))
        return False
    finally:api.CloseHandle(snapshot)

@contextmanager
def _commit_executable_lock(root):
    """Keep a new game launch from racing the short file-replacement phase."""
    if sys.platform!='win32':
        yield;return
    from ctypes import wintypes
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    api.CreateFileW.restype=wintypes.HANDLE;api.CloseHandle.argtypes=[wintypes.HANDLE]
    # Read-only, no-sharing handle; never changes the executable. A process
    # already opening it prevents this lock; a later launch waits/fails until
    # installation releases the handle instead of loading half a runtime.
    handle=api.CreateFileW(str(root/EXE),0x80000000,0,None,3,0x80,None)
    if handle==ctypes.c_void_p(-1).value:
        raise InstallError('game_locked','游戏程序被占用，安装尚未开始替换；请退出游戏后重试')
    try:yield
    finally:api.CloseHandle(handle)

def _candidates(anchor,max_depth=3,budget=160):
    root=Path(anchor).expanduser()
    if root.is_file():root=root.parent
    if not root.is_dir():return []
    queue=[(root,0)];found=[];seen=set()
    while queue and len(seen)<budget:
        folder,depth=queue.pop(0)
        try:resolved=folder.resolve()
        except OSError:continue
        if resolved in seen:continue
        seen.add(resolved)
        if (folder/EXE).is_file():found.append(resolved);continue
        if depth>=max_depth:continue
        try:children=sorted(folder.iterdir(),key=lambda p:(p.name.casefold()!='win',p.name.casefold()))
        except OSError:continue
        for child in children:
            if child.name in SKIP_DIRS or child.name.startswith('.') or _reparse(child):continue
            try:
                if child.is_dir():queue.append((child,depth+1))
            except OSError:continue
        # Bound queued traversal as well as visited directories.
        queue=queue[:max(0,budget-len(seen))]
    return found

def normalize_game_dir(path):
    given=Path(path).expanduser()
    if given.is_file():
        if given.name.casefold()!=EXE.casefold():raise InstallError('not_found','请选择 SiNiSistar2.exe 或游戏文件夹')
        given=given.parent
    if (given/EXE).is_file():return given.resolve()
    found=_candidates(given,max_depth=2,budget=100)
    if len(found)==1:return found[0]
    if len(found)>1:raise InstallError('ambiguous','发现多个游戏目录，请选择具体的 WIN 文件夹',{'candidates':[str(x) for x in found]})
    raise InstallError('not_found','未找到 SiNiSistar2.exe；请选择游戏的 WIN 文件夹')

class InstallManager:
    def __init__(self,payload_dir=None,*,_expected_build=None,_trusted_archives=None,_process_checker=None,_replace=None):
        self.payload_dir=Path(payload_dir) if payload_dir else ROOT/'installer_payload'
        self.expected_build=dict(EXPECTED_BUILD if _expected_build is None else _expected_build)
        self.build_profiles=PROFILES if _expected_build is None else [dict(id='test-fixture',label='Fixture',files=self.expected_build)]
        self._allow_interface_candidate=_expected_build is None
        self.trusted_archives=dict(PINNED_PAYLOAD if _trusted_archives is None else _trusted_archives)
        self.process_checker=_process_checker or game_is_running;self.replace=_replace or os.replace

    def payload_info(self):
        names=['manifest.json',*self.trusted_archives]
        available=all((self.payload_dir/name).is_file() for name in names)
        try:count=len(json.loads((self.payload_dir/'manifest.json').read_text(encoding='utf-8-sig'))['runtime_files'])
        except (OSError,ValueError,KeyError,TypeError):count=0
        return dict(available=available,validated=False,bytes=sum((self.payload_dir/n).stat().st_size for n in names if (self.payload_dir/n).is_file()),
                    files=count,plugin_version='0.8.0',error='' if available else '本地安装包缺失，请补全 installer_payload')

    def inspect_game(self,path):
        result=dict(game_dir='',executable='',telemetry_dir='',detected=False,supported=False,running=False,state='not_found',plugin_version='',errors=[],warnings=[])
        try:
            root=normalize_game_dir(path);result.update(game_dir=str(root),executable=str(root/EXE),telemetry_dir=str(root/'BepInEx/plugins/SiNiSistarDGLab/telemetry'),detected=True)
            actual={relative:sha256(_target(root,relative)) if _target(root,relative).is_file() else None for relative in self.expected_build}
            profile=next((p for p in self.build_profiles if p['files']==actual),None)
            result['game_fingerprints']=actual
            if profile is None:
                errors=candidate_checks({name:_target(root,name) for name in self.expected_build}) if self._allow_interface_candidate else ['核心文件不匹配']
                if errors:raise InstallError('unsupported','游戏运行环境未适配：'+'；'.join(errors),{'fingerprints':actual})
                profile=dict(id='interface-pending',label='其他渠道构建 · 待启动验证接口')
                result['warnings'].append('允许安装观察插件；启动后检查游戏接口，通过后才读取和联动。')
            result.update(build_profile=profile['id'],build_label=profile['label'],compatibility_mode='runtime-interface' if profile['id']=='interface-pending' else 'known-build',interface_verified=False)
            result['supported']=True;result['running']=bool(self.process_checker(root/EXE))
            plugin=_target(root,PLUGIN)
            if plugin.is_file():
                if sha256(plugin)==self.trusted_archives['SiNiSistarDGLab.Observer.dll']:result['plugin_version']='0.8.0'
                elif sha256(plugin) in KNOWN_OLD_OBSERVERS:result['plugin_version']='旧版观察插件'
                else:result['warnings'].append('存在同名但未知版本的观察插件，安装将拒绝覆盖')
            result['state']='running' if result['running'] else 'installed' if result['plugin_version']=='0.8.0' else 'ready'
            config=_target(root,CONFIG)
            if config.exists():result['warnings'].append('已有 BepInEx 配置将保留，除非它是本安装器创建且未经修改的版本')
        except (InstallError,OSError,ValueError,KeyError) as error:
            result['state']=getattr(error,'code','conflict');result['errors'].append(str(error))
        return result

    def discover_game_dirs(self,anchor=None,extra_roots=()):
        anchor=Path(anchor or ROOT).expanduser();roots=[anchor,*map(Path,extra_roots)]
        # Only the immediate parent is considered; traversal stays depth/budget
        # bounded and skips common development and reparse directories.
        if anchor.parent!=anchor:roots.append(anchor.parent)
        candidates=[];seen=set()
        for folder in roots:
            for game in _candidates(folder,max_depth=3,budget=180):
                key=str(game).casefold()
                if key not in seen:seen.add(key);candidates.append(self.inspect_game(game))
        return candidates

    def _payload(self):
        try:manifest=json.loads((self.payload_dir/'manifest.json').read_text(encoding='utf-8-sig'))
        except (OSError,ValueError) as error:raise InstallError('payload_missing','本地安装清单缺失或损坏') from error
        if manifest.get('owner')!=OWNER or manifest.get('schema')!=1 or manifest.get('source_archive_sha256')!=SOURCE_HASH:
            raise InstallError('payload_invalid','安装包来源信息不匹配')
        for name,expected in self.trusted_archives.items():
            path=self.payload_dir/name
            if not path.is_file() or sha256(path)!=expected or manifest.get('archives',{}).get(name,{}).get('sha256')!=expected:
                raise InstallError('payload_invalid','安装包校验失败，未更改游戏文件',{'file':name})
        entries={};casefold=set()
        try:
            with zipfile.ZipFile(self.payload_dir/'bepinex-runtime.zip') as archive:
                available={i.filename for i in archive.infolist() if not i.is_dir()}
                listed=set()
                for item in manifest['runtime_files']:
                    relative=_relative(item['path']);listed.add(relative)
                    if relative.casefold() in casefold:raise InstallError('payload_invalid','安装包包含重复目标')
                    casefold.add(relative.casefold())
                    if not (relative.startswith(('BepInEx/core/','dotnet/')) or relative in ('.doorstop_version','winhttp.dll','doorstop_config.ini')):
                        raise InstallError('payload_invalid','安装包包含范围外文件',{'path':relative})
                    info=archive.getinfo(relative)
                    if ((info.external_attr>>16)&0o170000)==0o120000:raise InstallError('payload_invalid','安装包包含符号链接')
                    data=archive.read(relative)
                    if len(data)!=item['size'] or hashlib.sha256(data).hexdigest()!=item['sha256']:
                        raise InstallError('payload_invalid','运行时文件校验失败',{'path':relative})
                    entries[relative]=dict(source='zip',member=relative,sha256=item['sha256'],size=item['size'])
                if available!=listed:raise InstallError('payload_invalid','安装包内容与清单不一致')
        except (zipfile.BadZipFile,KeyError,TypeError,OSError) as error:raise InstallError('payload_invalid','运行时安装包不可读取') from error
        for relative,name in ((PLUGIN,'SiNiSistarDGLab.Observer.dll'),(CACHE,'unity-2022.3.62.zip')):
            entries[relative]=dict(source='file',member=name,sha256=self.trusted_archives[name],size=(self.payload_dir/name).stat().st_size)
        entries[CONFIG]=dict(source='generated',sha256=hashlib.sha256(CONFIG_BYTES).hexdigest(),size=len(CONFIG_BYTES))
        return manifest,entries

    def _not_running(self,root):
        try:running=self.process_checker(root/EXE)
        except InstallError:raise
        except Exception as error:raise InstallError('process_check_failed','无法确认游戏已退出，安装尚未开始') from error
        if running:raise InstallError('game_running','请先保存并退出所选游戏；安装未更改任何文件')

    def install(self,path,progress=None):
        def notify(percent,message):
            if progress:
                try:progress(percent,message)
                except Exception:pass
        root=normalize_game_dir(path);self._not_running(root);notify(2,'核对游戏版本')
        inspection=self.inspect_game(root)
        if not inspection['supported']:raise InstallError(inspection['state'],' / '.join(inspection['errors']) or '游戏版本不受支持')
        self._not_running(root);notify(12,'校验本地安装包')
        payload,entries=self._payload();manifest_target=_target(root,MANIFEST);prior={};owned={}
        if manifest_target.exists():
            try:
                prior=json.loads(manifest_target.read_text(encoding='utf-8-sig'))
                if prior.get('owner')!=OWNER:raise ValueError('owner')
                owned={_relative(row['path']):row['sha256'] for row in prior.get('files',[])}
            except (OSError,ValueError,KeyError,TypeError) as error:raise InstallError('conflict','现有安装记录无法确认来源，未更改文件') from error
        changes=[];unchanged=[];preserved_config=False;warnings=[];fingerprints={}
        for relative,entry in list(entries.items()):
            target=_target(root,relative)
            if target.exists() and not target.is_file():raise InstallError('conflict','安装目标不是文件',{'path':relative})
            current=sha256(target) if target.exists() else None;fingerprints[relative]=current
            if current==entry['sha256']:unchanged.append(relative);continue
            if current:
                known=owned.get(relative)==current or (relative==PLUGIN and current in KNOWN_OLD_OBSERVERS)
                if relative==CONFIG and not known:
                    preserved_config=True;warnings.append('保留现有 BepInEx.cfg，不覆盖用户配置');entries.pop(relative);continue
                if not known:raise InstallError('conflict','存在不同来源或已修改的文件，安装未覆盖',{'path':relative})
            changes.append(relative)
        self._not_running(root);notify(25,'预检通过，准备暂存文件')
        if not changes and prior.get('plugin_version')=='0.8.0' and all(owned.get(k)==v['sha256'] for k,v in entries.items()):
            notify(100,'文件已完整安装；请启动游戏验证加载')
            return self._result(root,payload,[],unchanged,preserved_config,'',warnings)
        token=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]
        stage=_target(root,'.sinisistar-dglab-install-'+token+'.tmp');stage.mkdir()
        committed=[];created_dirs=[];backup_dir='';rollback_errors=[]
        def parents(target):
            missing=[];folder=target.parent
            while folder!=root and not folder.exists():missing.append(folder);folder=folder.parent
            for folder in reversed(missing):folder.mkdir();created_dirs.append(folder)
        try:
            with zipfile.ZipFile(self.payload_dir/'bepinex-runtime.zip') as archive:
                for index,relative in enumerate(changes):
                    entry=entries[relative];staged=_target(stage,'new/'+relative);staged.parent.mkdir(parents=True,exist_ok=True)
                    if entry['source']=='zip':staged.write_bytes(archive.read(entry['member']))
                    elif entry['source']=='file':shutil.copy2(self.payload_dir/entry['member'],staged)
                    else:staged.write_bytes(CONFIG_BYTES)
                    if sha256(staged)!=entry['sha256']:raise InstallError('staging_failed','暂存校验失败，原文件未更改')
                    target=_target(root,relative)
                    if target.exists():
                        old=_target(stage,'old/'+relative);old.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,old)
                    notify(25+int(45*(index+1)/max(1,len(changes))),'暂存运行时与观察插件')
            new_manifest=dict(owner=OWNER,schema=1,plugin_version='0.8.0',runtime=payload['runtime'],source=payload.get('source',''),
                              installed_at=datetime.now(timezone.utc).isoformat(),game_build=inspection.get('build_profile','v1.3.1'),game_fingerprints=inspection.get('game_fingerprints',self.expected_build),
                              files=[dict(path=k,sha256=v['sha256']) for k,v in entries.items()],load_verified=False)
            staged_manifest=_target(stage,'new/'+MANIFEST);staged_manifest.parent.mkdir(parents=True,exist_ok=True)
            staged_manifest.write_text(json.dumps(new_manifest,ensure_ascii=False,indent=2),encoding='utf-8')
            if manifest_target.exists():
                old=_target(stage,'old/'+MANIFEST);old.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(manifest_target,old)
            with _commit_executable_lock(root):
                self._not_running(root)
                for relative,digest in fingerprints.items():
                    target=_target(root,relative)
                    if (sha256(target) if target.exists() else None)!=digest:raise InstallError('changed_during_install','文件在安装准备期间发生变化，未开始替换',{'path':relative})
                notify(75,'写入已验证文件')
                for relative in [*changes,MANIFEST]:
                    target=_target(root,relative);parents(target)
                    self.replace(_target(stage,'new/'+relative),target);committed.append(relative)
                if (stage/'old').exists():
                    destination=_target(root,'.sinisistar-dglab-backups/'+token);parents(destination)
                    self.replace(stage/'old',destination);backup_dir=str(destination)
            notify(100,'安装完成；请启动游戏验证插件加载')
            return self._result(root,payload,changes,unchanged,preserved_config,backup_dir,warnings)
        except Exception as error:
            for relative in reversed(committed):
                try:
                    target=_target(root,relative);old=_target(stage,'old/'+relative)
                    if old.exists():os.replace(old,target)
                    elif target.exists():target.unlink()
                except OSError as failure:rollback_errors.append(str(failure))
            for folder in reversed(created_dirs):
                try:folder.rmdir()
                except OSError:pass
            if rollback_errors:raise InstallError('rollback_failed','安装中断，部分文件需要按备份恢复',{'errors':rollback_errors,'staging_dir':str(stage)}) from error
            if isinstance(error,InstallError):raise
            raise InstallError('install_failed','安装失败，已恢复安装前的文件',{'error':str(error)}) from error
        finally:
            # This computed delete target is an explicitly checked child of
            # the selected game root, never the root or a discovered path.
            if not rollback_errors and stage.exists() and stage.resolve().is_relative_to(root) and stage.name.startswith('.sinisistar-dglab-install-'):
                shutil.rmtree(stage)

    @staticmethod
    def _result(root,payload,changed,unchanged,preserved_config,backup_dir,warnings):
        return dict(success=True,game_dir=str(root),executable=str(root/EXE),telemetry_dir=str(root/'BepInEx/plugins/SiNiSistarDGLab/telemetry'),
                    plugin_version='0.8.0',runtime=payload['runtime'],changed_files=changed,unchanged_files=unchanged,
                    preserved_config=preserved_config,backup_dir=backup_dir,requires_restart=True,load_verified=False,warnings=warnings)

def discover_game_dirs(anchor=None,extra_roots=()):return InstallManager().discover_game_dirs(anchor,extra_roots)
