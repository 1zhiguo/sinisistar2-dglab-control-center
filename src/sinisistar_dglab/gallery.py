"""Read-only gallery playback observations. This module grants no output."""
import math,time
from .telemetry import TYPES

SCENES={int(k):v for k,v in TYPES['SceneID'].items() if v.startswith(('Ga_','Gallery'))}

def describe_gallery(s,now=None):
    now=time.monotonic() if now is None else now
    stamp=s.get('sampled_at');f=s.get('flow') or {}
    fresh=(s.get('source')=='bepinex' and s.get('live') is True
        and type(stamp) in (int,float) and math.isfinite(stamp) and 0<=now-stamp<.6
        and type(s.get('pid')) is int and s['pid']>0 and isinstance(s.get('session'),str) and bool(s['session']))
    inside=bool(fresh and type(s.get('scene_id')) is int and s['scene_id'] in SCENES and SCENES[s['scene_id']]==s.get('scene'))
    raw=s.get('gallery');g=raw if inside and isinstance(raw,dict) else {}
    dedicated=bool(g.get('available') is True and g.get('active') is True and g.get('guide_available') is True)
    index=g.get('selected_index_raw');guide_open=g.get('guide_open') is True
    # Verified in 0.4.2: 0 is the preview, positive indices match [1]/[2]/[3],
    # and returning to the list leaves stale take pointers behind at index -1.
    selected=bool(dedicated and guide_open and type(index) is int and index>0)
    playing=bool(inside and not s.get('loading') and f.get('valid') is True and f.get('playing') is True
        and f.get('type') in ('HierarchyEventPlayer','PlayableDirectorPlayer') and bool(f.get('name')) and f['name']!='Init'
        and (not dedicated or selected))
    phase='outside' if fresh else 'unavailable'
    if inside:phase='loading' if s.get('loading') else 'playing' if playing else 'preparing' if s.get('event_playing') or f.get('playing') else 'idle'
    rate=s.get('time_scale');game_paused=bool(s.get('paused'))
    internal_wait=bool(playing and (f.get('paused') or s.get('event_paused')) and not game_paused)
    if playing and game_paused:phase='paused'
    elif internal_wait:phase='event_wait'
    elif playing and type(rate) in (int,float) and rate==0:phase='time_stopped'
    if dedicated and not s.get('loading'):
        if not guide_open or type(index) is int and index<0:phase='browsing'
        elif index==0:phase='preview'
        elif selected and g.get('ui_paused') is True:phase='manual_stop'
        elif selected and not playing:phase='selected'
    label={'outside':'不在图鉴','unavailable':'图鉴信号不可用','loading':'图鉴载入中','idle':'图鉴场景 · 未检测到演出播放器',
           'preparing':'图鉴演出准备中','playing':'图鉴演出播放中','paused':'游戏已暂停',
           'event_wait':'图鉴演出内部等待','time_stopped':'图鉴时间停止','browsing':'图鉴列表 · 未播放',
           'preview':'图鉴预览页','manual_stop':'图鉴已手动停止（Space）','selected':'图鉴片段已选中 · 等待播放信号'}[phase]
    position=f.get('timeline_time');duration=f.get('timeline_duration')
    timeline=lambda x:x if type(x) in (int,float) and math.isfinite(x) and x>=0 else None
    identity=(s.get('session'),s.get('pid'),s.get('scene_id'),s.get('player'),f.get('run'),f.get('key')) if playing else None
    # Selection changes before the old take is replaced. Track these separately
    # so a new button index is never presented as a newly loaded old take.
    selection_id=(s.get('session'),s.get('pid'),g.get('enemy_id'),index) if selected else None
    take_id=(s.get('session'),s.get('pid'),g.get('take_player'),g.get('take_data'),g.get('take_name')) if selected and g.get('take_selected') is True else None
    controls={k:g.get(k) for k in ('ui_paused','slow','dev_mode','ui_hidden')} if dedicated else {}
    return dict(inGallery=inside,playing=playing,phase=phase,label=label,playerValid=bool(s.get('valid')) if fresh else False,
        name=f.get('name','') if playing else '',type=f.get('type','') if playing else '',identity=identity,
        run=f.get('run') if playing else None,scene=s.get('scene','') if inside else '',
        timelineTime=timeline(position) if playing else None,timelineDuration=timeline(duration) if playing else None,
        manualPauseConfirmed=bool(selected and type(g.get('ui_paused')) is bool),uniqueCgIdAvailable=False,
        dedicatedAvailable=dedicated,dedicatedError=str(g.get('error') or ''),takeIdentity=take_id,
        selectionIdentity=selection_id,selectionActive=selected,
        takeSelected=take_id is not None,takeName=str(g.get('take_name') or '') if take_id else '',
        enemyId=g.get('enemy_id') if dedicated else None,selectedIndexRaw=g.get('selected_index_raw') if dedicated else None,
        playType={0:'Animator',1:'EventPlayer'}.get(g.get('play_type_raw'),'未知') if dedicated else '',
        changing=g.get('changing') is True if dedicated else False,controls=controls,
        controlLabel=('Stop 已开启' if controls.get('ui_paused') is True else 'Stop 未开启') if dedicated else '等待新版观察插件',
        coverage='已验证 EventPlayer 图鉴切换与 Space；Animator 直接动画仍需验证')

class GalleryPlayback:
    def __init__(self):self.previous=None
    def update(self,s,now=None):
        current=describe_gallery(s,now);prior=self.previous or {};events=[]
        def add(key,text):events.append(dict(key=key,text=text))
        if current['inGallery'] and not prior.get('inGallery'):add('gallery_enter','进入图鉴 / 画廊')
        if prior.get('playing') and (not current['playing'] or current['identity']!=prior.get('identity')):
            add('gallery_play_end','图鉴播放器结束 / 变化：'+prior['name']+' · '+current['label'])
        if current['playing'] and (not prior.get('playing') or current['identity']!=prior.get('identity')):
            add('gallery_play_start','图鉴播放器开始：'+current['name']+' · '+current['type'])
        elif current['playing'] and current['phase']!=prior.get('phase'):
            add('gallery_play_state',current['label']+' · '+current['name'])
        if current['selectionIdentity'] and current['selectionIdentity']!=prior.get('selectionIdentity'):
            add('gallery_selection_change','图鉴选择：怪物 #'+str(current['enemyId'])+' · 片段 ['+str(current['selectedIndexRaw'])+']')
        if current['takeIdentity'] and current['takeIdentity']!=prior.get('takeIdentity'):
            add('gallery_take_change','图鉴载入片段：'+current['takeName']+' · '+current['playType'])
        if current['inGallery'] and current['phase']=='browsing' and prior.get('phase') not in (None,'browsing'):
            add('gallery_list','已返回图鉴列表 · 忽略残留片段指针')
        if current['dedicatedAvailable'] and current['controls']!=prior.get('controls'):
            add('gallery_controls','图鉴控制：'+current['controlLabel']+' · 慢放 '+str(current['controls'].get('slow'))+' · DevMode '+str(current['controls'].get('dev_mode'))+' · 隐藏界面 '+str(current['controls'].get('ui_hidden')))
        if prior.get('inGallery') and not current['inGallery']:
            add('gallery_signal_lost' if current['phase']=='unavailable' else 'gallery_leave',
                '图鉴读取信号失效' if current['phase']=='unavailable' else '已退出图鉴场景')
        self.previous=current;return events
