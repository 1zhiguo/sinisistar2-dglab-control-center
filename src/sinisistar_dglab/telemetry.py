"""Fingerprint-bound, external read-only observer. No injected calls or writes."""
from __future__ import annotations
import hashlib, json, threading, time
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TYPES = json.loads((Path(__file__).parent/'assets/types.json').read_text(encoding='utf-8'))
BUILD = 'b869493305bbe587598c8709e7fe271f00d79d37803c6a8241946d6a6297499d'
METADATA = 'a56278d0162b6c148312b56fbe208b54ba9af2d3bad609ebf9349b7ae7ddc84b'

class Observer:
    def __init__(self, executable=None):
        self.executable = str(executable or ROOT/'SiNiSistar2_v1_3_1/WIN/SiNiSistar2.exe')
        self._lock=threading.Lock(); self._stop=threading.Event(); self._thread=None
        self._state={'live':False,'valid':False,'error':'等待游戏启动','source':'external','sample_id':0}

    def snapshot(self):
        with self._lock: return deepcopy(self._state)

    def start(self):
        if self._thread and self._thread.is_alive(): return
        self._stop.clear(); self._thread=threading.Thread(target=self._run,daemon=True,name='SiNiSistarObserver'); self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread: self._thread.join(2)

    def _publish(self,state):
        with self._lock: self._state=state

    def _run(self):
        from .memory import ProcessReader, find_process_id, find_module_base
        sequence=0
        while not self._stop.is_set():
            try:
                pid=find_process_id('SiNiSistar2.exe',self.executable)
                path=Path(self.executable).parent
                for file,digest in [(path/'GameAssembly.dll',BUILD),(path/'SiNiSistar2_Data/il2cpp_data/Metadata/global-metadata.dat',METADATA)]:
                    if hashlib.sha256(file.read_bytes()).hexdigest()!=digest: raise ValueError('游戏构建未验证：拒绝使用本版偏移')
                base=find_module_base(pid,'GameAssembly.dll')
                with ProcessReader(pid) as r:
                    if r.read(base,2)!=b'MZ': raise ValueError('模块身份无效')
                    while not self._stop.is_set():
                        state=self.read(r,base); sequence+=1
                        state.update(live=True,pid=pid,source='external',sample_id=sequence,sampled_at=time.monotonic())
                        self._publish(state); self._stop.wait(.1)
            except Exception as exc:
                self._publish({'live':False,'valid':False,'error':str(exc),'source':'external','sample_id':sequence})
                self._stop.wait(1)

    @staticmethod
    def read(r,base):
        q=r.pointer_value
        def prop(ptr,kind='i',ro=True):
            if not ptr: return None
            ptr+=0x14 if ro else 0x10
            return r.boolean(ptr) if kind=='b' else r.float32(ptr) if kind=='f' else q(ptr) if kind=='p' else r.int32(ptr)
        def param(obj):
            if not obj: return None
            return {'current':prop(q(obj+0x20)), 'max':prop(q(obj+0x28))}
        def cname(obj):
            if not obj:return ''
            k=q(obj); addr=q(k+0x10); data=bytearray()
            for i in range(128):
                b=r.read(addr+i,1)
                if b==b'\0':break
                data.extend(b)
            return data.decode('utf-8',errors='replace')
        root=q(q(q(base+0x2e8a040)+0xb8)+0x40)
        if not root or cname(root)!='ManagerList': raise ValueError('管理器尚未就绪')
        ps=q(root+0x88);om=q(root+0x50);ui=q(root+0x48);seq=q(root+0x28);ev=q(root+0x78);tm=q(root+0x98)
        scene=r.int32(seq+0xf8);player=prop(q(om+0x28),'p',False);change=q(seq+0x48)
        loading=r.boolean(change+0x10) if change else True
        hp=param(q(ps+0x60));mp=param(q(ps+0x68));dur=param(q(ps+0x58));dress=q(ps+0x48)
        data={'valid':False,'error':'场景加载中' if loading else '等待角色','scene':TYPES['SceneID'].get(str(scene),str(scene)),
              'scene_id':scene,'player':player,'loading':loading,'hp':hp,'mp':mp,'durability':dur,
              'paused':prop(q(ui+0xe0),'b'),'event_playing':r.boolean(ev+0x88),'event_paused':r.boolean(ev+0x60),
              'broken':prop(q(dress+0x18),'b') if dress else None,'bound':False,'binder':'','abnormals':[],'gacha':None}
        if player and cname(player)=='Lelia':
            data['identity_matches']=q(player+0xa0)==q(ps+0x60)
            data['initialized']=r.boolean(player+0xf0)
            la=q(player+0x250);bind=q(player+0x200);gb=q(player+0x208);gs=q(gb+0x28) if gb else 0
            data['anim']=TYPES['AnimState'].get(str(r.int32(la+0x24)),'—') if la else '—'
            data['bound']=prop(q(bind+0x10),'b',False) if bind else None
            data['binder']=cname(q(bind+0x28)) if bind else ''
            if gs:
                gp=q(gs+0x20);active=prop(q(gs+0x38),'b',False)
                data['gacha']={'active':active,'value':r.float32(gs+0x48),'threshold':r.float32(gp+0x10) if gp else None}
            release=q(gb+0x48) if gb else 0
            if release and q(release)==q(base+0x2e75e68):data['release_reason']=TYPES['GachaBind.ReleaseReason'].get(str(r.int32(release+0x28)),'未知')
            abnormal=q(ps+0x50);arr=q(abnormal+0x48) if abnormal else 0
            if arr:
                count=r.uint32(arr+0x18)
                if count>64:raise ValueError('异常状态数组无效')
                for i in range(count):
                    a=q(arr+0x20+i*8)
                    if a:data['abnormals'].append({'name':TYPES['AbnormalType'].get(str(r.int32(a+0x18)),'未知状态'),'level':prop(q(a+0x50))})
            data['valid']=bool(data['identity_matches'] and data['initialized'] and not loading and hp and hp['max'] and 0<=hp['current']<=hp['max']<=10000000 and data['paused'] is not None)
            if data['valid']:data['error']=''
        arr=q(tm+0x28)
        data['time_scale']=None
        if arr and r.uint32(arr+0x18)>1:
            setting=q(arr+0x28);data['time_scale']=prop(q(setting+0x28),'f') if setting else None
        data['valid']=bool(data['valid'] and q(q(q(base+0x2e8a040)+0xb8)+0x40)==root and prop(q(om+0x28),'p',False)==player and r.int32(seq+0xf8)==scene)
        return data
