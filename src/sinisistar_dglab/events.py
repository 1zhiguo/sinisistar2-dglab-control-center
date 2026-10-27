"""Snapshot edge classification. Candidate events never authorize output."""
import time

class EventDetector:
    def __init__(self): self.previous=None; self.grab=None
    def reset(self):self.previous=None;self.grab=None
    def update(self,s):
        events=[];p=self.previous; self.previous=s
        valid=lambda x: bool(x and x.get('valid') and x.get('live') and time.monotonic()-x.get('sampled_at',0)<.7)
        if not valid(s):self.reset();return events
        if not valid(p) or (s.get('pid'),s.get('player'),s.get('scene_id'),s['hp']['max'])!=(p.get('pid'),p.get('player'),p.get('scene_id'),p['hp']['max']):self.grab=None;return events
        if s.get('sample_id')==p.get('sample_id'):return events
        if s['paused'] or p['paused'] or s.get('time_scale')!=1 or p.get('time_scale')!=1:self.grab=None;return events
        def event(key,text,verified=False):events.append({'key':key,'text':text,'verified':verified})
        delta=p['hp']['current']-s['hp']['current']
        if delta>0:event('damage',f"HP {p['hp']['current']} → {s['hp']['current']} · −{delta}",True)
        if delta<0:event('heal',f"HP {p['hp']['current']} → {s['hp']['current']}",True)
        if s['hp']['current']==0 and p['hp']['current']>0:event('hp0','HP 归零 · 尚不能等同于 Game Over',True)
        if not p.get('bound') and s.get('bound'):
            self.grab={'reached':False};event('grab','进入抓取 · '+s.get('binder','未知敌人'))
        if self.grab:
            g=s.get('gacha') or {};value=g.get('value');threshold=g.get('threshold')
            if isinstance(value,(int,float)) and isinstance(threshold,(int,float)) and threshold>0 and value>=threshold:self.grab['reached']=True
            if p.get('bound') and not s.get('bound'):
                if self.grab['reached'] and s['hp']['current']>0:event('escape','挣扎达标后脱困 · 组合判定')
                else:event('release','抓取结束 · 释放原因待对照')
                self.grab=None
        if p.get('broken') is False and s.get('broken') is True:event('break','衣服由完整变为破损')
        before={(x['name'],x.get('level')) for x in p.get('abnormals',[])};after={(x['name'],x.get('level')) for x in s.get('abnormals',[])}
        if before!=after:event('abnormal','异常状态或等级变化')
        return events
