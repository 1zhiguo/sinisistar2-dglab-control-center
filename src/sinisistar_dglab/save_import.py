"""Opt-in import of the supplied 1.3.1 save, with verified backups and undo.

Never called by installation or startup. The game's LocalLow saves are shared
by every game copy, so any running SiNiSistar2 process blocks writes.
"""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import base64, hashlib, json, os, sys, uuid, zipfile

PAYLOAD = Path(__file__).parent/'assets/optional-saves/full-cg.zip'
PAYLOAD_SHA256 = '431a4862e3f60dfd5ebd8b1e09b31b385cfa4cfc8318558ea4d9e8e3194acfa1'
SAVE_NAMES = ('System', 'SystemSpare', 'FileAuto')+tuple(f'File{i:02}' for i in range(1,11))

def digest(data):return hashlib.sha256(data).hexdigest()

def default_directory(build_profile=''):
    if sys.platform != 'win32':raise ValueError('存档导入仅支持 Windows')
    folder='SaveData_S' if build_profile.startswith('steam-') else 'SaveData'
    return Path(os.environ['USERPROFILE'])/'AppData/LocalLow/Uu/SiNiSistar2'/folder

def decode(data):
    try:result=json.loads(base64.b64decode(data.decode('utf-8-sig').splitlines()[0].strip(),validate=True).decode('utf-8')[::-1])
    except (ValueError,UnicodeError,IndexError) as error:raise ValueError('存档格式无效，未进行导入') from error
    if not isinstance(result,dict) or result.get('m_SavedVersion')!='1.3.1':raise ValueError('存档需要为游戏 1.3.1 版本')
    return result

def encode(data):return base64.b64encode(json.dumps(data,ensure_ascii=False,indent=4)[::-1].encode('utf-8'))

def safe(path):
    from .install_manager import _reparse
    path=Path(path).absolute()
    for part in (*reversed(path.parents),path):
        if _reparse(part):raise ValueError('存档或备份路径包含链接，请使用普通目录')
    return path

def read(path):
    safe(path)
    if path.stat().st_size>8*1024*1024:raise ValueError('存档文件过大，未进行导入')
    return path.read_bytes()

def merge_system(current, source):
    result=deepcopy(current)
    try:
        dst=result['m_SaveFlagAndVariable']['m_FlagByteArrays']
        src=source['m_SaveFlagAndVariable']['m_FlagByteArrays']
        if len(dst)!=len(src):raise ValueError()
        for a,b in zip(dst,src):
            x,y=a['m_ByteArray'],b['m_ByteArray']
            if len(x)!=len(y) or any(type(v) is not int or not 0<=v<=255 for v in x+y):raise ValueError()
            a['m_ByteArray']=[i|j for i,j in zip(x,y)]
    except (KeyError,TypeError,ValueError) as error:raise ValueError('系统存档标记结构不匹配，未进行导入') from error
    return result

class SaveImporter:
    def __init__(self,directory=None,*,payload=PAYLOAD,process_checker=None,replace=None,build_profile=''):
        from .install_manager import game_is_running
        self.directory=Path(directory) if directory else default_directory(build_profile)
        self.backups=self.directory.parent/'DGLabSaveBackups'
        self.payload=Path(payload);self.process_checker=process_checker or (lambda:game_is_running(None))
        self.replace=replace or os.replace

    def _closed(self):
        if self.process_checker():raise ValueError('请保存并退出所有 SiNiSistar2 游戏窗口后再操作存档')

    def status(self):
        return dict(directory=str(self.directory),available=self.payload.is_file(),canRestore=self._latest() is not None)

    def _latest(self):
        safe(self.backups)
        if not self.backups.exists():return None
        for path in sorted(self.backups.glob('*/manifest.json'),reverse=True):
            try:
                data=json.loads(read(path))
                if data.get('schema')==1 and data.get('applied') and not data.get('restored') and data.get('target')==str(self.directory.absolute()):return path,data
            except (OSError,ValueError):continue
        return None

    def _commit(self,changes):
        """Stage all writes, check the game again, roll back partial commits."""
        originals={name:read(self.directory/name) if (self.directory/name).exists() else None for name in changes}
        stages={};committed=[]
        try:
            for name,data in changes.items():
                safe(self.directory/name)
                if data is not None:
                    stage=self.directory/('.dglab-'+uuid.uuid4().hex+'.tmp');stages[name]=stage
                    with stage.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
            self._closed()
            for name,data in changes.items():
                target=self.directory/name
                if data is None:target.unlink(missing_ok=True)
                else:self.replace(stages[name],target)
                committed.append(name)
            for name,data in changes.items():
                if data is not None and read(self.directory/name)!=data:raise OSError('存档回读校验失败')
        except Exception:
            for name in reversed(committed):
                target=self.directory/name;data=originals[name]
                if data is None:target.unlink(missing_ok=True)
                else:
                    rollback=self.directory/('.dglab-'+uuid.uuid4().hex+'.tmp')
                    try:rollback.write_bytes(data);os.replace(rollback,target)
                    finally:rollback.unlink(missing_ok=True)
            raise
        finally:
            for path in stages.values():path.unlink(missing_ok=True)

    def import_save(self):
        self._closed();safe(self.directory);safe(self.backups)
        if digest(read(self.payload))!=PAYLOAD_SHA256:raise ValueError('全 CG 存档包校验失败')
        with zipfile.ZipFile(self.payload) as z:
            if sorted(z.namelist())!=['File01','System','SystemSpare'] or any(i.file_size>8*1024*1024 for i in z.infolist()):raise ValueError('全 CG 存档包内容无效')
            source={name:z.read(name) for name in z.namelist()}
        system=decode(source['System']);decode(source['SystemSpare']);decode(source['File01'])
        slot=next((f'File{i:02}' for i in range(1,11) if not (self.directory/f'File{i:02}').exists()),None)
        if not slot:raise ValueError('十个存档槽已满，请先在游戏内腾出一个空槽；未覆盖任何存档')
        current=None
        for name in ('System','SystemSpare'):
            if (self.directory/name).exists():current=decode(read(self.directory/name));break
        # Existing preferences/variables are retained. New profiles use neutral defaults.
        if current is None:
            current=deepcopy(system)
            current['m_KeyConfigText']='';current['m_LanguageType']=0
            current['m_SoundSetting']={k:10 for k in system['m_SoundSetting']}
        merged=encode(merge_system(current,system))
        changes={slot:source['File01'],'System':merged,'SystemSpare':merged}
        existing={name:read(self.directory/name) for name in SAVE_NAMES if (self.directory/name).exists()}
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-'+uuid.uuid4().hex[:8]
        backup=self.backups/stamp;backup.mkdir(parents=True)
        for name,data in existing.items():
            (backup/name).write_bytes(data)
            if read(backup/name)!=data:raise OSError('原存档备份校验失败')
        manifest=dict(schema=1,target=str(self.directory.absolute()),slot=slot,source='Alicelel',applied=False,restored=False,
                      original={k:digest(v) for k,v in existing.items()},installed={k:digest(v) for k,v in changes.items()})
        path=backup/'manifest.json';path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        self.directory.mkdir(parents=True,exist_ok=True);self._commit(changes)
        manifest['applied']=True
        try:path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        except OSError:
            self._commit({name:existing.get(name) for name in changes});raise
        return dict(slot=slot,backup=str(backup),message=f'全 CG 存档已导入槽位 {int(slot[4:])}；原存档已备份')

    def restore(self):
        self._closed();safe(self.directory)
        latest=self._latest()
        if not latest:raise ValueError('没有可恢复的导入备份')
        path,manifest=latest;installed=manifest.get('installed',{});original=manifest.get('original',{})
        slot=manifest.get('slot')
        if slot not in SAVE_NAMES[3:] or set(installed)!={slot,'System','SystemSpare'} or not set(original).issubset(SAVE_NAMES):raise ValueError('备份清单无效')
        for name,expected in installed.items():
            if not (self.directory/name).is_file() or digest(read(self.directory/name))!=expected:
                raise ValueError('导入后存档已有变化，为保留后续进度，请手动查看备份恢复')
        changes={}
        for name in installed:
            data=read(path.parent/name) if name in original else None
            if data is not None and digest(data)!=original[name]:raise ValueError('备份校验失败，未恢复')
            changes[name]=data
        self._commit(changes);manifest['restored']=True
        path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        return dict(backup=str(path.parent),message='已撤销最近一次导入并恢复原系统存档')
