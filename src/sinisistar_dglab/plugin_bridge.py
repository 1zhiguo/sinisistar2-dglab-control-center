"""Read the BepInEx plugin's atomic heartbeat and append-only event stream."""
from __future__ import annotations
from .game_builds import compatible_snapshot
import json, threading, time, queue, re
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
from .telemetry import ROOT,TYPES,BUILD
STATUS_NAMES=json.loads((Path(__file__).parent/'assets/status-name-ids.json').read_text(encoding='utf-8'))

class PluginObserver:
    def __init__(self,directory=None):
        self.directory=Path(directory) if directory else ROOT/'SiNiSistar2_v1_3_1/WIN/BepInEx/plugins/SiNiSistarDGLab/telemetry'
        self.events=queue.Queue();self.output_events=queue.Queue();self._stop=threading.Event();self._lock=threading.Lock();self._thread=None
        self._state={'live':False,'valid':False,'source':'bepinex','error':'等待 BepInEx 插件心跳','sample_id':0}
        self._offset=None;self._partial=b''

    def start(self):
        if self._thread and self._thread.is_alive():return
        self._stop.clear();self._thread=threading.Thread(target=self._run,daemon=True,name='BepInExBridgeReader');self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:self._thread.join(2)

    def snapshot(self):
        with self._lock:return deepcopy(self._state)

    @staticmethod
    def decode(data,now=None):
        if not isinstance(data,dict) or data.get('schema')!=1 or data.get('source')!='bepinex' or not compatible_snapshot(data):raise ValueError('插件协议或游戏接口校验未通过')
        stamp=datetime.fromisoformat(re.sub(r'(\.\d{6})\d+(?=[+-]\d{2}:\d{2}$)',r'\1',data['utc'].replace('Z','+00:00')));age=((now or datetime.now(timezone.utc))-stamp).total_seconds()
        if not 0<=age<.6:raise ValueError('插件心跳已过期，等待游戏更新')
        if not isinstance(data.get('pid'),int) or data['pid']<=0 or not isinstance(data.get('session'),str) or not data['session']:raise ValueError('插件会话无效')
        for field in ['hp','mp','durability']:
            p=data.get(field)
            if p is not None and (not isinstance(p,dict) or not isinstance(p.get('current'),int) or not isinstance(p.get('max'),int) or not 0<=p['current']<=p['max']<=10000000):raise ValueError('插件资源数据无效')
        if data.get('valid') and data.get('hp') is None:raise ValueError('玩家 HP 尚未就绪')
        s=deepcopy(data);s.update(live=True,sampled_at=time.monotonic()-age,error='')
        s['scene']=TYPES['SceneID'].get(str(data.get('scene_id')),'未知场景');s['anim']=TYPES['AnimState'].get(str(data.get('anim_raw')),'—')
        s['abnormals']=[dict(x,name=TYPES['AbnormalType'].get(str(x.get('type_raw')),'未知状态 #'+str(x.get('type_raw'))),
                            localized_name=STATUS_NAMES.get(str(x.get('name_id')))) for x in data.get('abnormals',[]) if isinstance(x,dict)]
        return s

    def recent_events(self,session):
        """Display-only history; never enqueue old callbacks for output handling."""
        rows=[]
        try:
            with (self.directory/'events.jsonl').open('rb') as f:
                f.seek(max(0,f.seek(0,2)-512000))
                for line in f.read().splitlines():
                    try:
                        e=json.loads(line)
                        if isinstance(e,dict) and e.get('session')==session and e.get('event_type'):rows.append(e)
                    except (ValueError,UnicodeDecodeError):continue
        except OSError:pass
        return rows

    def _run(self):
        path=self.directory/'events.jsonl'
        while not self._stop.is_set():
            try:
                s=self.decode(json.loads((self.directory/'latest.json').read_text(encoding='utf-8-sig')))
                with self._lock:self._state=s
            except (OSError,ValueError,KeyError,TypeError) as e:
                message='等待插件加载 / '+str(e)
                try:
                    report=json.loads((self.directory/'compatibility.json').read_text(encoding='utf-8-sig'))
                    if report.get('status')=='incompatible':message='游戏接口检查未通过：'+'；'.join(str(x) for x in report.get('errors',[])[:3])
                except (OSError,ValueError,TypeError,AttributeError):pass
                with self._lock:self._state={'live':False,'valid':False,'source':'bepinex','error':message,'sample_id':0}
            try:
                size=path.stat().st_size
                if self._offset is None:self._offset=size
                if size<self._offset:self._offset=0;self._partial=b''
                with path.open('rb') as f:
                    f.seek(self._offset);buf=f.read(128000);self._offset=f.tell()
                lines=(self._partial+buf).split(b'\n');self._partial=lines.pop()
                if len(self._partial)>100000:self._partial=b''
                for line in lines:
                    try:
                        e=json.loads(line)
                        if isinstance(e,dict) and isinstance(e.get('event_type'),str):
                            for target in (self.events,self.output_events):
                                if target.qsize()<1000:target.put(e)
                    except (ValueError,UnicodeDecodeError):continue
            except OSError:pass
            self._stop.wait(.1)
