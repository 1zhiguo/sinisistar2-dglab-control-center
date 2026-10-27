"""Independent gallery configuration and playback clock; no device operations."""
from copy import deepcopy
from .cg_policy import make_cg,sanitize_cg
from .gallery import SCENES,describe_gallery

def is_gallery(s):
    return type(s.get('scene_id')) is int and s['scene_id'] in SCENES and SCENES[s['scene_id']]==s.get('scene')

def make_gallery(death):
    c=make_cg(death,inherit=False,split=True)
    c.update(pause_on_stop=True)
    c['rule'].update(enabled=False,name='图鉴回放反馈',death_mode='until_end')
    return c

def sanitize_gallery(raw,death,sanitize_rule):
    default=make_gallery(death)
    if not isinstance(raw,dict):return default
    source=deepcopy(raw)
    source['rule']=dict(default['rule'],**(raw.get('rule') if isinstance(raw.get('rule'),dict) else {}))
    c=sanitize_cg(source,death,sanitize_rule)
    c.update(inherit_death=False,same_hp_enabled=False,pause_on_stop=raw.get('pause_on_stop',True) is True)
    c['rule'].update(name='图鉴回放反馈',death_mode='until_end',pulse_max=False,vibration_max=False)
    return c

def gallery_gate(s,now,config,*,ignore_pause=False):
    view=describe_gallery(s,now);g=s.get('gallery') or {}
    if not view['inGallery']:return '等待新鲜图鉴数据'
    if not config or not (config.get('rule') or {}).get('enabled'):return '回想模式不参与 · 图鉴反馈未启用'
    if s.get('loading'):return '图鉴加载中'
    if not view['dedicatedAvailable']:return '等待图鉴专用字段'
    if not view['selectionActive']:return '图鉴列表 / 预览 · 停止输出'
    if type(g.get('enemy_id')) is not int or g['enemy_id']<0:return '图鉴怪物身份尚未就绪'
    if type(g.get('take_count')) is not int or not 0<g['selected_index_raw']<=g['take_count']:return '图鉴片段索引无效'
    if not ignore_pause and s.get('paused'):return '游戏已暂停'
    if not ignore_pause and config.get('pause_on_stop',True) and g.get('ui_paused'):return '图鉴 Space 已停止输出'
    if g.get('play_type_raw')!=1:return '此类图鉴动画尚未验证'
    if not view['takeSelected'] or any(type(g.get(k)) is not int or g[k]<=0 for k in ('take_player','take_data')):return '等待图鉴片段载入'
    # CurrentTake can survive list exit. The UI selection AND live player are
    # required. Internal event waits intentionally remain eligible.
    if not view['playing']:return '等待图鉴播放信号'
    return ''

class GalleryClock:
    def __init__(self):self.reset()
    def reset(self):
        self.session=None;self.selection=None;self.take=None;self.last_take=None;self.pending=None
        self.age=0.;self.last_at=None;self.stopped=False;self.running=False;self.episode=0
    def update(self,s,config,now):
        view=describe_gallery(s,now);g=s.get('gallery') or {}
        if not view['inGallery']:
            self.reset();return dict(ready=False,reason='等待新鲜图鉴数据',age=0.)
        session=(s.get('session'),s.get('pid'))
        if session!=self.session:self.reset();self.session=session
        delta=max(0.,min(.6,now-self.last_at)) if self.last_at is not None else 0.
        self.last_at=now
        selection=view['selectionIdentity']
        if not selection:
            self.selection=None;self.take=None;self.age=0.;self.running=False;self.stopped=False
            return dict(ready=False,reason='图鉴列表 / 预览 · 停止输出',age=0.)
        changed=selection!=self.selection
        if changed:
            self.selection=selection;self.pending=self.take or self.last_take;self.take=None
            self.age=0.;self.running=False;self.episode+=1
        reason=gallery_gate(s,now,config,ignore_pause=True)
        candidate=(g.get('take_player'),g.get('take_data')) if view['takeSelected'] else None
        if reason:
            self.running=False;return dict(ready=False,reason=reason,age=self.age)
        if self.take is None:
            if self.pending and candidate==self.pending:
                self.running=False;return dict(ready=False,reason='正在切换图鉴片段 · 等待新片段载入',age=0.)
            self.take=candidate;self.last_take=candidate;self.pending=None;self.age=0.;self.running=False
        elif self.take!=candidate:
            self.take=candidate;self.last_take=candidate;self.age=0.;self.running=False;self.episode+=1
        stopped=bool(s.get('paused') or config.get('pause_on_stop',True) and g.get('ui_paused'))
        if self.running and not self.stopped and not stopped:self.age+=delta
        self.stopped=stopped;self.running=True
        return dict(ready=not stopped,reason='图鉴已暂停 · 队列与渐强进度冻结' if stopped else '',age=self.age,
                    seed=str((self.session,self.selection,self.take,self.episode)),name=view['takeName'])
