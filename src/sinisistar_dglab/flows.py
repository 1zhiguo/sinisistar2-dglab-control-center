"""A catalog of encountered runtime identities; no guessed CG classification."""
from copy import deepcopy
from datetime import datetime,timezone
import json
from pathlib import Path
from .simulation import zero_hp_capture
from .penalty_flows import flow_classification

class FlowCatalog:
    def __init__(self,path):
        self.path=Path(path);self.items={};self._last=None;self._run=None
        try:
            rows=json.loads(self.path.read_text(encoding='utf-8'))
            if isinstance(rows,list):self.items={x['key']:x for x in rows[:500] if isinstance(x,dict) and isinstance(x.get('key'),str)}
        except (OSError,ValueError,KeyError):pass
    def observe(self,s):
        flow=s.get('flow') or {}
        if not s.get('live'):return False
        capture=bool(s.get('valid') and zero_hp_capture(s) and s.get('binder') and not flow.get('playing'))
        if capture:
            # The identity covers the enemy's current zero-HP captivity, not
            # an individual animation variant or a GameOver callback.
            flow=dict(valid=True,playing=True,key=json.dumps(['capture',s.get('scene_id'),s['binder'],'zero_hp'],ensure_ascii=False),
                      name=s['binder']+' · 零血受制',type=s['binder'],group='怪物内部流程',run=s.get('player'),
                      label='零血且仍被抓取',defeat_confirmed=False)
        if not flow.get('valid') or not flow.get('playing') or not flow.get('key'):
            self._last=None;self._run=None;return False
        key=flow['key'];token=(s.get('session'),flow.get('run'),key,flow.get('label'),flow.get('defeat_confirmed'))
        if token==self._last:return False
        self._last=token
        new_run=self._run!=(s.get('session'),flow.get('run'),key);self._run=(s.get('session'),flow.get('run'),key)
        is_new=key not in self.items
        row=self.items.setdefault(key,dict(key=key,name=flow.get('name') or flow.get('type') or '未命名演出',scene=s.get('scene',''),group=flow.get('group',''),labels=[],defeat_confirmed=False))
        row.update(kind='capture_penalty' if capture else 'event_player',runtime_verified=True,precise_cg_verified=False)
        label=flow.get('label')
        new_label=bool(label and label not in row['labels'])
        new_evidence=bool(flow.get('defeat_confirmed') and not row['defeat_confirmed'])
        if not (is_new or new_run or new_label or new_evidence):return False
        if new_label:row['labels'].append(label);row['labels']=row['labels'][-150:]
        row.update(last_seen=datetime.now(timezone.utc).isoformat(),defeat_confirmed=row['defeat_confirmed'] or flow.get('defeat_confirmed') is True)
        while len(self.items)>500:self.items.pop(next(k for k in self.items if k!=key))
        self.path.parent.mkdir(parents=True,exist_ok=True)
        tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps(list(self.items.values())[-500:],ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(self.path)
        return True
    def rows(self):
        rows=deepcopy(list(self.items.values()))
        for row in rows:
            try:
                scene,group,name,kind=json.loads(row['key'])
                row['penalty_classification'],row['penalty_label']=flow_classification(scene,dict(group=group,name=name,type=kind))
            except (ValueError,TypeError,KeyError):row.update(penalty_classification='',penalty_label='')
        return sorted(rows,key=lambda x:x.get('last_seen',''),reverse=True)
