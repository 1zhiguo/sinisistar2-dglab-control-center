"""Pulse adapter including zero-HP captivity; named CG rules are not routed."""
from copy import deepcopy
import math,time
from .simulation import Simulator,death_penalty_stage
from .status_policy import positive_status
from .locked_hp import locked_hp_penalty
from .scripted_go import scripted_go_penalty
from .same_hp import same_hp_feedback
from .gallery_policy import is_gallery,gallery_gate

PULSE_EVENTS=frozenset(('hp_loss','grab_hold','defeat_hold','grab_hp_loss','break'))

def has_pulse_abnormal(s,profile):
    rules=profile.get('abnormals',{})
    return any(not positive_status(x) and isinstance(x.get('level'),(int,float)) and x['level']>0 and
               rules.get(x.get('name'),{}).get('enabled') and rules.get(x.get('name'),{}).get('pulse_enabled')
               for x in s.get('abnormals',[]) if isinstance(x,dict))

def pulse_gate(s,now,zero_hp_mode='capture',abnormal_feedback=False,non_damage_feedback=False,*,profile=None):
    if not s.get('live') or not 0<=now-s.get('sampled_at',0)<.6:return '等待新鲜游戏数据'
    if is_gallery(s):return gallery_gate(s,now,(profile or {}).get('gallery'))
    if (s.get('source')!='bepinex' or not s.get('valid') or not isinstance(s.get('player'),int) or s['player']<=0) and not scripted_go_penalty(s):return '等待有效玩家'
    if not isinstance(s.get('pid'),int) or s['pid']<=0:return '玩家会话无效'
    if s.get('loading'):return '加载中'
    if s.get('paused'):return '游戏已暂停'
    captive=death_penalty_stage(s)
    if (s.get('event_playing') or (s.get('flow') or {}).get('playing')) and not (captive or abnormal_feedback or non_damage_feedback):return 'CG / 演出输出尚未开放'
    if (s.get('event_paused') or (s.get('flow') or {}).get('paused')) and not (locked_hp_penalty(s) or scripted_go_penalty(s) or non_damage_feedback):return '演出已暂停'
    if str(s.get('scene','')).startswith(('Ga_','Gallery')):return '回想模式不参与'
    hp=s.get('hp') or {}
    if type(hp.get('current')) is not int or type(hp.get('max')) is not int or not 0<=hp['current']<=hp['max'] or hp['max']<=0:return '玩家资源无效'
    if hp['current']==0 and not (captive or abnormal_feedback):return 'HP 归零 · 已脱离受制流程'
    if hp['current']==0 and zero_hp_mode=='stop':return '零血策略已设为暂停'
    if (locked_hp_penalty(s) or scripted_go_penalty(s)) and zero_hp_mode=='stop':return '战败策略已设为暂停'
    rate=s.get('time_scale')
    if locked_hp_penalty(s) and rate==0:return '游戏时间停止'
    if not isinstance(rate,(int,float)) or not math.isfinite(rate) or rate<0 or (rate==0 and not captive):return '游戏时间停止'
    return ''

class PulsePlanner:
    def __init__(self):self.engine=Simulator()
    def reset(self):self.engine.reset(keep_death=True);self.engine.gallery_clock.reset()
    def update(self,s,profile,waves,*,now=None,enabled=False,emergency=False):
        now=time.monotonic() if now is None else now
        if is_gallery(s):return self.engine.evaluate_gallery(s,profile,waves,now,enabled,emergency,route='pulse')
        self.engine.gallery_clock.reset()
        abnormal=bool(s.get('valid') and has_pulse_abnormal(s,profile))
        reason='急停已锁定' if emergency else 'Pulse 已暂停' if not enabled else pulse_gate(s,now,profile.get('zero_hp_mode','capture'),abnormal,same_hp_feedback(s,profile))
        self.engine.sync_death(s,now)
        if reason:self.engine.reset(keep_death=True);return self.engine.blank(reason)
        filtered=deepcopy(profile);filtered['flows']=[];filtered['zero_hp_mode']='states' if abnormal else 'capture'
        if not (filtered.get('cg') or {}).get('inherit_death',True):filtered['cg']['rule']['vibration_enabled']=False
        restricted=bool(s.get('event_playing') or (s.get('flow') or {}).get('playing') or (s.get('hp') or {}).get('current')==0)
        death=death_penalty_stage(s)
        for key,rule in filtered['rules'].items():
            if key not in PULSE_EVENTS or (restricted and not (death and key=='defeat_hold')):rule['enabled']=False
            rule['vibration_enabled']=False
        for rule in filtered['abnormals'].values():
            rule['vibration_enabled']=False
            if not s.get('valid'):rule['enabled']=False
        return self.engine.evaluate(s,filtered,waves,now=now,enabled=True)
