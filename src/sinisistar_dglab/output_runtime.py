"""Shared output decision path. No Qt, disk I/O or UI callbacks."""
from .pulse import pulse_gate,has_pulse_abnormal
from .ovc_plan import has_ovc_abnormal
from .same_hp import same_hp_feedback
from .gallery_policy import is_gallery
from .simulation import VIBRATION_WAVES

def plan_outputs(self,s,now):
    con=self._service.snapshot() if self._service else {}
    game_feedback_identity=(s.get('session'),s.get('pid'),'gallery') if is_gallery(s) else (s.get('session'),s.get('pid'),s.get('player'),s.get('scene_id'),(s.get('hp') or {}).get('max'))
    identity=(game_feedback_identity,con.get('controller_id'),con.get('target_id'))
    if identity!=self._identity:self._identity=identity;self._detector.reset();self._pulse_planner.reset();self._warm=0
    gate=pulse_gate(s,now,self._sim_profile['zero_hp_mode'],has_pulse_abnormal(s,self._sim_profile),same_hp_feedback(s,self._sim_profile),profile=self._sim_profile);ready=not gate
    if not ready:self._warm=0
    elif self._stamp!=s.get('sample_id'):self._warm+=1
    self._stamp=s.get('sample_id')
    enabled=bool(ready and self._warm>=2 and self._armed and not self._emergency and not self._sim_running and self._sim_source=='live')
    # Only top-level caps change here. Planners treat the shared nested
    # settings as read-only; copying every preset/status each 100 ms blocks
    # the GUI exactly when a new QML page needs to be incubated.
    pulse_profile=dict(self._sim_profile)
    for channel in self._channels:
        key=channel['key'].lower()
        pulse_profile['pulse_cap_'+key]=min(pulse_profile['pulse_cap_'+key],channel['limit'],con.get('limit_'+key) or 0)
    self._pulse_plan=self._pulse_planner.update(s,pulse_profile,self._waves,now=now,enabled=enabled,emergency=self._emergency)
    local=con.get('local_only') is True
    route_ok=local if self._connection['pulse_backend']=='mock' else (con.get('protocol')=='v4' if self._connection['pulse_backend']=='v4' else True)
    self._reason='急停已锁定' if self._emergency else '输出已暂停' if not self._armed else gate if gate else '等待状态基线' if self._warm<2 else '连接模式不匹配' if not route_ok else '等待 APP 配对与强度回报' if not con.get('feedback_known') else self._pulse_plan['reason']
    permitted=bool(enabled and route_ok and con.get('feedback_known') and not con.get('error'))
    if self._service:
        caps={c['key']:min(c['limit'],self._sim_profile['pulse_cap_'+c['key'].lower()]) for c in self._channels}
        allowed=self._service.set_output_permission(permitted,self._reason,hard_limits=caps)
        if allowed:
            frames={c:frame if self._pulse_channels[c] else None for c,frame in self._pulse_plan['pulse_stream'].items()}
            self._service.submit_plan(frames,generated_at=self._pulse_plan['generated_at'])
    ovc=self._ovc_service.snapshot() if self._ovc_service else {}
    ovc_identity=(game_feedback_identity,ovc.get('controller_id'),ovc.get('target_id'),ovc.get('selected_slot_id'))
    if ovc_identity!=self._ovc_identity:self._ovc_identity=ovc_identity;self._ovc_planner.reset();self._ovc_warm=0
    ovc_gate=pulse_gate(s,now,self._sim_profile['zero_hp_mode'],has_ovc_abnormal(s,self._sim_profile),same_hp_feedback(s,self._sim_profile),profile=self._sim_profile)
    if ovc_gate:self._ovc_warm=0
    elif self._ovc_stamp!=s.get('sample_id'):self._ovc_warm+=1
    self._ovc_stamp=s.get('sample_id')
    ovc_enabled=bool(not ovc_gate and self._ovc_warm>=2 and self._ovc_armed and not self._emergency and not self._sim_running and self._sim_source=='live')
    ovc_profile=dict(self._sim_profile)
    for channel in ('A','B'):
        key=channel.lower();ovc_profile['vibration_cap_'+key]=min(ovc_profile['vibration_cap_'+key],self._ovc_limits[channel],ovc.get('limit_'+key) or 0)
    vibration_waves=VIBRATION_WAVES+self._vibration_custom
    self._ovc_plan=self._ovc_planner.update(s,ovc_profile,vibration_waves,now=now,enabled=ovc_enabled,emergency=self._emergency)
    if self._ovc_service:
        accepted=self._ovc_service.set_output_permission(ovc_enabled and ovc.get('feedback_known') and not ovc.get('error'),self._ovc_plan['reason'],hard_limits={c:min(self._ovc_limits[c],self._sim_profile['vibration_cap_'+c.lower()]) for c in ('A','B')})
        if accepted:self._ovc_service.submit_plan({c:f if self._ovc_channels[c] else None for c,f in self._ovc_plan['vibration_stream'].items()},generated_at=self._ovc_plan['generated_at'])
