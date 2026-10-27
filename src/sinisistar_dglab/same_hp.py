"""Repeated live damage notifications during a playing, non-damaging scene.

Stable snapshot values and MP deltas never establish this evidence.
"""
from copy import deepcopy
from datetime import datetime,timezone
from .monitoring_time import parse_callback_time

WINDOW=8.
MIN_GAP=.2

def eligible(s):
    f=s.get('flow') or {};hp=s.get('hp') or {}
    return bool(s.get('source')=='bepinex' and s.get('valid') is True and type(s.get('player')) is int and s['player']>0
        and type(s.get('pid')) is int and s['pid']>0 and s.get('session') and not s.get('loading')
        and (s.get('event_playing') is True or f.get('valid') is True and f.get('playing') is True)
        and not str(s.get('scene','')).startswith(('Ga_','Gallery')) and not str(f.get('name','')).startswith('ForGallery')
        and type(hp.get('current')) is int and type(hp.get('max')) is int and 0<hp['current']<=hp['max'])

def same_hp_flow(s,timeout=None):
    e=s.get('feedback_evidence') or {};now=s.get('sampled_at',0)
    timeout=e.get('same_hp_timeout',3.) if timeout is None else timeout
    return bool(eligible(s) and e.get('same_hp_confirmed') is True and e.get('same_hp_value')==(s.get('hp') or {}).get('current')
        and isinstance(e.get('same_hp_last_at'),(int,float)) and 0<=now-e['same_hp_last_at']<timeout)

def same_hp_feedback(s,profile):
    c=profile.get('cg') or {}
    return bool(c.get('same_hp_enabled') and same_hp_flow(s,c.get('same_hp_timeout',3.)))

class SameHpFlowEvidence:
    def __init__(self):self.reset();self.episode=0
    def reset(self):self.identity=None;self.first=None;self.last=None;self.sequence=None;self.count=0;self.confirmed=False
    def update(self,s,callbacks=(),*,now,wall_now=None):
        s=deepcopy(s);ev=s.setdefault('feedback_evidence',{});wall_now=wall_now or datetime.now(timezone.utc)
        f=s.get('flow') or {};hp=(s.get('hp') or {}).get('current')
        identity=(s.get('session'),s.get('pid'),s.get('player'),s.get('scene_id'),f.get('run'),f.get('key'),hp)
        fresh=s.get('live') is True and 0<=now-s.get('sampled_at',0)<.6
        if identity!=self.identity or not fresh or not eligible(s):self.reset();self.identity=identity
        if fresh and eligible(s) and not s.get('paused') and s.get('time_scale',1)>0:
            for e in callbacks:
                if (not isinstance(e,dict) or e.get('history') or e.get('event_type')!='damage_callback'
                    or any(e.get(k)!=s.get(k) for k in ('session','pid','player'))
                    or ('scene_id' in e and e['scene_id']!=s.get('scene_id'))
                    or type(e.get('sequence')) is not int or self.sequence is not None and e['sequence']<=self.sequence
                    or type(e.get('before_hp')) is not int or type(e.get('remain_hp')) is not int
                    or e['before_hp']!=hp or e['remain_hp']!=hp):continue
                try:age=(wall_now-parse_callback_time(e['utc'])).total_seconds()
                except (KeyError,ValueError,TypeError,AttributeError):continue
                if not 0<=age<.6:continue
                self.sequence=e['sequence'];at=now-age
                if self.last is not None and at-self.last<MIN_GAP:continue
                if self.last is None or at-self.last>WINDOW:
                    self.count=0;self.confirmed=False;self.first=at
                self.count+=1;self.last=at
                if self.count>=2 and not self.confirmed:self.confirmed=True;self.episode+=1
        ev.update(same_hp_confirmed=self.confirmed,same_hp_count=self.count,same_hp_value=hp,
            same_hp_last_at=self.last,same_hp_episode=self.episode)
        return s
