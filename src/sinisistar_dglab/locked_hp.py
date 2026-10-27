"""Generic live 1-HP damage evidence, independent of enemy/CG identities.

Raw callback evidence is consumed once before either output planner runs.
Cached resources without a live player cannot establish this condition.
"""
from datetime import datetime,timezone
from copy import deepcopy
import math

WINDOW_SECONDS=8.
MIN_GAP_SECONDS=.2

def interaction(s):
    f=s.get('flow') or {}
    return s.get('bound') is True or (f.get('valid') is True and f.get('playing') is True)

def locked_hp_penalty(s):
    evidence=s.get('feedback_evidence') or {};hp=s.get('hp') or {}
    return (evidence.get('locked_hp_active') is True and s.get('valid') is True
            and type(s.get('player')) is int and s['player']>0
            and type(hp.get('current')) is int and hp['current'] in (0,1)
            and (hp['current']==0 or interaction(s)))

def live_struggle(s):
    """Actual active struggle at 1 HP during a flow, rather than a guessed name."""
    f=s.get('flow') or {};g=s.get('gacha') or {}
    return ((s.get('hp') or {}).get('current')==1 and f.get('valid') is True and f.get('playing') is True
            and f.get('type') in ('HierarchyEventPlayer','PlayableDirectorPlayer') and bool(f.get('name'))
            and g.get('active') is True
            and all(type(g.get(k)) in (int,float) and math.isfinite(g[k]) for k in ('value','threshold'))
            and g['value']>=0 and g['threshold']>0)

class LockedHpEvidence:
    def __init__(self):self.reset()
    def reset(self):
        self.identity=None;self.first_at=None;self.last_at=None;self.last_sequence=None;self.active=False;self.count=0;self.evidence_source='live_damage_callback'

    def update(self,s,callbacks=(),*,now,wall_now=None):
        s=deepcopy(s);s.pop('feedback_evidence',None)
        wall_now=wall_now or datetime.now(timezone.utc)
        hp=s.get('hp') or {};f=s.get('flow') or {}
        identity=(s.get('session'),s.get('pid'),s.get('player'),s.get('scene_id'))
        fresh=s.get('live') is True and 0<=now-s.get('sampled_at',0)<.6
        real=(s.get('source')=='bepinex' and s.get('valid') is True and type(s.get('player')) is int and s['player']>0
              and type(s.get('pid')) is int and s['pid']>0 and isinstance(s.get('session'),str) and bool(s['session']))
        resources=(type(hp.get('current')) is int and type(hp.get('max')) is int and hp['max']>0 and hp['current'] in (0,1))
        # Cached resources, loading, gallery, recovery and free control clear evidence.
        eligible=(fresh and real and resources and not s.get('loading') and not str(s.get('scene','')).startswith(('Ga_','Gallery'))
                  and (hp['current']==0 and self.active or interaction(s)))
        if identity!=self.identity or not eligible:self.reset();self.identity=identity
        if eligible:
            # Timeline pauses while awaiting a struggle result. Repeated live
            # damage can establish evidence there; the real game pause cannot.
            paused=bool(s.get('paused'))
            rate=s.get('time_scale')
            stopped=not isinstance(rate,(int,float)) or not math.isfinite(rate) or rate<=0
            if paused or stopped:
                # An existing episode remains identifiable, but planners gate output.
                self.first_at=None;self.last_at=None
            elif live_struggle(s):
                self.active=True;self.evidence_source='live_struggle'
            elif hp['current']==1 and not self.active:
                for e in callbacks:
                    if (not isinstance(e,dict) or e.get('history') or e.get('event_type')!='damage_callback'
                        or any(e.get(k)!=s.get(k) for k in ('session','pid','player'))
                        or type(e.get('sequence')) is not int or (self.last_sequence is not None and e['sequence']<=self.last_sequence)
                        or any(type(e.get(k)) is not int for k in ('before_hp','remain_hp','spend_hp'))
                        or (e['before_hp'],e['remain_hp'],e['spend_hp'])!=(1,1,0)):continue
                    try:
                        stamp=datetime.fromisoformat(e['utc'].replace('Z','+00:00'))
                        age=(wall_now-stamp).total_seconds()
                    except (KeyError,ValueError,TypeError,AttributeError):continue
                    if not 0<=age<.6:continue
                    at=stamp.timestamp();self.last_sequence=e['sequence']
                    if self.last_at is not None and at-self.last_at<MIN_GAP_SECONDS:continue
                    if self.first_at is None or at-self.first_at>WINDOW_SECONDS:
                        self.first_at=at;self.count=1
                    else:self.count+=1
                    self.last_at=at
                    if self.count>=2:self.active=True;break
        s['feedback_evidence']=dict(locked_hp_active=self.active,locked_hp_count=self.count,
                                    locked_hp_window=WINDOW_SECONDS,source=self.evidence_source)
        return s
