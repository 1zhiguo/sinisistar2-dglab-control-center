"""Independent game-to-vibration planner; no electrical unit conversion."""
from .channel_policy import planner_copy
import time
from .simulation import Simulator,death_penalty_stage
from .pulse import pulse_gate,PULSE_EVENTS
from .status_policy import positive_status
from .same_hp import same_hp_feedback
from .gallery_policy import is_gallery
from .cg_playback import describe_game_cg

def has_ovc_abnormal(s,profile):
    rules=profile.get('abnormals',{})
    return any(not positive_status(x) and isinstance(x.get('level'),(int,float)) and x['level']>0 and
               rules.get(x.get('name'),{}).get('enabled') and rules.get(x.get('name'),{}).get('vibration_enabled')
               for x in s.get('abnormals',[]) if isinstance(x,dict))

class OvcPlanner:
    def __init__(self):self.engine=Simulator()
    def reset(self):self.engine.reset(keep_death=True);self.engine.gallery_clock.reset()
    def update(self,s,profile,waves,*,now=None,enabled=False,emergency=False):
        now=time.monotonic() if now is None else now;abnormal=bool(s.get('valid') and has_ovc_abnormal(s,profile))
        if is_gallery(s):return self.engine.evaluate_gallery(s,profile,[],now,enabled,emergency,vibration_waves=waves,route='vibration')
        self.engine.gallery_clock.reset()
        playback=describe_game_cg(s,now)
        reason='急停已锁定' if emergency else '负鼠已暂停' if not enabled else pulse_gate(s,now,profile.get('zero_hp_mode','capture'),abnormal,same_hp_feedback(s,profile),profile=profile)
        self.engine.sync_death(s,now)
        if reason and not playback['recognized']:self.engine.reset(keep_death=True);return self.engine.blank(reason)
        filtered=planner_copy(profile);filtered['flows']=[];filtered['zero_hp_mode']='states' if abnormal else 'capture'
        if not (filtered.get('cg') or {}).get('inherit_death',True):filtered['cg']['rule']['pulse_enabled']=False
        restricted=bool(s.get('event_playing') or (s.get('flow') or {}).get('playing') or (s.get('hp') or {}).get('current')==0)
        death=death_penalty_stage(s)
        for key,rule in filtered['rules'].items():
            if key not in PULSE_EVENTS or (restricted and not ((death or playback['recognized']) and key=='defeat_hold')):rule['enabled']=False
            rule['pulse_enabled']=False
        for rule in filtered['abnormals'].values():
            rule['pulse_enabled']=False
            if not s.get('valid'):rule['enabled']=False
        return self.engine.evaluate(s,filtered,[],now=now,enabled=not bool(reason),emergency=emergency,vibration_waves=waves)
