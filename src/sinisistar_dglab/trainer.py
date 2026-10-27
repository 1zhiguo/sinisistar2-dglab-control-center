"""Explicit, expiring local requests to the optional gameplay helper."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from pathlib import Path
import json,math,os,sys,time,uuid
from .telemetry import BUILD,ROOT
from .monitoring import parse_time
from .telemetry import TYPES
from .monitoring import status_label
from .status_policy import positive_status

KNOWN_OLD_TRAINERS=frozenset(('fc60235d835efcd32cb895fb22a745610d5ea4c75e412c24733c5c741dd69ac3',
                            'adb864d220d712ff867f6d344a134cb13ed383903cffef089b1d73a1d815ed33'))

def _read_json(path):
    # Permit atomic replacement by the game's writer while the UI reads.
    if sys.platform=='win32':
        import ctypes,msvcrt
        from ctypes import wintypes
        api=ctypes.WinDLL('kernel32',use_last_error=True)
        api.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
        api.CreateFileW.restype=wintypes.HANDLE
        handle=api.CreateFileW(str(path),0x80000000,0x7,None,3,0x80,None)
        if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
        with os.fdopen(msvcrt.open_osfhandle(handle,os.O_RDONLY),'rb') as file:payload=file.read(65537)
    else:
        with Path(path).open('rb') as file:payload=file.read(65537)
    if len(payload)>65536:raise ValueError('辅助插件消息过大')
    return json.loads(payload.decode('utf-8-sig'))

def decode_snapshot(data,*,now=None):
    if not isinstance(data,dict) or data.get('schema')!=1 or data.get('source')!='bepinex-trainer' or data.get('fingerprint')!=BUILD:
        raise ValueError('辅助插件协议或游戏版本不匹配')
    age=((now or datetime.now(timezone.utc))-parse_time(data['utc'])).total_seconds()
    if not 0<=age<1:raise ValueError('辅助插件心跳已过期')
    if type(data.get('pid')) is not int or data['pid']<=0 or not isinstance(data.get('session'),str) or len(data['session'])!=32:
        raise ValueError('辅助插件会话无效')
    if any(type(data.get(key)) is not bool for key in ('valid','can_edit','attack_available')):raise ValueError('辅助插件状态标志无效')
    for name in ('hp','mp'):
        value=data.get(name)
        if value is not None and (not isinstance(value,dict) or type(value.get('current')) is not int or type(value.get('max')) is not int or not 0<=value['current']<=value['max']<=10000000):
            raise ValueError('辅助插件资源数据无效')
    value=data.get('attack_multiplier')
    if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=10:raise ValueError('攻击力倍率无效')
    if data.get('can_edit') and (type(data.get('player')) is not int or data['player']<=0 or not data.get('valid') or data.get('hp') is None or data.get('mp') is None):
        raise ValueError('玩家对象尚未就绪')
    items=data.get('abnormals',[])
    if not isinstance(items,list) or len(items)>256:raise ValueError('辅助插件异常列表无效')
    for item in items:
        if not isinstance(item,dict) or type(item.get('type_raw')) is not int or not -2147483648<=item['type_raw']<=2147483647 or type(item.get('level')) is not int or not 0<item['level']<=10000000:
            raise ValueError('辅助插件异常状态无效')
    if 'status_removal_available' in data and type(data['status_removal_available']) is not bool:raise ValueError('辅助插件功能标志无效')
    if 'attack_persistent' in data and type(data['attack_persistent']) is not bool:raise ValueError('辅助倍率保存标志无效')
    return deepcopy(data)

class TrainerBridge:
    def __init__(self):
        self.directory=None;self.live={};self.pending=None;self.deadline=0.;self.message='安装辅助插件并重启游戏后可用';self.error=''
    @property
    def state(self):
        rows=[];seen=set()
        # The status manager may retain the save's data on the title screen.
        # It is current player state only while a valid player is present.
        current=self.live.get('abnormals',[]) if self.live.get('valid') and self.live.get('player') else []
        for item in current:
            if item['type_raw'] in seen:continue
            seen.add(item['type_raw']);name=TYPES['AbnormalType'].get(str(item['type_raw']),'未知状态 #'+str(item['type_raw']))
            rows.append(dict(item,name=name,label=status_label(name),positive=positive_status(name)))
        return dict(self.live,abnormals=rows,negative_count=sum(not r['positive'] for r in rows),online=bool(self.live),pending=bool(self.pending),message=self.message,error=self.error,
                    can_edit=bool(self.live.get('can_edit') and not self.pending))
    def poll(self,directory):
        directory=Path(directory)
        if directory!=self.directory:
            self.directory=directory;self.live={};self.pending=None;self.error='';self.message='等待辅助插件加载'
        try:self.live=decode_snapshot(_read_json(directory/'latest.json'))
        except (OSError,ValueError,KeyError,TypeError):self.live={}
        if self.pending:
            if self.live and any(self.live.get(k)!=self.pending[k] for k in ('session','pid','player')):
                self.pending=None;self.error='玩家或游戏会话已变化，旧修改请求已取消';return
            try:
                result=_read_json(directory/'result.json')
                if result.get('id')==self.pending['id']:
                    if any(result.get(k)!=self.pending[k] for k in ('session','pid','player')):raise ValueError('修改回执的玩家身份不匹配')
                    if result.get('attribute')!=self.pending['attribute']:raise ValueError('修改回执的属性不匹配')
                    if result.get('ok') is True:
                        if any(type(result.get(k)) not in (int,float) or not math.isfinite(result[k]) for k in ('before','after')):raise ValueError('修改回执缺少有效数值')
                        if self.pending['attribute'] in ('abnormal','abnormals'):
                            if any(type(result[k]) is not int or not 0<=result[k]<=256 for k in ('before','after')) or result['after']!=0:
                                raise ValueError('异常解除回执无效')
                        elif self.pending['attribute']=='attack':
                            if not 0<=result['after']<=10:raise ValueError('攻击力回执超出范围')
                        elif type(result['after']) is not int or type(result.get('max')) is not int or not 0<=result['after']<=result['max']<=10000000:
                            raise ValueError('资源回执超出范围')
                        if self.pending['attribute'] in ('abnormal','abnormals'):
                            self.message=f"已解除 {result['before']-result['after']} 种异常 · 游戏已确认"
                        else:
                            label={'hp':'HP','mp':'MP','attack':'攻击力倍率'}[self.pending['attribute']]
                            self.message=f"{label}：{result.get('before')} → {result.get('after')} · 游戏已确认"
                        self.error=''
                    else:self.error=str(result.get('error') or '游戏未确认修改')
                    self.pending=None
            except (OSError,ValueError,KeyError,TypeError):pass
            if self.pending and time.monotonic()>self.deadline:
                self.pending=None;self.error='等待游戏确认超时；请求已过期，不会自动重发'
    def send(self,attribute,mode,value):
        if self.pending:raise ValueError('请等待上一次修改完成')
        if not self.live.get('can_edit'):raise ValueError('请进入可操作存档，等待辅助插件就绪')
        if attribute not in ('hp','mp','attack','abnormal','abnormals'):raise ValueError('修改参数无效')
        if type(value) not in (int,float) or not math.isfinite(value):raise ValueError('请输入有效数值')
        if attribute in ('abnormal','abnormals'):
            if not self.live.get('status_removal_available'):raise ValueError('请更新辅助插件到 0.2.0 后重启游戏')
            if attribute=='abnormal':
                if mode!='remove' or type(value) not in (int,float) or value!=int(value) or not -2147483648<=value<=2147483647:raise ValueError('异常解除参数无效')
                if not any(r['type_raw']==int(value) for r in self.live.get('abnormals',[])):raise ValueError('该状态已经消失，请查看当前列表')
            elif mode!='clear_negative' or value!=0:raise ValueError('批量解除参数无效')
        elif attribute=='attack':
            if mode not in ('add','set','reset'):raise ValueError('修改参数无效')
            if not self.live.get('attack_available'):raise ValueError('攻击力辅助未就绪')
            if abs(value)>10 or (mode=='set' and value<0):raise ValueError('攻击力倍率范围为 0–10 倍')
        elif mode not in ('add','set') or value!=int(value) or abs(value)>10000000:raise ValueError('HP / MP 请输入整数')
        request=dict(id=uuid.uuid4().hex,session=self.live['session'],pid=self.live['pid'],player=self.live['player'],
                     attribute=attribute,mode=mode,value=value,expires_utc=(datetime.now(timezone.utc)+timedelta(seconds=4)).isoformat())
        path=self.directory/'command.json';temp=path.with_name('command.'+request['id']+'.tmp')
        try:
            temp.write_text(json.dumps(request,ensure_ascii=False),encoding='utf-8')
            for attempt in range(6):
                try:temp.replace(path);break
                except PermissionError:
                    if attempt==5:raise
                    time.sleep(.01)
        finally:temp.unlink(missing_ok=True)
        self.pending=request;self.deadline=time.monotonic()+5;self.error='';self.message='正在等待游戏确认…'

def install_trainer(game_dir):
    """Install only the optional helper. Never replace a DLL loaded by the game."""
    from .install_manager import InstallManager,_target,sha256
    root=Path(game_dir).resolve();info=InstallManager().inspect_game(root)
    if not info.get('supported') or info.get('errors'):raise ValueError('请先在「设备与游戏」核验并安装游戏插件环境')
    if not (root/'BepInEx/core/BepInEx.Unity.IL2CPP.dll').is_file():raise ValueError('请先安装 BepInEx 运行环境')
    payload=ROOT/'installer_payload';manifest=json.loads((payload/'trainer-manifest.json').read_text(encoding='utf-8'))
    source=payload/'SiNiSistarDGLab.Trainer.dll'
    if manifest.get('fingerprint')!=BUILD or manifest.get('file')!=source.name or sha256(source)!=manifest.get('sha256'):
        raise ValueError('辅助插件安装包校验失败')
    destination=_target(root,'BepInEx/plugins/SiNiSistarTrainer/SiNiSistarDGLab.Trainer.dll')
    if destination.exists():
        old_hash=sha256(destination)
        if old_hash==manifest['sha256']:return '辅助插件已安装；首次使用请保存并重启游戏'
        if info.get('running'):raise ValueError('请先保存并退出游戏，再更新辅助插件')
        if old_hash not in KNOWN_OLD_TRAINERS:raise ValueError('存在其他版本的同名辅助插件，请先备份移除后安装')
        backup=_target(root,'BepInEx/plugins/SiNiSistarTrainer/backups/'+old_hash+'.bak')
        backup.parent.mkdir(parents=True,exist_ok=True)
        if not backup.exists():backup.write_bytes(destination.read_bytes())
    destination.parent.mkdir(parents=True,exist_ok=True)
    staged=destination.with_suffix('.tmp');staged.write_bytes(source.read_bytes());staged.replace(destination)
    return '辅助插件已安装；请保存并重启游戏以加载'
