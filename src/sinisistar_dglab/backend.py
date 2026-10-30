from __future__ import annotations
import base64, io, json, math, queue, time, threading
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from pathlib import Path
from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer, QUrl, QProcess
from PySide6.QtGui import QGuiApplication, QDesktopServices
from .events import EventDetector
from .telemetry import ROOT,TYPES
from .plugin_bridge import PluginObserver
from .monitoring import EventMonitor,statuses,parse_time
from .simulation import Simulator,default_profile,initial_profile,sanitize_profile,sanitize_rule,base_rule,VIBRATION_WAVES,demo_state,zero_hp_capture,death_penalty_stage
from .status_policy import positive_status,STATUS_CATALOG,normalize_abnormal
from .flows import FlowCatalog
from .pulse import PulsePlanner,pulse_gate,has_pulse_abnormal
from .ovc_plan import OvcPlanner,has_ovc_abnormal
from .hud_settings import HUD_DEFAULTS,sanitize_hud
from .trainer import TrainerBridge,install_trainer
from .device_setup import setup_status
from .penalty_flows import current_penalty_class
from .flow_semantics import FlowReview
from .locked_hp import LockedHpEvidence
from .scripted_go import scripted_go_penalty
from .cg_policy import effective_cg,make_cg,sanitize_cg
from .monster_catalog import MonsterCatalog
from .resource_preview import build_cache as build_monster_cache
from .same_hp import SameHpFlowEvidence,same_hp_flow,same_hp_feedback
from .cg_playback import describe_game_cg
from .cg_coverage import CgCoverage
from .cg_batch import CgBatchRecorder
from .gallery import GalleryPlayback,describe_gallery
from .gallery_policy import sanitize_gallery,is_gallery
from .localization import Localizer,LANGUAGES
from .tutorial import STEP_COUNT,TUTORIAL_VERSION
from . import __version__

WAVES=[
 {'key':'impact','name':'余烬 · 冲击','points':[0,.9,1,.65,.3,.12,0,0,.48,.3,.12,0,0,0,0,0]},
 {'key':'breath','name':'烛息 · 呼吸','points':[0,.06,.16,.3,.49,.68,.86,1,.93,.78,.57,.36,.18,.07,0,0]},
 {'key':'pulse','name':'钟鸣 · 脉冲','points':[0,.75,1,.2,0,0,.75,1,.2,0,0,.75,1,.2,0,0]},
 {'key':'surge','name':'暗潮 · 渐强','points':[0,.02,.05,.1,.18,.29,.43,.61,.82,1,.84,.6,.36,.16,.04,0]},
 {'key':'ripple','name':'涟漪 · 交替','points':[0,.4,.8,.4,0,.3,.6,.3,0,.2,.4,.2,0,.1,.2,0]},
]
WAVES+=json.loads((Path(__file__).parent/'assets/ricca-pulse-presets.json').read_text(encoding='utf-8'))

def default_rules():
    specs=[('damage','受到伤害','实时 HP 下降','已验证 · 当前构建',True),('grab','进入抓取','抓取状态开启，记录敌人类型','BepInEx 回调已观察',False),
           ('escape','成功挣脱','本次挣扎达标后脱困且仍存活','组合判定 · 待扩展',False),('break','服装破损','完整 → 破损的状态变化','状态边沿已观察',False),
           ('hp0','血量归零','仅表示零血，独立于 Game Over','零血已验证',False),('defeat','战败流程','区分原地恢复与游戏结束','需观察插件 / 对照',False),
           ('heal','生命恢复','同一角色的 HP 增加','数值已验证',False),('abnormal','异常状态变化','添加、解除或等级变化','类型与生效等级可读',False)]
    return [dict(key=k,name=n,description=d,evidence=e,output=o,enabled=o,channel='A' if o else 'B',strength=8,duration=.8,wave='impact' if o else 'breath') for k,n,d,e,o in specs]

class Backend(QObject):
    saveImportChanged=Signal()
    panicDetected=Signal()
    changed=Signal(); configChanged=Signal(); eventsChanged=Signal(); flowsChanged=Signal(); exitRequested=Signal(); hudChanged=Signal(); hudSettingsRequested=Signal(); trainerRequested=Signal(); detectorRequested=Signal(); installChanged=Signal(); monsterCatalogChanged=Signal(); toast=Signal(str); languageChanged=Signal(); tutorialRequested=Signal(); hotkeyChanged=Signal(); cgCoverageChanged=Signal(); cgBatchChanged=Signal()
    def __init__(self,*,offline=False,settings=None,parent=None,developer_tools=False):
        super().__init__(parent);self.offline=offline;self.settings=Path(settings) if settings else ROOT/'artifacts/settings.json'
        self._developer_tools=bool(developer_tools);self._cg_batch_active=False
        self._localizer=Localizer();self._language='zh-CN';self._tutorial_first_run=not self.settings.exists()
        self._tutorial=dict(version=TUTORIAL_VERSION,step=0,seen=False,completed=False);self._hotkey_manager=None;self._emergency_shortcut={'sequence':'Ctrl+F12','modifiers':2,'vk':123}
        self._event_batch=False;self._events_dirty=False;self._flows_dirty=False;self._event_lines=[];self._semantic_flows_cache=None
        self._shutdown_started=False;self._shutdown_errors=[];self._output_worker=None;self._state_for_publish=None;self._ui_publish_at=0.
        self._rules=default_rules();self._channels=[{'key':'A','limit':20,'frequency':30},{'key':'B','limit':20,'frequency':20}]
        self._waves=deepcopy(WAVES);self._vibration_custom=[];self._editing_route='pulse';self._selected='impact';self._points=list(WAVES[0]['points']);self._events=[]
        self._armed=False;self._emergency=False;self._emergency_resume={};self._service=None;self._qr='';self._qrurl='';self._observer=None
        self._live={};self._last={};self._detector=EventDetector();self._identity=None;self._warm=0;self._stamp=None;self._monitor=EventMonitor()
        self._locked_hp=LockedHpEvidence();self._same_hp=SameHpFlowEvidence()
        self._gallery=GalleryPlayback()
        self._cg_info={};self._cg_coverage=CgCoverage(self.settings.parent/'cg-coverage.json');self._cg_coverage_rows=self._cg_coverage.rows();self._cg_coverage_at=0.
        self._cg_batch=CgBatchRecorder(self.settings.parent/'cg-batch');self._cg_batch_state=self._cg_batch.snapshot();self._cg_batch_at=0.;self._cg_batch_export=''
        self._traces={'A':[0.0]*64,'B':[0.0]*64};self._trace_at=time.monotonic();self._trace_new=set()
        self._hud=False;self._ip='';self._port=10002;self._reason='输出已暂停';self._last_error='';self._status='等待游戏启动'
        self._sim_profile=initial_profile();self._simulator=Simulator();self._sim_running=False;self._sim_source='live';self._demo_start=0.
        for channel in self._channels:channel['limit']=int(self._sim_profile['pulse_cap_'+channel['key'].lower()])
        self._sim_plan=self._simulator.blank();self._flows=FlowCatalog(self.settings.parent/'observed-flows.json')
        self._flow_review=FlowReview(self.settings.parent/'flow-review.json')
        self._monsters=MonsterCatalog(self.settings.parent)
        self._monster_cache_state=dict(busy=False,ready=bool(self._monsters.images),progress=0,error='',message='怪物图鉴随包预览已就绪' if self._monsters.bundled_complete else '本地预览缓存已就绪' if self._monsters.images else '选择游戏目录后自动生成怪物图鉴预览')
        try:self._static_flows=json.loads((Path(__file__).parent/'assets/capture-candidates.json').read_text(encoding='utf-8'))['candidates']
        except (OSError,ValueError,KeyError):self._static_flows=[]
        try:self._flow_scenes=json.loads((Path(__file__).parent/'assets/flow-scene-candidates.json').read_text(encoding='utf-8'))['candidates']
        except (OSError,ValueError,KeyError):self._flow_scenes=[]
        self._pulse_planner=PulsePlanner();self._pulse_plan=self._pulse_planner.engine.blank('Pulse 已暂停')
        self._mock_app=None;self._mock_session=None;self._mock_pending=False;self._mock_restore=None;self._last_mock_path='';self._pulse_channels={'A':True,'B':True}
        self._v4=None;self._ovc_service=None;self._ovc_armed=False;self._ovc_channels={'A':True,'B':True};self._ovc_limits={c:int(self._sim_profile['vibration_cap_'+c.lower()]) for c in 'AB'}
        self._ovc_planner=OvcPlanner();self._ovc_plan=self._ovc_planner.engine.blank('负鼠已暂停');self._ovc_warm=0;self._ovc_stamp=None;self._ovc_identity=None
        self._ovc_traces={'A':[0.]*64,'B':[0.]*64};self._ovc_trace_new=set()
        self._connection={'pulse_backend':'mock','v3_port':10002,'v4_port':9998,'lan_ip':'','auto_enable':True};self._available_ips=[]
        self._auto_present=set();self._auto_pending={};self._auto_suppressed=set();self._auto_v3=None;self._auto_v3_pending=None;self._requested_devices={};self._diagnostics_at=0.
        self._dialogue_until=0.;self._dialogue_identity=None
        self._game_directory=ROOT/'SiNiSistar2_v1_3_1/WIN'
        self._install_manager=None;self._install_queue=queue.Queue();self._install_thread=None;self._game_candidates=[]
        self._launch_after_install=None;self._game_probe_at=0.;self._game_probe_thread=None
        self._install_state=dict(busy=False,phase='idle',progress=0,message='选择游戏目录，或自动查找附近的 SiNiSistar2。',error='',selectedPath='',valid=False,gameRunning=False,installedVersion='',payloadReady=False,needsRestart=False)
        self._hud_settings=dict(HUD_DEFAULTS);self._hud=self._hud_settings['enabled'];self._hud_adjusting=False
        self._hud_hotkey_registered=False;self._emergency_hotkey_registered=False
        self._trainer=TrainerBridge()
        self._save_importer=None;self._save_state=dict(available=False,canRestore=False,busy=False,message='',error='',directory='',backup='')
        self._load();self._history();self.log('system','控制中心已启动 · 输出保持暂停','系统')
        self._timer=QTimer(self);self._timer.setInterval(100);self._timer.timeout.connect(self.tick);self._timer.start()
        if not offline:self._observer=PluginObserver(self._telemetry_directory());self._observer.start()
        if not offline:self._start_output_worker()

    def _start_output_worker(self):
        from .output_worker import OutputWorker
        if self._output_worker:return
        self._output_worker=OutputWorker(on_panic=self.panicDetected.emit)
        self.panicDetected.connect(self.emergencyStop)
        self.configChanged.connect(self._publish_output_config)
        self.changed.connect(self._publish_output_controls)
        self.hotkeyChanged.connect(self._publish_output_controls)
        self._publish_output_config();self._publish_output_controls();self._output_worker.start()

    def _publish_output_config(self):
        if self._output_worker:
            self._output_worker.configure(self._sim_profile,self._waves,self._vibration_custom,self._channels,self._ovc_limits)
            self._publish_output_controls()

    def _publish_output_controls(self):
        if self._output_worker and not self._shutdown_started:
            self._output_worker.controls(observer=self._observer,service=self._service,ovc_service=self._ovc_service,
                armed=self._armed,ovc_armed=self._ovc_armed,emergency=self._emergency,sim_running=self._sim_running,sim_source=self._sim_source,
                connection=self._connection,pulse_channels=self._pulse_channels,ovc_channels=self._ovc_channels,
                shortcut=self._emergency_shortcut,hotkey_active=self._emergency_hotkey_registered and not bool(self._hotkey_manager and self._hotkey_manager.capturing))

    @Property(str,constant=True)
    def appVersion(self):return __version__

    @Property(bool,constant=True)
    def developerTools(self):return self._developer_tools

    @Property(str,notify=languageChanged)
    def language(self):return self._language

    @Slot(str,str,result=str)
    def translate(self,text,language):
        if language=='zh-CN':return text
        if any(text==w.get('name') for w in self._waves if w['key'].startswith('custom_')) or any(text==w.get('name') for w in self._vibration_custom):return text
        return self._localizer.translate(text,language)

    @Slot(str)
    def setLanguage(self,language):
        if language not in LANGUAGES or language==self._language:return
        self._language=language;self.save();self.languageChanged.emit();self._emit_changed()

    @Property('QVariantMap',notify=configChanged)
    def tutorialState(self):return dict(self._tutorial,autoShow=bool(not self.offline and self._tutorial_first_run and not self._tutorial['seen']))

    @Property('QVariantList',notify=languageChanged)
    def tutorialSteps(self):
        from .tutorial import steps
        return steps(self._language)

    @Slot()
    def openTutorial(self):self.tutorialRequested.emit()

    @Slot(int,bool)
    def saveTutorial(self,step,completed=False):
        self._tutorial.update(version=TUTORIAL_VERSION,step=int(self._clamp(step,0,STEP_COUNT-1)),seen=True,completed=bool(completed) or self._tutorial['completed'])
        self.save();self.configChanged.emit()

    @Property('QVariantMap',notify=hotkeyChanged)
    def hotkeySettings(self):
        return self._hotkey_manager.snapshot() if self._hotkey_manager else dict(sequence=self._emergency_shortcut['sequence'],registered=False,capturing=False,candidate={},error='')

    @Slot()
    def beginHotkeyCapture(self):
        if self._hotkey_manager:self._hotkey_manager.begin()

    @Slot()
    def cancelHotkeyCapture(self):
        if self._hotkey_manager:self._hotkey_manager.cancel()

    @Slot()
    def saveEmergencyHotkey(self):
        if self._hotkey_manager:self._hotkey_manager.apply()

    @Slot()
    def resetEmergencyHotkey(self):
        if self._hotkey_manager:
            from .hotkeys import DEFAULT
            self._hotkey_manager.apply(dict(DEFAULT))

    def _history(self):
        paths=sorted((ROOT/'.analysis').glob('runtime-*.jsonl'),key=lambda p:p.stat().st_mtime,reverse=True)
        for p in paths:
            try:
                with p.open('rb') as f:
                    f.seek(max(0,p.stat().st_size-32000));lines=f.read().splitlines()
                for line in reversed(lines):
                    r=json.loads(line)
                    if 'hp' in r:
                        self._last={'hp':r.get('hp'),'mp':r.get('mp'),'durability':r.get('durability'),'scene':r.get('scene','—'),'anim':r.get('anim','—'),
                                    'paused':r.get('ui_paused'),'bound':r.get('bound'),'binder':r.get('binder_class',''),'broken':r.get('broken'),
                                    'abnormals':[{'name':x.get('type','未知状态'),'level':x.get('level_property'),'type_raw':x.get('type_raw')} for x in r.get('added_abnormals',[])]}
                        return
            except (OSError,ValueError):continue

    def _load(self):
        try:self._apply(json.loads(self.settings.read_text(encoding='utf-8')))
        except (OSError,ValueError,TypeError,KeyError):pass

    def _apply(self,data):
        if not isinstance(data,dict):raise ValueError('配置格式无效')
        self._language=data.get('language') if data.get('language') in LANGUAGES else 'zh-CN'
        tutorial=data.get('tutorial') or {};same_guide=tutorial.get('version')==TUTORIAL_VERSION
        self._tutorial=dict(version=TUTORIAL_VERSION,step=int(self._clamp(tutorial.get('step',0),0,STEP_COUNT-1)) if same_guide else 0,
                            seen=tutorial.get('seen') is True,completed=same_guide and tutorial.get('completed') is True)
        from .hotkeys import normalize_shortcut
        self._emergency_shortcut=normalize_shortcut(data.get('emergency_hotkey'))
        self._sim_profile=sanitize_profile(data.get('simulation',{}))
        self._hud_settings=sanitize_hud(data.get('hud',{}))
        self._hud=self._hud_settings['enabled']
        if isinstance(data.get('game_directory'),str) and data['game_directory']:self._game_directory=Path(data['game_directory'])
        connection=data.get('connections',{})
        if isinstance(connection,dict):
            self._connection['auto_enable']=connection.get('auto_enable',True) is True
            if connection.get('pulse_backend') in ('mock','v3','v4'):self._connection['pulse_backend']=connection['pulse_backend']
            for key in ('v3_port','v4_port'):self._connection[key]=int(self._clamp(connection.get(key,self._connection[key]),1024,65535))
            self._connection['lan_ip']=str(connection.get('lan_ip',''))[:64]
        for channel in ('A','B'):self._ovc_limits[channel]=int(self._clamp((data.get('ovc_limits') or {}).get(channel,50),0,200)//10)*10
        from .quick_policy import needs_ovc_preset_upgrade
        if needs_ovc_preset_upgrade(data.get('simulation')) and self._sim_profile['quick_active_preset']:
            self._ovc_limits={c:int(self._sim_profile['vibration_cap_'+c.lower()]) for c in 'AB'}
        for entry in data.get('rules',[]):
            for rule in self._rules:
                if entry.get('key')==rule['key']:
                    rule.update(enabled=entry.get('enabled') is True,channel='B' if entry.get('channel')=='B' else 'A',strength=self._clamp(entry.get('strength',8),0,100),duration=self._clamp(entry.get('duration',.8),.1,5),wave=str(entry.get('wave','impact')))
        for i,c in enumerate(data.get('channels',[])[:2]):self._channels[i].update(limit=int(self._clamp(c.get('limit',20),0,100)),frequency=int(self._clamp(c.get('frequency',30),1,100)))
        for w in data.get('custom_waves',[])[:20]:
            points=w.get('points',[])
            if len(points)==16 and all(isinstance(v,(int,float)) and math.isfinite(v) and 0<=v<=1 for v in points):
                key=str(w.get('key',''))
                if key.startswith('custom_') and key not in [x['key'] for x in self._waves]:self._waves.append({'key':key,'name':str(w.get('name','自定义'))[:32],'points':points})
        for w in data.get('custom_vibration_waves',[])[:20]:
            points=w.get('points',[]);key=str(w.get('key',''))
            if key.startswith('vib_custom_') and len(points)==16 and all(isinstance(v,(int,float)) and math.isfinite(v) and 0<=v<=1 for v in points):
                self._vibration_custom.append({'key':key,'name':str(w.get('name','自定义震动'))[:32],'points':points})

    @staticmethod
    def _clamp(v,a,b):
        try:v=float(v)
        except (ValueError,TypeError):return a
        return max(a,min(b,v)) if math.isfinite(v) else a

    def save(self):
        self.settings.parent.mkdir(parents=True,exist_ok=True)
        data={'version':3,'rules':self._rules,'channels':self._channels,'custom_waves':[w for w in self._waves if w['key'].startswith('custom_')],'custom_vibration_waves':self._vibration_custom,'simulation':self._sim_profile,'hud':self._hud_settings,'connections':self._mock_restore if self._mock_session and self._mock_restore else self._connection,'ovc_limits':self._ovc_limits,'game_directory':str(self._game_directory)}
        data.update(language=self._language,tutorial=self._tutorial,emergency_hotkey=self._emergency_shortcut)
        tmp=self.settings.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(self.settings)
        if self._mock_session:self._mock_session.profile(self._sim_profile,self._channels,self._ovc_limits)

    def log(self,key,text,tag='观察'):
        now=datetime.now(timezone(timedelta(hours=8)))
        row={'time':now.strftime('%H:%M:%S'),'utc':now.isoformat(),'key':key,'text':text,'tag':tag}
        self._events.insert(0,row);self._events=self._events[:150];self._notify_events()
        line=json.dumps(row,ensure_ascii=False)+'\n'
        if self._event_batch:self._event_lines.append(line)
        else:self._write_event_lines([line])

    def _write_event_lines(self,lines):
        if not lines:return
        p=self.settings.parent/'events.jsonl';p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('a',encoding='utf-8') as f:f.writelines(lines)

    def _notify_events(self):
        if self._event_batch:self._events_dirty=True
        else:self.eventsChanged.emit()

    def _notify_flows(self):
        self._semantic_flows_cache=None
        if self._event_batch:self._flows_dirty=True
        else:self.flowsChanged.emit()

    def _emit_changed(self,*,live=False):
        now=time.monotonic()
        if live and now-self._ui_publish_at<.2:return
        self._ui_publish_at=now
        # All QML consumers see one coherent snapshot per notification. The
        # temporary cache is cleared afterwards, so direct API reads stay fresh.
        if self._state_for_publish is not None:
            self.changed.emit();return
        self._state_for_publish=self.state
        try:self.changed.emit()
        finally:self._state_for_publish=None

    @Property('QVariantMap',notify=changed)
    def state(self):
        if self._state_for_publish is not None:return self._state_for_publish
        live=self._live;fresh=live.get('live') and time.monotonic()-live.get('sampled_at',0)<.6
        valid=bool(fresh and live.get('valid'));s=live if valid else self._last
        con=self._service.snapshot() if self._service else {}
        ovc=self._ovc_service.snapshot() if self._ovc_service else {}
        ovc_channels={c:dict(ovc.get('output_channels',{}).get(c,{'active':False,'strength':0}),
                            limit=min(self._ovc_limits[c],self._sim_profile['vibration_cap_'+c.lower()],ovc.get('limit_'+c.lower()) or 0),reported=ovc.get('strength_'+c.lower()),
                            wave=next((row.get('vibration_wave_'+c,row['vibration_wave']) for row in self._ovc_plan.get('active',[]) if any(row['name'] in selected for selected in self._ovc_plan.get('selected',{}).get('vibration'+c,[]))),''),trace=list(self._ovc_traces[c])) for c in ('A','B')}
        def value(name,part='current'):
            x=s.get(name);return x.get(part) if isinstance(x,dict) else None
        abnormal_rows=statuses(s.get('abnormals',[]),self._sim_profile);gallery=describe_gallery(live)
        return {'hp':value('hp'),'maxHp':value('hp','max'),'mp':value('mp'),'maxMp':value('mp','max'),'durability':value('durability'),'maxDurability':value('durability','max'),
                'scene':live.get('scene','等待游戏') if fresh else s.get('scene','等待游戏'),'anim':s.get('anim','—'),'paused':s.get('paused') is True,'bound':s.get('bound') is True,'binder':s.get('binder') or '未被抓取',
                'valid':valid,'sourceLabel':'图鉴实时只读' if gallery['inGallery'] else '实时只读' if valid else '演出实时 / 角色不可用' if fresh and scripted_go_penalty(live) else '历史快照' if self._last else '暂无数据','gameStatus':self._status,'error':live.get('error',''),
                'armed':self._armed,'emergency':self._emergency,'outputReason':self._reason,'serverReady':con.get('server_ready',False),'connected':con.get('connected',False),
                'pulseSetup':self._device_setup('pulse',con),'ovcSetup':self._device_setup('ovc',ovc),
                'feedbackKnown':con.get('feedback_known',False),'strengthA':con.get('strength_a'),'strengthB':con.get('strength_b'),'limitA':con.get('limit_a'),'limitB':con.get('limit_b'),
                'traceA':list(self._traces['A']),'traceB':list(self._traces['B']),'outputActive':con.get('output_active',False),'outputChannel':con.get('output_channel',''),'outputStrength':con.get('output_strength',0),
                'outputChannels':con.get('output_channels',{}),'pulseLocalTest':con.get('local_only',self._connection['pulse_backend']=='mock'),'pulseStage':{'mock':'本机模拟 APP','v3':'DG-LAB V3','v4':'DG-LAB 4'}[self._connection['pulse_backend']],
                'ovcChannels':ovc_channels,'ovcConnected':ovc.get('connected',False),'ovcArmed':self._ovc_armed,'ovcStatus':ovc.get('reason') or ovc.get('error') or ('已连接' if ovc.get('connected') else '等待负鼠连接'),
                'dualMockConnected':bool(con.get('local_only') and ovc.get('local_only') and con.get('connected') and ovc.get('connected')),
                'ovcReason':self._ovc_plan['reason'],'ovcEnabledChannels':dict(self._ovc_channels),
                'pulseChannels':dict(self._pulse_channels),'mockApp':self._mock_app.snapshot() if self._mock_app else {'running':False,'connected':False,'commands':0,'pulsesA':0,'pulsesB':0,'error':''},
                'ip':con.get('lan_ip',self._ip),'port':con.get('port',self._port),'ips':con.get('available_ips',[]),'qrSource':self._qr,'qrUrl':self._qrurl,
                'deviceError':con.get('error',''),'deviceStatus':('模拟 APP 已配对' if con.get('local_only') else 'APP 已配对') if con.get('connected') else '等待 APP 配对' if con.get('server_ready') else '未开启连接',
                'hudDialogueActive':bool(fresh and not death_penalty_stage(live) and (live.get('event_playing') or (live.get('flow') or {}).get('playing') or time.monotonic()<self._dialogue_until)),
                'eventCount':len([e for e in self._events if e['tag']!='系统']),'abnormalCount':len(s.get('abnormals',[])),'hud':self._hud,
                'abnormals':abnormal_rows,'broken':s.get('broken'),'eventPlaying':s.get('event_playing') is True,
                'feedbackAbnormalCount':len({x['name'] for x in abnormal_rows if x['pulse_participates'] or x['ovc_participates']}),
                'pulseAbnormalCount':len({x['name'] for x in abnormal_rows if x['pulse_participates']}),
                'ovcAbnormalCount':len({x['name'] for x in abnormal_rows if x['ovc_participates']}),
                'abnormalTypeCount':sum(name!='None' for name in TYPES['AbnormalType'].values()),
                'enemyHitCount':self._monitor.counts.get('enemy_hit',0),'enemyKillCount':self._monitor.counts.get('enemy_kill',0),
                'observerVersion':live.get('observer_version','0.1.0') if fresh else '—','combatHooks':live.get('combat_hooks') or {},
                'gacha':s.get('gacha') or {},'hookCount':live.get('hook_count',0),'session':live.get('session',''),'pluginFresh':bool(fresh),
                'gamePid':live.get('pid',0),
                'flow':deepcopy(live.get('flow') or {}) if fresh else {},'flowHooks':live.get('flow_hooks') or {},
                'penaltyClassification':current_penalty_class(live)[0] if fresh else '',
                'penaltyLabel':current_penalty_class(live)[1] if fresh else '',
                'nonDamageLabel':('同值 HP 演出 · '+str((live.get('flow') or {}).get('name',''))) if fresh and same_hp_flow(live,(self._sim_profile.get('cg') or {}).get('same_hp_timeout',3.)) else '',
                'lockedHpEvidence':deepcopy(live.get('feedback_evidence') or {}) if fresh else {},
                'galleryPlayback':gallery,
                'cgPlayback':dict(self._cg_info),'cgDetectionMode':self._sim_profile.get('cg_detection_mode','hybrid'),
                'reader':'BepInEx · IL2CPP v1.3.1','pluginStatus':('插件在线 · '+str(live.get('hook_count',0))+' 个观察钩子') if fresh else '等待重启游戏并加载观察插件'}

    @Property('QVariantList',notify=configChanged)
    def rules(self):return deepcopy(self._rules)
    @Property('QVariantList',notify=configChanged)
    def channels(self):return deepcopy(self._channels)
    @Property('QVariantList',notify=configChanged)
    def waves(self):return deepcopy(self._waves)
    @Property('QVariantList',notify=eventsChanged)
    def events(self):return deepcopy(self._events)
    @Property('QVariantList',notify=eventsChanged)
    def monitorEvents(self):return deepcopy(self._monitor.rows)
    @Property('QVariantList',notify=eventsChanged)
    def eventCatalog(self):return self._monitor.catalog(self._live.get('combat_hooks'),self._live.get('flow_hooks'))
    @Property('QVariantList',notify=configChanged)
    def points(self):return list(self._points)
    @Property(str,notify=configChanged)
    def selectedWave(self):return self._selected
    @Property(str,notify=configChanged)
    def editingRoute(self):return self._editing_route
    @Property('QVariantMap',notify=changed)
    def simulation(self):return dict(deepcopy(self._sim_plan),running=self._sim_running,mode=self._sim_source)
    @Property('QVariantMap',notify=changed)
    def pulsePlan(self):return deepcopy(self._pulse_plan)
    @Property('QVariantMap',notify=configChanged)
    def simulationSettings(self):return deepcopy({k:v for k,v in self._sim_profile.items() if k not in ('rules','abnormals','flows')})
    @Property('QVariantMap',notify=configChanged)
    def cgSettings(self):
        c=effective_cg(self._sim_profile)
        if c.get('version')!=2:c=sanitize_cg(c,self._sim_profile['rules']['defeat_hold'],sanitize_rule)
        c['rule'].update(key='cg_hold',name='CG 观看反馈');return c

    @Property('QVariantMap',notify=configChanged)
    def gallerySettings(self):
        return sanitize_gallery(self._sim_profile.get('gallery'),self._sim_profile['rules']['defeat_hold'],sanitize_rule)

    @Property('QVariantList',notify=cgCoverageChanged)
    def cgCoverage(self):return deepcopy(self._cg_coverage_rows)

    @Property('QVariantMap',notify=cgBatchChanged)
    def cgBatch(self):return dict(deepcopy(self._cg_batch_state),exportPath=self._cg_batch_export)

    def _batch_profile(self):return dict(simulation=self._sim_profile,channels=self._channels,ovc_limits=self._ovc_limits,
        custom_waves=[w for w in self._waves if w['key'].startswith('custom_')],custom_vibration_waves=self._vibration_custom)

    def _refresh_batch(self):self._cg_batch_state=self._cg_batch.snapshot();self.cgBatchChanged.emit()

    @Slot()
    def beginCgBatch(self):
        self._cg_batch_active=True
        self._cg_batch.ensure(self._batch_profile());self._cg_batch.profile(self._batch_profile());self._cg_batch.save(force=True);self._refresh_batch()

    @Slot()
    def newCgBatch(self):self._cg_batch_active=True;self._cg_batch.new(self._batch_profile());self._refresh_batch()

    @Slot()
    def toggleCgBatch(self):
        if self._cg_batch.recording:self._cg_batch.pause()
        else:self._cg_batch.resume()
        self._refresh_batch()

    @Slot(str,str)
    def markCgBatch(self,key,verdict):
        ok=self._cg_batch.mark(key,verdict);self._refresh_batch()
        if not ok:self.toast.emit(self._cg_batch.error or '请先打开要测试的 CG')

    @Slot(str,str)
    def noteCgBatch(self,key,note):self._cg_batch.note(key,note);self._refresh_batch()

    @Slot(bool)
    def exportCgBatch(self,finish):
        try:
            if finish:self._cg_batch.finish()
            target=self._cg_batch.export();self._cg_batch_export=str(target)
            if finish and self._mock_session:self.stopMockBoth()
            self._refresh_batch();self.toast.emit('测试记录已导出：'+str(target))
        except (OSError,ValueError) as error:self.toast.emit('导出失败：'+str(error))

    @Slot()
    def openCgBatchFolder(self):
        path=Path(self._cg_batch_export).parent if self._cg_batch_export else self._cg_batch.root/'exports';path.mkdir(parents=True,exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    @Slot(str)
    def setCgDetectionMode(self,mode):
        if mode not in ('hybrid','playback_only'):return
        self._sim_profile['cg_detection_mode']=mode;self._simulation_changed()
        self._pulse_planner.engine.reset();self._ovc_planner.engine.reset()
        self.log('cg_ablation','仅 CG 播放信号 · 已屏蔽 HP、抓取和异常输出' if mode=='playback_only' else '恢复 CG 播放 + HP 兜底','系统')

    @Slot()
    def clearCgCoverage(self):
        self._cg_coverage.clear();self._cg_coverage_rows=self._cg_coverage.rows();self.cgCoverageChanged.emit()

    @Slot()
    def exportCgCoverage(self):
        data=dict(self._cg_coverage.report(),rows=self._cg_coverage.rows(),mode=self._sim_profile.get('cg_detection_mode','hybrid'),observer_version=self._live.get('observer_version'),mock_directory=self._last_mock_path)
        path=self.settings.parent/'cg-coverage-export.json';path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');self.toast.emit('覆盖报告已保存：'+str(path))

    @staticmethod
    def _cg_scope(selector):return 'gallery' if selector.startswith('gallery/') else 'cg'

    def _cg_edit(self,scope='cg'):
        if scope=='gallery':return self.gallerySettings
        c=sanitize_cg(self.cgSettings,self._sim_profile['rules']['defeat_hold'],sanitize_rule);c['inherit_death']=False;return c

    def _cg_save(self,c,scope='cg'):
        self._sim_profile[scope]=(sanitize_gallery if scope=='gallery' else sanitize_cg)(c,self._sim_profile['rules']['defeat_hold'],sanitize_rule)
        self._sim_profile['quick_active_preset']=''
        self._simulation_changed()
        self._pulse_planner.engine.reset();self._ovc_planner.engine.reset()

    @Slot(str)
    def syncCgFeedback(self,source):
        if source not in ('cg','gallery'):return
        target='gallery' if source=='cg' else 'cg'
        source_config=self._cg_edit(source);target_config=self._cg_edit(target)
        target_config['routes']=deepcopy(source_config['routes'])
        # Copy output strategies only. Each scope keeps its own eligibility,
        # master switch, end condition, same-HP and Space pause behavior.
        for field,value in source_config['rule'].items():
            if field.startswith(('pulse_','vibration_')):
                target_config['rule'][field]=deepcopy(value)
        self._cg_save(target_config,target)
        self.toast.emit('已同步到图鉴独立反馈，输出已暂停' if target=='gallery' else '已同步到游戏 CG 反馈，输出已暂停')

    @Slot(bool)
    def setGalleryPauseOnStop(self,enabled):
        c=self._cg_edit('gallery');c['pause_on_stop']=bool(enabled);self._cg_save(c,'gallery')

    @Slot(bool)
    def setSameHpFeedbackEnabled(self,enabled):
        c=self._cg_edit();c['same_hp_enabled']=bool(enabled);self._cg_save(c)

    @Slot(float)
    def setSameHpTimeout(self,seconds):
        c=self._cg_edit();c['same_hp_timeout']=self._clamp(seconds,.5,30);self._cg_save(c)

    @Slot(str,'QVariant')
    def setCgRule(self,field,value):
        scope=self._cg_scope(field);field=field.removeprefix('gallery/');c=self._cg_edit(scope)
        if field not in c['rule'] or field in ('key','name','pulse_max','vibration_max'):return
        c['rule'][field]=value
        if field in ('pulse_wave','vibration_wave'):
            catalog=self._waves if field=='pulse_wave' else self.vibrationWaves
            preset=next((w for w in catalog if w['key']==value),None)
            if not preset:return
            if preset.get('native_period'):c['rule'][field.replace('_wave','_period')]=preset['native_period']
        for route in ('pulse','vibration'):
            if field in (route+'_wave',route+'_period',route+'_ramp_seconds','pulse_frequency'):
                suffix=field[len(route)+1:] if field.startswith(route+'_') else 'frequency'
                for options in c['routes'][route].values():
                    options[suffix]=value
                    if suffix=='wave':options['period']=c['rule'][route+'_period']
        self._cg_save(c,scope)

    @Slot(str,str,float,float)
    def setCgStrengthRange(self,route,channel,low,high):
        scope=self._cg_scope(route);route=route.removeprefix('gallery/')
        if route not in ('pulse','vibration') or channel not in ('a','b'):return
        c=self._cg_edit(scope);maximum=min(100 if route=='pulse' else 200,self._sim_profile[route+'_cap_'+channel])
        high=self._clamp(high,0,maximum);low=self._clamp(low,0,high)
        c['rule'][route+'_start_strength_'+channel]=low;c['rule'][route+'_strength_'+channel]=high;self._cg_save(c,scope)

    @Slot(str,str,'QVariant')
    def setCgOption(self,route,field,value):
        scope=self._cg_scope(route)
        base,channels=self._cg_selector(route)
        if not channels or field not in ('mode','loop','end','ramp_mode','ramp_scope','ramp_steps','ramp_seconds','wave','period','frequency'):return
        c=self._cg_edit(scope)
        for channel in channels:
            c['routes'][base][channel][field]=value
            if field=='wave':
                preset=next((w for w in (self._waves if base=='pulse' else self.vibrationWaves) if w['key']==value),None)
                if not preset:return
                if preset.get('native_period'):c['routes'][base][channel]['period']=preset['native_period']
        self._cg_save(c,scope)

    @staticmethod
    def _cg_selector(selector):
        parts=selector.removeprefix('gallery/').split(':');route=parts[0]
        if route not in ('pulse','vibration'):return route,()
        return route,tuple('AB') if len(parts)==1 else (parts[1],) if len(parts)==2 and parts[1] in ('A','B') else ()

    @Slot(str,str)
    def addCgQueue(self,route,wave):
        scope=self._cg_scope(route)
        base,channels=self._cg_selector(route)
        if not channels:return
        catalog=self._waves if base=='pulse' else self.vibrationWaves
        preset=next((w for w in catalog if w['key']==wave),None)
        if not preset:return
        c=self._cg_edit(scope)
        for channel in channels:
            q=c['routes'][base][channel]['queue']
            if len(q)>=32:self.toast.emit('每个通道最多 32 条队列波形');return
            q.append(dict(wave=wave,seconds=10.,period=preset.get('native_period') or c['routes'][base][channel]['period']))
        self._cg_save(c,scope)

    @Slot(str,int,str,'QVariant')
    def setCgQueue(self,route,index,field,value):
        scope=self._cg_scope(route)
        base,channels=self._cg_selector(route)
        if not channels or field not in ('wave','seconds','period','scale'):return
        c=self._cg_edit(scope)
        for channel in channels:
            q=c['routes'][base][channel]['queue']
            if not 0<=index<len(q):return
            q[index][field]=value
            if field=='wave':
                preset=next((w for w in (self._waves if base=='pulse' else self.vibrationWaves) if w['key']==value),None)
                if not preset:return
                if preset.get('native_period'):q[index]['period']=preset['native_period']
        self._cg_save(c,scope)

    @Slot(str)
    def applyProgressiveCgQueue(self,route):
        scope='cg'
        from .cg_policy import progressive_queue
        if route not in ('pulse','vibration','both'):return
        c=self._cg_edit(scope)
        for r in (('pulse','vibration') if route=='both' else (route,)):
            for channel in 'AB':
                c['routes'][r][channel].update(mode='sequence',loop=True,end='hold',ramp_mode='linear',ramp_scope='cycle',ramp_seconds=60.,queue=progressive_queue(r,self._waves if r=='pulse' else self.vibrationWaves,channel))
            c['rule'][r+'_ramp_seconds']=60.
        c['rule']['death_mode']='until_end';self._cg_save(c,scope)
        self.toast.emit('已载入 60 秒五段递进队列 · 每段 12 秒 · 输出保持暂停')

    @Slot(str,int,int)
    def moveCgQueue(self,route,index,delta):
        scope=self._cg_scope(route)
        base,channels=self._cg_selector(route)
        if not channels or delta not in (-1,1):return
        c=self._cg_edit(scope);target=index+delta
        for channel in channels:
            q=c['routes'][base][channel]['queue']
            if not 0<=index<len(q) or not 0<=target<len(q):return
            q[index],q[target]=q[target],q[index]
        self._cg_save(c,scope)

    @Slot(str,int)
    def removeCgQueue(self,route,index):
        scope=self._cg_scope(route)
        base,channels=self._cg_selector(route)
        if not channels:return
        c=self._cg_edit(scope)
        for channel in channels:
            q=c['routes'][base][channel]['queue']
            if not 0<=index<len(q):return
            q.pop(index)
        self._cg_save(c,scope)

    @Slot()
    def copyDeathToCg(self):
        c=self._cg_edit();c['rule']=make_cg(self._sim_profile['rules']['defeat_hold'],inherit=False)['rule']
        self._cg_save(c)
    @Property('QVariantMap',notify=configChanged)
    def quickPolicy(self):
        from .quick_policy import current_values
        rule=self._sim_profile['rules']['defeat_hold']
        ranges={}
        for route in ('pulse','vibration'):
            for channel in 'AB':
                high=rule.get(route+'_strength_'+channel.lower());high=rule[route+'_strength'] if high is None else high
                low=rule.get(route+'_start_strength_'+channel.lower())
                if low is None:low=rule.get(route+'_start_strength')
                ranges[route+channel]=dict(low=high if low is None else min(low,high),high=high,seconds=rule[route+'_ramp_seconds'])
        return dict(presets=deepcopy(self._sim_profile['quick_presets']),active=self._sim_profile['quick_active_preset'],current=current_values(self._sim_profile),
                    deathRanges=ranges,
                    death={route+channel:rule.get(route+'_strength_'+channel.lower()) if rule.get(route+'_strength_'+channel.lower()) is not None else rule[route+'_strength'] for route in ('pulse','vibration') for channel in 'AB'},
                    deathMode=rule['death_mode'],deathSeconds=rule['death_seconds'],deathEnabled=rule['enabled'],pulseChannels=rule['pulse_channel'] if rule['pulse_enabled'] else '',ovcChannels=rule['vibration_channel'] if rule['vibration_enabled'] else '')
    @Property('QVariantList',notify=configChanged)
    def simulationEvents(self):return deepcopy(list(self._sim_profile['rules'].values()))
    @Property('QVariantList',notify=configChanged)
    def simulationAbnormals(self):return [dict(deepcopy(r),**STATUS_CATALOG.get(name,{}),feedback_excluded=positive_status(name)) for name,r in self._sim_profile['abnormals'].items()]

    @Slot('QVariantList',bool)
    def batchSetAbnormals(self,keys,enabled):
        count=0
        for key in set(k for k in keys if isinstance(k,str)):
            rule=self._sim_profile['abnormals'].get(key)
            if not rule or positive_status(key):continue
            rule['enabled']=bool(enabled)
            if enabled:rule['pulse_enabled']=True
            normalize_abnormal(rule);count+=1
        if count:
            self._sim_profile['quick_active_preset']='';self._simulation_changed()
            self.toast.emit(('已启用' if enabled else '已关闭')+str(count)+' 种异常反馈 · 输出保持暂停')
    @Property('QVariantList',notify=configChanged)
    def simulationFlows(self):return deepcopy(self._sim_profile['flows'])
    @Property('QVariantList',notify=configChanged)
    def vibrationWaves(self):return deepcopy(VIBRATION_WAVES+self._vibration_custom)
    @Property('QVariantMap',notify=changed)
    def ovcPlan(self):return deepcopy(self._ovc_plan)
    @Property('QVariantMap',notify=configChanged)
    def connectionSettings(self):return dict(self._connection,ips=list(self._available_ips))
    @Property('QVariantMap',notify=changed)
    def v4State(self):return self._v4.snapshot() if self._v4 else {'server_ready':False,'devices':[],'qr_url':''}
    @Property('QVariantList',notify=changed)
    def v4Devices(self):return self._v4.devices_snapshot() if self._v4 else []
    @Property('QVariantMap',notify=configChanged)
    def ovcLimits(self):return dict(self._ovc_limits)
    @Property('QVariantMap',notify=installChanged)
    def installState(self):return deepcopy(self._install_state)

    @Property('QVariantMap',notify=changed)
    def trainerState(self):
        state=self._trainer.state
        if not state.get('status_removal_available') and self._live.get('valid') and self._live.get('live') and 0<=time.monotonic()-self._live.get('sampled_at',0)<.6:
            state['abnormals']=[dict(type_raw=r['raw'],level=r['level'],name=r['name'],label=r['label'],positive=r['positive']) for r in statuses(self._live.get('abnormals',[]),self._sim_profile)]
            state['negative_count']=sum(not r['positive'] for r in state['abnormals'])
        return dict(state,installed=(self._game_directory/'BepInEx/plugins/SiNiSistarTrainer/SiNiSistarDGLab.Trainer.dll').is_file())

    @Slot()
    def openTrainer(self):self.trainerRequested.emit()

    @Property('QVariantMap',notify=saveImportChanged)
    def saveImportState(self):return dict(self._save_state)

    def _save_import_manager(self):
        if self._save_importer is None:
            from .save_import import SaveImporter
            info=self._installer().inspect_game(self._game_directory)
            if info.get('compatibility_mode')=='runtime-interface':raise ValueError('此渠道的存档路径尚未验证，暂不提供一键导入')
            self._save_importer=SaveImporter(build_profile=info.get('build_profile',''))
        return self._save_importer

    @Slot()
    def refreshSaveImport(self):
        try:self._save_state.update(self._save_import_manager().status())
        except Exception as error:self._save_state.update(available=False,error=str(error))
        self.saveImportChanged.emit()

    def _save_action(self,restore=False):
        if self.offline:self.toast.emit('离线预览不修改存档');return
        if self._install_state['busy'] or self._save_state['busy']:return
        self._armed=False;self._ovc_armed=False;self._reset_output()
        self._save_state.update(busy=True,error='',message='正在备份并导入…' if not restore else '正在恢复备份…');self.saveImportChanged.emit()
        def work():
            try:
                manager=self._save_import_manager()
                return dict(ok=True,**(manager.restore() if restore else manager.import_save()),**manager.status())
            except Exception as error:return dict(ok=False,error=str(error))
        self._run_install_task('save_restore' if restore else 'save_import',work)

    @Slot()
    def importFullCgSave(self):self._save_action()

    @Slot()
    def restoreImportedSave(self):self._save_action(True)

    @Slot()
    def openSaveBackupFolder(self):
        try:
            path=self._save_import_manager().backups
            if path.is_dir():QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        except Exception as error:self.toast.emit(str(error))

    @Slot()
    def installTrainer(self):
        if self.offline:self.toast.emit('离线预览不安装游戏辅助');return
        try:self._trainer.message=install_trainer(self._game_directory);self._trainer.error=''
        except Exception as error:self._trainer.error=str(error)
        self._emit_changed()

    @Slot(str,str,float)
    def modifyGameValue(self,attribute,mode,value):
        if self.offline:self.toast.emit('离线预览不修改游戏');return
        self._armed=False;self._ovc_armed=False;self._reset_output()
        try:
            self._trainer.poll(self._game_directory/'BepInEx/plugins/SiNiSistarTrainer/ipc')
            self._trainer.send(attribute,mode,value)
        except Exception as error:self._trainer.error=str(error)
        self._emit_changed()
    @Property('QVariantList',notify=installChanged)
    def gameCandidates(self):return deepcopy(self._game_candidates)

    def _telemetry_directory(self):return self._game_directory/'BepInEx/plugins/SiNiSistarDGLab/telemetry'

    def _installer(self):
        if self._install_manager is None:
            from .install_manager import InstallManager
            self._install_manager=InstallManager()
        return self._install_manager

    def _run_install_task(self,phase,work):
        if self._install_state['busy']:return
        self._install_state.update(busy=True,phase=phase,progress=0,error='',message='正在查找游戏目录…' if phase=='scan' else '正在检查游戏…' if phase=='inspect' else '正在准备安装…')
        self.installChanged.emit()
        def run():
            try:self._install_queue.put((phase,work()))
            except Exception as error:
                details=getattr(error,'details',{});location=details.get('path') or details.get('file') or details.get('staging_dir') or ''
                self._install_queue.put(('error',{'error':str(error)+(' · '+str(location) if location else ''),'code':getattr(error,'code','error')}))
        self._install_thread=threading.Thread(target=run,name='SiNiSistarPluginInstaller',daemon=False);self._install_thread.start()

    @Slot()
    def scanGameDirectories(self):
        def scan():
            rows=self._installer().discover_game_dirs(anchor=ROOT,extra_roots=(self._game_directory.parent,))
            chosen=next((x for x in rows if Path(x.get('game_dir') or '')==self._game_directory),None) or next((x for x in rows if x.get('supported')),None)
            if chosen:self._prepare_monster_cache(chosen)
            return rows
        self._run_install_task('scan',scan)

    @Slot(str)
    def chooseGameDirectory(self,path):
        if path.startswith('file:'):path=QUrl(path).toLocalFile()
        def inspect():
            info=self._installer().inspect_game(path);self._prepare_monster_cache(info);return info
        self._run_install_task('inspect',inspect)

    def _prepare_monster_cache(self,info,*,minimum=0,maximum=100,force=False):
        if not info.get('supported') or info.get('errors'):return
        if self._monsters.bundled_complete and not force:
            info['monster_cache']=dict(success=True,bundled=True,reused=True,images=len(self._monsters.images));return
        def progress(n,message):
            self._install_queue.put(('cache_progress',dict(progress=n,message=message,overall=minimum+int((maximum-minimum)*n/100))))
        try:
            info['monster_cache']=build_monster_cache(info['game_dir'],self.settings.parent/'monster-cache',progress,force=force)
        except Exception as error:
            info['monster_cache']=dict(success=False,error=str(error))

    def _apply_monster_cache(self,result):
        if not result:return
        if result.get('bundled'):
            self._monsters.reload()
            self._monster_cache_state.update(busy=False,ready=bool(self._monsters.images),progress=100,error='',reused=True,message='怪物图鉴随包预览已就绪，无需等待生成')
            self.monsterCatalogChanged.emit();return
        success=result.get('success') and self._monsters.reload(result['path'])
        if success:
            self._monsters.save()
            self._monster_cache_state.update(busy=False,ready=True,progress=100,error='',reused=bool(result.get('reused')),message='怪物图鉴已就绪 · '+str(result.get('images',len(self._monsters.images)))+' 张本地预览')
        else:
            message=result.get('error') or self._monsters.error or '缓存载入失败'
            self._monsters.reload()
            self._monster_cache_state.update(busy=False,ready=bool(self._monsters.images),error=message,message='预览更新失败，保留已有图鉴；可稍后重试')
        self.monsterCatalogChanged.emit()

    def _apply_game_inspection(self,info):
        path=str(info.get('game_dir') or '')
        if path!=self._install_state.get('selectedPath'):self._install_state.update(needsRestart=False,pluginOnline=False,interfaceMessage='',interfaceError=False)
        errors=info.get('errors') or [];warnings=info.get('warnings') or []
        payload=self._installer().payload_info()
        valid=bool(info.get('supported') and info.get('detected') and not errors)
        self._install_state.update(selectedPath=path,valid=valid,gameRunning=bool(info.get('running')),installedVersion=info.get('plugin_version',''),gameVersion='1.3.1' if valid and info.get('compatibility_mode')!='runtime-interface' else '',
            buildProfile=info.get('build_profile',''),buildLabel=info.get('build_label',''),
            compatibilityMode=info.get('compatibility_mode',''),
            payloadReady=bool(payload.get('available')),error='；'.join(str(x) for x in errors),
            message='请先退出这个目录里的游戏，再安装。' if info.get('running') else '；'.join(str(x) for x in warnings) or ('目录检查通过，可以安装或修复。' if valid else '没有找到支持的 SiNiSistar2 1.3.1 游戏目录。'))
        if valid and Path(path)!=self._game_directory:
            self._save_importer=None
            self._armed=False;self._ovc_armed=False;self._reset_output()
            if self._observer:self._observer.stop()
            self._game_directory=Path(path);self._live={};self._last={};self._identity=None;self._dialogue_until=0.
            if not self.offline:self._observer=PluginObserver(self._telemetry_directory());self._observer.start()
            self.save();self._emit_changed()
        self._apply_monster_cache(info.get('monster_cache'))

    @Slot()
    def installGamePlugin(self):
        self._begin_game_install(False)

    @Slot()
    def installAndLaunchGame(self):
        if self.offline:self.toast.emit('离线预览不安装或启动游戏');return
        self._begin_game_install(True)

    def _begin_game_install(self,launch):
        if self._install_state['busy'] or not self._install_state['selectedPath']:return
        self._armed=False;self._ovc_armed=False;self._reset_output();self._emit_changed()
        path=self._install_state['selectedPath']
        self._launch_after_install=path if launch else None
        def install():
            result=self._installer().install(path,progress=lambda percent,message:self._install_queue.put(('progress',dict(progress=int(percent*.75),message=message))))
            info=dict(game_dir=result['game_dir'],supported=True,errors=[])
            self._prepare_monster_cache(info,minimum=75,maximum=100)
            result['monster_cache']=info.get('monster_cache');return result
        self._run_install_task('install',install)

    def _launch_installed_game(self,info):
        """Launch the same verified selection, keeping device output paused."""
        self._armed=False;self._ovc_armed=False;self._reset_output()
        if info.get('running'):
            self._install_state.update(gameRunning=True,message='游戏已运行，等待观察插件上线。');return
        root=Path(info.get('game_dir') or '').resolve();executable=Path(info.get('executable') or '').resolve()
        if not info.get('supported') or info.get('errors') or root!=self._game_directory.resolve() or executable.parent!=root or executable.name!='SiNiSistar2.exe' or not executable.is_file():
            raise RuntimeError('游戏路径未通过启动检查，请重新选择目录。')
        ok,pid=QProcess.startDetached(str(executable),[],str(root))
        if not ok:raise RuntimeError('游戏未能启动，请检查可执行文件或系统提示。')
        self._install_state.update(gameRunning=True,message='游戏已启动，等待观察插件上线；首次生成运行文件可能需要等待。',launchedPid=pid)
        self.log('game_launch','已启动所选游戏 · '+str(executable),'系统')

    def _probe_game_process(self):
        if self.offline or not self._install_state.get('valid') or self._install_state['busy']:return
        now=time.monotonic()
        if now-self._game_probe_at<2 or (self._game_probe_thread and self._game_probe_thread.is_alive()):return
        path=self._install_state.get('selectedPath')
        if not path or not (Path(path)/'SiNiSistar2.exe').is_file():return
        self._game_probe_at=now
        def probe():
            try:
                from .install_manager import game_is_running
                self._install_queue.put(('running',dict(path=path,running=game_is_running(Path(path)/'SiNiSistar2.exe'))))
            except Exception:pass
        self._game_probe_thread=threading.Thread(target=probe,name='SiNiSistarGameProcessProbe',daemon=True);self._game_probe_thread.start()

    def _poll_installer(self):
        dirty=False
        for _ in range(100):
            try:phase,data=self._install_queue.get_nowait()
            except queue.Empty:break
            dirty=True
            if phase=='running':
                if data['path']==self._install_state.get('selectedPath'):self._install_state['gameRunning']=data['running']
                continue
            if phase=='cache_progress':
                self._monster_cache_state.update(busy=True,progress=data['progress'],message=data['message'],error='')
                self._install_state.update(progress=data['overall'],message=data['message']);continue
            if phase=='progress':self._install_state.update(progress=data['progress'],message=data['message']);continue
            self._install_state.update(busy=False,phase='idle')
            if phase in ('save_import','save_restore'):
                self._save_state.update(busy=False)
                self._save_state.update({k:v for k,v in data.items() if k!='ok'})
                self._install_state.update(message='存档操作完成。' if data['ok'] else '存档操作未完成。')
                self.saveImportChanged.emit();continue
            if phase=='error':self._launch_after_install=None;self._monster_cache_state['busy']=False;self._install_state.update(error=data['error'],message='操作未完成，请检查目录或提示后重试。');continue
            if phase=='scan':
                self._game_candidates=[dict(x,path=x.get('game_dir',''),name=Path(x.get('game_dir') or 'SiNiSistar2').parent.name,supported=bool(x.get('supported')),installed=bool(x.get('plugin_version'))) for x in data]
                chosen=next((x for x in data if Path(x.get('game_dir') or '')==self._game_directory),None) or next((x for x in data if x.get('supported')),None)
                if chosen:self._apply_game_inspection(chosen)
                else:self._install_state.update(message='附近未找到游戏，请手动选择解压后的目录。',payloadReady=bool(self._installer().payload_info().get('available')))
            elif phase=='inspect':self._apply_game_inspection(data)
            elif phase=='preview':self._apply_monster_cache(data.get('monster_cache'))
            elif phase=='install':
                info=self._installer().inspect_game(data['game_dir']);info['monster_cache']=data.get('monster_cache');self._apply_game_inspection(info)
                self._install_state.update(progress=100,needsRestart=True,message='安装完成。请启动游戏；首次生成运行文件可能需要等待，插件在线后才算加载成功。',error='')
                self.log('install','BepInEx 与观察插件安装完成 · '+data['game_dir'],'系统')
                launch=self._launch_after_install;self._launch_after_install=None
                if launch==data['game_dir']:
                    try:self._launch_installed_game(info)
                    except Exception as error:self._install_state.update(error=str(error),message='插件已安装，游戏尚未启动。')
        if dirty:self.installChanged.emit()
    @Property('QVariantList',notify=flowsChanged)
    def observedFlows(self):return self._flows.rows()
    @Property('QVariantList',notify=flowsChanged)
    def semanticFlows(self):
        if self._semantic_flows_cache is None:
            self._semantic_flows_cache=self._flow_review.rows(self._flows.rows(),self._static_flows,self._flow_scenes)
        return deepcopy(self._semantic_flows_cache)

    @Property('QVariantList',notify=monsterCatalogChanged)
    def monsterCatalog(self):return self._monsters.rows()
    @Property('QVariantMap',notify=monsterCatalogChanged)
    def monsterCatalogSummary(self):return self._monsters.summary()
    @Property('QVariantMap',notify=installChanged)
    def monsterCacheState(self):return dict(self._monster_cache_state)
    @Property(str,notify=changed)
    def currentMonster(self):
        s=self._live
        if not s.get('live') or not s.get('valid') or not s.get('bound') or time.monotonic()-s.get('sampled_at',0)>=.6:return ''
        return self._monsters.match(s.get('binder_class') or s.get('binder'))

    @Slot(str)
    def toggleMonsterFavorite(self,key):
        self._monsters.toggle_favorite(key);self.monsterCatalogChanged.emit()

    @Slot()
    def reloadMonsterPreviews(self):
        self._monsters.reload();self.monsterCatalogChanged.emit()
        self.toast.emit('本地预览已刷新 · '+str(len(self._monsters.images))+' 张')

    @Slot()
    def generateMonsterPreviews(self):
        def generate():
            info=self._installer().inspect_game(self._game_directory)
            self._prepare_monster_cache(info,force=True)
            if not info.get('monster_cache'):info['monster_cache']=dict(success=False,error='请先选择受支持的游戏目录')
            return info
        self._run_install_task('preview',generate)

    @Slot(str)
    def importMonsterPreviews(self,url):
        path=QUrl(url).toLocalFile() if url.startswith('file:') else url
        if self._monsters.reload(path):
            self._monsters.save();self.toast.emit('已载入本地预览缓存 · '+str(len(self._monsters.images))+' 张')
        else:self.toast.emit(self._monsters.error)
        self.monsterCatalogChanged.emit()

    @Slot('QVariantList',str)
    def reviewFlows(self,keys,decision):
        # Review intentions are deliberately separate from strategy and arm state.
        count=self._flow_review.choose([k for k in keys if isinstance(k,str)],decision,[r['key'] for r in self.semanticFlows])
        if count:self._notify_flows();self.toast.emit('已保存 '+str(count)+' 项联动意向；当前输出策略未改变')

    @Slot()
    def exportFlowReview(self):
        target=self._flow_review.export(self.semanticFlows,self.settings.parent/'flow-review/流程语义与联动意向.csv')
        self.toast.emit('清单已导出：'+str(target))
    @Property('QVariantMap',notify=hudChanged)
    def hudSettings(self):return deepcopy(self._hud_settings)
    @Property(bool,notify=hudChanged)
    def hudAdjusting(self):return self._hud_adjusting
    @Property(bool,notify=hudChanged)
    def hudHotkeyRegistered(self):return self._hud_hotkey_registered
    @Property(bool,notify=hudChanged)
    def emergencyHotkeyRegistered(self):return self._emergency_hotkey_registered

    @Slot(str,'QVariant')
    def setHudSetting(self,key,value):
        if key not in HUD_DEFAULTS:return
        self._hud_settings=sanitize_hud(dict(self._hud_settings,**{key:value}))
        if key=='enabled':
            self._hud=self._hud_settings['enabled']
            if not self._hud:self._hud_adjusting=False
            self._emit_changed()
        self.save();self.hudChanged.emit()

    @Slot(bool)
    def setHudAdjusting(self,enabled):
        self._hud_adjusting=enabled
        if enabled:self.setHudSetting('enabled',True)
        self.hudChanged.emit()

    @Slot()
    def toggleHudAdjusting(self):self.setHudAdjusting(not self._hud_adjusting)

    @Slot()
    def openHudSettings(self):self.setHudAdjusting(True);self.hudSettingsRequested.emit()

    @Slot()
    def resetHudSettings(self):self._hud_settings=dict(HUD_DEFAULTS);self._hud=True;self.save();self.hudChanged.emit();self._emit_changed()

    @Slot(float,float,float,float,float,float,float,float)
    def saveHudPosition(self,x,y,origin_x,origin_y,client_width,client_height,width,height):
        horizontal=100*(x-origin_x)/max(1,client_width-width);vertical=100*(y-origin_y)/max(1,client_height-height)
        self._hud_settings=sanitize_hud(dict(self._hud_settings,anchor='custom',x=horizontal,y=vertical));self.save();self.hudChanged.emit()

    @Slot(str,float,float,float,float,float,float,float,float)
    def saveHudPanelPosition(self,route,x,y,origin_x,origin_y,client_width,client_height,width,height):
        prefix='ovc_' if route in ('ovc','vibration') else ''
        horizontal=100*(x-origin_x)/max(1,client_width-width);vertical=100*(y-origin_y)/max(1,client_height-height)
        self._hud_settings=sanitize_hud(dict(self._hud_settings,**{prefix+'anchor':'custom',prefix+'x':horizontal,prefix+'y':vertical}));self.save();self.hudChanged.emit()

    @Slot()
    def openEventDetector(self):self.detectorRequested.emit()

    @Property('QVariantMap',constant=True)
    def detectorScreen(self):
        screens=QGuiApplication.screens();screen=screens[1] if len(screens)>1 else QGuiApplication.primaryScreen()
        rect=screen.availableGeometry() if screen else None
        return dict(x=rect.x()+40 if rect else 80,y=rect.y()+40 if rect else 80,width=min(1000,rect.width()-80) if rect else 1000,height=min(850,rect.height()-80) if rect else 800)

    def _simulation_changed(self):
        self._cancel_auto('pulse');self._cancel_auto('ovc')
        was_armed=self._armed or self._ovc_armed;self._armed=False;self._ovc_armed=False;self._reset_output()
        if was_armed:self.toast.emit('策略已修改，输出已暂停；检查后可重新启动')
        self._simulator.reset();self.save();self._cg_batch.profile(self._batch_profile());self.configChanged.emit();self._emit_changed()

    @Slot(str,str,float)
    def setQuickPresetValue(self,name,key,value):
        from .quick_policy import sanitize_presets
        if name not in self._sim_profile['quick_presets'] or key not in self._sim_profile['quick_presets'][name]:return
        raw=deepcopy(self._sim_profile['quick_presets']);raw[name][key]=value
        self._sim_profile['quick_presets']=sanitize_presets(raw);self.save();self.configChanged.emit()

    @Slot(str,'QVariant')
    def editQuickValue(self,key,value):
        from .quick_policy import current_values,edit_current
        if key not in current_values(self._sim_profile):return
        self._sim_profile=edit_current(self._sim_profile,{key:value})
        if key in ('pulse_cap','ovc_cap'):self._sync_quick_limits('pulse' if key=='pulse_cap' else 'vibration')
        self._simulation_changed()

    @Slot(str,float,float)
    def editQuickRange(self,key,low,high):
        from .quick_policy import edit_current
        if key in ('pulse_grab','ovc_grab'):pairs=[(key+'_start',key)]
        elif key in ('pulse_death','ovc_death'):pairs=[(key+'_start_'+c,key+'_'+c) for c in 'ab']
        elif key in ('pulse_death_a','pulse_death_b','ovc_death_a','ovc_death_b'):
            prefix,channel=key.rsplit('_',1);pairs=[(prefix+'_start_'+channel,key)]
        else:return
        low=self._clamp(low,0,200 if key.startswith('ovc_') else 100);high=self._clamp(high,low,200 if key.startswith('ovc_') else 100)
        changes={}
        for first,last in pairs:changes[first]=low;changes[last]=high
        self._sim_profile=edit_current(self._sim_profile,changes);self._simulation_changed()

    def _sync_quick_limits(self,route):
        if route=='pulse':
            for channel in self._channels:channel['limit']=int(self._sim_profile['pulse_cap_'+channel['key'].lower()])
        else:self._ovc_limits={c:int(self._sim_profile['vibration_cap_'+c.lower()]) for c in 'AB'}

    @Slot(str,str,str)
    def setChannelFeedback(self,route,channel,mode):
        from .channel_policy import MODES
        if route not in ('pulse','vibration') or channel not in ('A','B') or mode not in MODES:return
        self._sim_profile['channel_feedback'][route][channel]=mode
        self._sim_profile['quick_active_preset']='';self._simulation_changed()

    @Slot(str,str,float)
    def setQuickDeathStrength(self,name,route,value):
        from .quick_policy import sanitize_presets
        if name not in self._sim_profile['quick_presets'] or route not in ('pulse','ovc'):return
        raw=deepcopy(self._sim_profile['quick_presets'])
        for channel in 'ab':raw[name][route+'_death_'+channel]=value
        self._sim_profile['quick_presets']=sanitize_presets(raw);self.save();self.configChanged.emit()

    @Slot(str,str)
    def setQuickDeathMode(self,name,mode):
        if name not in self._sim_profile['quick_presets'] or mode not in ('until_end','timed'):return
        self._sim_profile['quick_presets'][name]['death_mode']=mode
        self.save();self.configChanged.emit()

    @Slot(str,str,float,float)
    def setQuickRange(self,name,key,low,high):
        from .quick_policy import sanitize_presets
        if name not in self._sim_profile['quick_presets']:return
        raw=deepcopy(self._sim_profile['quick_presets']);draft=raw[name]
        if key in ('pulse_grab','ovc_grab'):pairs=[(key+'_start',key)]
        elif key in ('pulse_death','ovc_death'):pairs=[(key+'_start_'+c,key+'_'+c) for c in 'ab']
        elif key in ('pulse_death_a','pulse_death_b','ovc_death_a','ovc_death_b'):
            prefix,channel=key.rsplit('_',1);pairs=[(prefix+'_start_'+channel,key)]
        else:return
        low=self._clamp(low,0,200 if key.startswith('ovc_') else 100);high=self._clamp(high,low,200 if key.startswith('ovc_') else 100)
        for first,last in pairs:draft[first]=low;draft[last]=high
        self._sim_profile['quick_presets']=sanitize_presets(raw);self.save();self.configChanged.emit()

    @Slot(int,str,str,float,float)
    def setRuleStrengthRange(self,index,route,channel,low,high):
        rows=list(self._sim_profile['rules'].values())
        if not 0<=index<len(rows) or route not in ('pulse','vibration') or channel not in ('','a','b'):return
        rule=rows[index]
        if rule['key'] not in ('grab_hold','defeat_hold'):return
        maximum=200 if route=='vibration' else 100;step=10 if route=='vibration' else 1
        low=int(self._clamp(low,0,maximum)//step*step);high=int(self._clamp(high,low,maximum)//step*step)
        suffix='_'+channel if channel and rule['key']=='defeat_hold' else ''
        rule[route+'_start_strength'+suffix]=low;rule[route+'_strength'+suffix]=high
        self._sim_profile['quick_active_preset']='';self._simulation_changed()

    @Slot(str,bool)
    def applyQuickPreset(self,name,death_only=False):
        from .quick_policy import apply_preset,PRESET_NAMES
        if name not in PRESET_NAMES:return
        self._sim_profile=apply_preset(self._sim_profile,name,death_only=death_only)
        if not death_only:
            for channel in self._channels:channel['limit']=int(self._sim_profile['pulse_cap_'+channel['key'].lower()])
            self._ovc_limits={c:int(self._sim_profile['vibration_cap_'+c.lower()]) for c in 'AB'}
        self._simulation_changed()
        self.toast.emit(('死亡惩罚强度' if death_only else '强度预设')+'已应用：'+PRESET_NAMES[name]+' · 输出保持暂停')

    @Slot(str)
    def resetQuickPreset(self,name):
        from .quick_policy import default_presets
        if name not in self._sim_profile['quick_presets']:return
        self._sim_profile['quick_presets'][name]=default_presets()[name];self.save();self.configChanged.emit()

    @Slot(str,str,bool)
    def setDeathChannel(self,route,channel,enabled):
        if route not in ('pulse','vibration') or channel not in ('A','B'):return
        rule=self._sim_profile['rules']['defeat_hold'];channels=set(rule[route+'_channel']) if rule[route+'_enabled'] else set()
        if enabled:channels.add(channel)
        else:channels.discard(channel)
        rule[route+'_enabled']=bool(channels)
        if channels:rule[route+'_channel']=''.join(c for c in 'AB' if c in channels)
        self._sim_profile['quick_active_preset']='';self._simulation_changed()

    @Slot(str,'QVariant')
    def setSimulationSetting(self,key,value):
        if key not in self.simulationSettings:return
        if key in ('quick_presets','quick_active_preset'):return
        if key in ('pulse_abnormal_base','pulse_stack_bonus','vibration_stack_bonus'):
            self.toast.emit('异常固定每种 Pulse 10，负鼠 0；不同种类按通道相加');return
        raw=deepcopy(self._sim_profile);raw[key]=value;raw['quick_active_preset']=''
        if key=='pulse_abnormal_base':
            for rule in raw['abnormals'].values():rule['pulse_strength']=self._clamp(value,0,100)
        self._sim_profile=sanitize_profile(raw);self._simulation_changed()

    @Property('QVariantList',constant=True)
    def captureCandidates(self):
        rows=self._static_flows
        return [dict(row,key='static:'+row['enemy'],name=row['enemy']+' · 静态候选',scene='v1.3.1 定义，未实机确认',kind='static_candidate',
                     labels=['状态 '+x['name'] for x in row['states']]+['动画 '+x['name'] for x in row['animations']]+
                            ['动画字段 '+x for x in row['animation_fields']]+['任务 '+x for x in row['tasks']]) for row in rows]

    @Slot(str,int,str,'QVariant')
    def setSimulationRule(self,group,index,field,value):
        if group not in ('rules','abnormals','flows'):return
        rows=self._sim_profile[group];keys=list(rows) if isinstance(rows,dict) else None
        if not 0<=index<len(rows):return
        r=rows[keys[index]] if keys is not None else rows[index]
        if group=='abnormals' and positive_status(r['key']) and field in ('enabled','pulse_enabled','vibration_enabled'):
            self.toast.emit('正面 Buff 不参与联动和种类叠加');return
        if field not in r or field in ('key','name'):return
        if group=='abnormals' and field in ('pulse_strength','pulse_level_step','pulse_gain','vibration_strength','vibration_level_step','vibration_gain','vibration_enabled'):
            self.toast.emit('异常固定每种 Pulse 10，负鼠 0，不受等级影响');return
        updated=dict(r);updated[field]=value
        clean=sanitize_rule(updated,r)
        if field=='pulse_wave':
            preset=next((w for w in self._waves if w['key']==clean['pulse_wave'] and w.get('frames')),None)
            if preset:clean['pulse_period']=preset['native_period']
        if keys is None:rows[index]=clean
        else:rows[keys[index]]=clean
        self._sim_profile['quick_active_preset']=''
        self._simulation_changed()

    @Slot()
    def toggleSimulation(self):
        if self._emergency:self.toast.emit('请先解除急停锁定');return
        if not self._sim_running:
            self.stopConnection();self._armed=False
        self._sim_running=not self._sim_running;self._simulator.reset();self._emit_changed()

    @Slot(str)
    def simulationSource(self,source):
        if source not in ('live','grab_hp','abnormals','flow'):return
        self._sim_source=source;self._demo_start=time.monotonic();self._simulator.reset();self._emit_changed()

    @Slot(int)
    def addFlowRule(self,index):
        rows=self.observedFlows
        if not 0<=index<len(rows):return
        flow=rows[index]
        if flow.get('kind')=='capture_penalty':self.toast.emit('怪物内部受制流程暂用零血持续规则，尚无精确动画身份');return
        # Multiple rules for one identity may select different labels/time windows.
        self._sim_profile['flows'].append(base_rule(flow['key'],flow['name'],priority=60));self._simulation_changed()
        self.toast.emit('已添加演出模拟规则，可设置阶段标签与时间窗口')

    @Slot(int)
    def removeFlowRule(self,index):
        if 0<=index<len(self._sim_profile['flows']):self._sim_profile['flows'].pop(index);self._simulation_changed()

    @Slot()
    def toggleArm(self):
        self._cancel_auto('pulse')
        if self._armed:
            self._armed=False;self._reset_output(ovc=False);self.log('armed','已暂停 Pulse 输出','系统');self._emit_changed()
        else:self._enable_device('pulse')

    def _device_setup(self,role,snapshot=None):
        service=self._service if role=='pulse' else self._ovc_service
        s=snapshot if snapshot is not None else service.snapshot() if service else {}
        device=next((d for d in self.v4Devices if d.get('clientId')==s.get('selected_client_id') and d.get('slotId')==s.get('selected_slot_id')), {}) if s.get('protocol')=='v4' else {}
        caps={c:min(self._sim_profile[('pulse' if role=='pulse' else 'vibration')+'_cap_'+c.lower()],
                    next(x['limit'] for x in self._channels if x['key']==c) if role=='pulse' else self._ovc_limits[c]) for c in 'AB'}
        result=setup_status(role,s,enabled=self._pulse_channels if role=='pulse' else self._ovc_channels,caps=caps,device=device,
                            emergency=self._emergency,pending=bool(self._trainer.pending),simulating=self._sim_running,live_source=self._sim_source=='live')
        result['autoPending']=role in self._auto_pending
        return result

    def _enable_device(self,role,*,automatic=False):
        status=self._device_setup(role)
        if not status['canEnable']:
            if not automatic:self.toast.emit(status['reason'])
            return False
        if not automatic:self._auto_suppressed.discard(role)
        if role=='pulse':self._armed=True;self._reset_output(ovc=False)
        else:self._ovc_armed=True;self._ovc_planner.reset();self._ovc_warm=0;self._ovc_stamp=None
        self.log('armed',('自动启用' if automatic else '已启用')+('郊狼 Pulse' if role=='pulse' else '负鼠')+' · 可用通道 '+status['usableChannels'],'系统')
        self._emit_changed();return True

    @Slot(str)
    def explainOutputUnavailable(self,role):
        if role in ('pulse','ovc'):
            status=self._device_setup(role);self.toast.emit(status['reason'] or '设备已就绪，可启用输出。')

    @Slot(str)
    def retryDevice(self,role):
        if role not in ('pulse','ovc'):return
        status=self._device_setup(role)
        service=self._service if role=='pulse' else self._ovc_service
        s=service.snapshot() if service else {}
        if s.get('protocol')!='v4':self.explainOutputUnavailable(role);return
        client,slot=self._requested_devices.get(role,(s.get('selected_client_id',''),s.get('selected_slot_id','')))
        if not client or not slot:self.explainOutputUnavailable(role);return
        if self._select_v4_device(role,client,slot,automatic=True):
            self._auto_suppressed.discard(role)
            self._auto_pending[role]=(id(self._v4),client,slot)
            self.toast.emit('正在重新同步并确认归零；就绪后将启用对应设备。')

    def _cancel_auto(self,role):
        self._auto_pending.pop(role,None)
        self._auto_suppressed.add(role)
        if self._v4:
            kind='COYOTE_030' if role=='pulse' else 'OVC_1'
            self._auto_present.update((id(self._v4),d['clientId'],d['slotId']) for d in self.v4Devices if d.get('type')==kind)
        if role=='pulse' and self._service:
            self._auto_v3_pending=None
            s=self._service.snapshot();self._auto_v3=(id(self._service),s.get('controller_id'),s.get('target_id'))

    def _sync_auto_devices(self):
        if self.offline or not self._connection['auto_enable']:return
        devices=self.v4Devices;present={(id(self._v4),d['clientId'],d['slotId']) for d in devices
            if not d.get('_connectionUnconfirmed') and (d.get('slotState') or {}).get('hasDevice') is not False
            and (d.get('props') or {}).get('connectState')!='disconnected'
            and ((d.get('slotState') or {}).get('hasDevice') is True or (d.get('props') or {}).get('connectState')=='connected')}
        added=present-self._auto_present;self._auto_present=present
        blocked=self._emergency or self._trainer.pending or self._sim_running or self._sim_source!='live'
        for role,kind in (('pulse','COYOTE_030'),('ovc','OVC_1')):
            if role=='pulse' and self._connection['pulse_backend']!='v4':continue
            service=self._service if role=='pulse' else self._ovc_service
            if not service:continue
            s=service.snapshot();selected=(s.get('selected_client_id'),s.get('selected_slot_id'))
            candidates=[d for d in devices if d.get('type')==kind and (id(self._v4),d['clientId'],d['slotId']) in added]
            armed=self._armed if role=='pulse' else self._ovc_armed
            if candidates and not blocked and role not in self._auto_suppressed and (not armed or not s.get('connected')):
                # Retain an existing selection; a second device must not steal it.
                item=next((d for d in candidates if (d['clientId'],d['slotId'])==selected),None) if all(selected) else candidates[0]
                if armed:
                    # A reconnect may allocate a new slot on the same APP.
                    previous=self._requested_devices.get(role,selected)
                    item=next((d for d in candidates if d['clientId']==previous[0]),None)
                if item and self._select_v4_device(role,item['clientId'],item['slotId'],automatic=True):
                    self._auto_pending[role]=(id(self._v4),item['clientId'],item['slotId'])
            pending=self._auto_pending.get(role)
            if not pending:continue
            s=service.snapshot()
            if s.get('selection_pending') and not blocked:continue
            if blocked or pending not in present or s.get('error') or s.get('readiness_failed'):
                self._auto_pending.pop(role,None);continue
            if (s.get('selected_client_id'),s.get('selected_slot_id'))==pending[1:] and self._enable_device(role,automatic=True):self._auto_pending.pop(role,None)
        if self._connection['pulse_backend'] in ('v3','mock') and self._service:
            s=self._service.snapshot();identity=(id(self._service),s.get('controller_id'),s.get('target_id'))
            if s.get('connected') and s.get('feedback_known') and identity!=self._auto_v3:
                self._auto_v3=identity;self._auto_v3_pending=identity
            if self._auto_v3_pending:
                if blocked or not s.get('connected') or s.get('error'):self._auto_v3_pending=None
                elif self._enable_device('pulse',automatic=True):self._auto_v3_pending=None

    def _reset_output(self,*,ovc=True):
        if self._output_worker:self._output_worker.invalidate(ovc=ovc)
        self._detector.reset();self._warm=0;self._stamp=None
        self._pulse_planner.reset();self._pulse_plan=self._pulse_planner.engine.blank('Pulse 已暂停 / 状态变化')
        if self._service:self._service.set_output_permission(False,'配置或运行状态变化')
        if ovc:
            self._ovc_warm=0;self._ovc_stamp=None;self._ovc_planner.reset();self._ovc_plan=self._ovc_planner.engine.blank('负鼠已暂停 / 状态变化')
            if self._ovc_service:self._ovc_service.set_output_permission(False,'配置或运行状态变化')

    @Slot()
    def emergencyStop(self):
        if not self._emergency:
            self._emergency_resume={role:self._resume_identity(service) for role,service,armed in
                (('pulse',self._service,self._armed),('ovc',self._ovc_service,self._ovc_armed)) if armed and service}
        if self._output_worker:self._output_worker.panic()
        self._cancel_auto('pulse');self._cancel_auto('ovc')
        self._sim_running=False;self._simulator.reset();self._sim_plan=self._simulator.blank('急停已锁定')
        self._emergency=True;self._armed=False;self._ovc_armed=False;self._reset_output()
        for service in (self._service,self._ovc_service):
            if service:
                (service.latch_emergency_stop if hasattr(service,'latch_emergency_stop') else service.emergency_zero)()
        self.log('emergency','紧急归零并锁定输出','系统');self._emit_changed()

    @Slot()
    def unlock(self):
        self._emergency=False;self._armed=False;self._ovc_armed=False;self._reset_output()
        if self._output_worker:self._output_worker.unlock()
        for service in (self._service,self._ovc_service):
            if service and hasattr(service,'clear_emergency_stop'):service.clear_emergency_stop()
        self.toast.emit('已解除锁定，输出仍保持暂停');self._emit_changed()

    @staticmethod
    def _resume_identity(service):
        s=service.snapshot()
        return (id(service),s.get('controller_id'),s.get('target_id'),s.get('selected_client_id'),s.get('selected_slot_id'))

    @Slot()
    def resumeAfterEmergency(self):
        if not self._emergency:return
        targets=dict(self._emergency_resume);self.unlock();restored=[]
        for role,service in (('pulse',self._service),('ovc',self._ovc_service)):
            if role in targets and service and self._resume_identity(service)==targets[role] and self._enable_device(role):restored.append(role)
        self._emergency_resume={}
        self.toast.emit('已恢复急停前启用的通道' if restored else '已解除急停；请在设备就绪后启用输出');self._emit_changed()

    @Slot(int,str,'QVariant')
    def setRule(self,index,field,value):
        if not 0<=index<len(self._rules):return
        r=self._rules[index]
        if field=='enabled':r[field]=bool(value)
        elif field=='channel':r[field]='B' if str(value)=='B' else 'A'
        elif field=='strength':r[field]=int(self._clamp(value,0,100))
        elif field=='duration':r[field]=round(self._clamp(value,.1,5),1)
        elif field=='wave' and str(value) in [w['key'] for w in self._waves]:r[field]=str(value)
        else:return
        self._reset_output(ovc=False);self.save();self.configChanged.emit();self._emit_changed()

    @Slot(int,str,float)
    def setChannel(self,index,field,value):
        if index not in (0,1) or field not in ('limit','frequency'):return
        self._channels[index][field]=int(self._clamp(value,0 if field=='limit' else 1,100));self._reset_output();self.save();self.configChanged.emit();self._emit_changed()

    @Slot(str)
    def selectWave(self,key):
        catalog=self.vibrationWaves if self._editing_route=='vibration' else self._waves
        wave=next((w for w in catalog if w['key']==key),None)
        if wave:
            from .simulation import envelope
            self._selected=key;self._points=list(wave['points']) if len(wave['points'])==16 else [envelope(wave['points'],i/16) for i in range(16)];self.configChanged.emit()

    @Slot(str)
    def editWaveRoute(self,route):
        if route not in ('pulse','vibration'):return
        self._editing_route=route;self.selectWave(self.vibrationWaves[0]['key'] if route=='vibration' else self._waves[0]['key'])

    @Slot(int,float)
    def editPoint(self,index,value):
        if 0<=index<16:self._points[index]=self._clamp(value,0,1);self.configChanged.emit()

    @Slot(float,float,float,float)
    def editWaveStroke(self,x0,y0,x1,y1):
        from .waveform_edit import apply_stroke
        try:self._points=apply_stroke(self._points,x0,y0,x1,y1)
        except ValueError:return
        self.configChanged.emit()

    @Slot('QVariantList')
    def setWavePoints(self,points):
        from .waveform_edit import sanitize_points
        try:self._points=sanitize_points(points)
        except (ValueError,TypeError):return
        self.configChanged.emit()

    @Slot(str,bool)
    def addCustomWave(self,name,blank=False):
        catalog=self._vibration_custom if self._editing_route=='vibration' else self._waves
        if sum(w['key'].startswith(('custom_','vib_custom_')) for w in catalog)>=20:self.toast.emit('自定义波形最多保存 20 个');return
        if blank:self._points=[0.]*16
        self.saveWave(name)

    @Slot()
    def updateCustomWave(self):
        catalog=self._vibration_custom if self._editing_route=='vibration' else self._waves
        wave=next((w for w in catalog if w['key']==self._selected and w['key'].startswith(('custom_','vib_custom_'))),None)
        if not wave:self.toast.emit('预设保留不变，请另存为自定义波形');return
        wave['points']=list(self._points);self._simulation_changed();self.toast.emit('自定义波形已更新，输出已暂停')

    @Slot(str)
    def renameCustomWave(self,name):
        if not name.strip():return
        catalog=self._vibration_custom if self._editing_route=='vibration' else self._waves
        wave=next((w for w in catalog if w['key']==self._selected and w['key'].startswith(('custom_','vib_custom_'))),None)
        if wave:wave['name']=name.strip()[:32];self.save();self.configChanged.emit()

    @Slot()
    def deleteCustomWave(self):
        vibration=self._editing_route=='vibration';catalog=self._vibration_custom if vibration else self._waves
        wave=next((w for w in catalog if w['key']==self._selected and w['key'].startswith(('custom_','vib_custom_'))),None)
        if not wave:return
        key=wave['key'];catalog.remove(wave);route='vibration' if vibration else 'pulse';fallback='ovc_surf_wave' if vibration else 'breath'
        for group in ('rules','abnormals','flows'):
            rows=self._sim_profile[group];rows=rows.values() if isinstance(rows,dict) else rows
            for rule in rows:
                if rule[route+'_wave']==key:rule[route+'_wave']=fallback;rule[route+'_enabled']=False
        for scope in ('cg','gallery'):
            cg=self._sim_profile.get(scope) or {}
            if scope=='cg' and cg.get('inherit_death',True):continue
            cg=(sanitize_gallery if scope=='gallery' else sanitize_cg)(cg,self._sim_profile['rules']['defeat_hold'],sanitize_rule);self._sim_profile[scope]=cg
            for channel,options in cg['routes'][route].items():
                if options['wave']==key or any(x['wave']==key for x in options['queue']):
                    cg['rule'][route+'_channel']=cg['rule'][route+'_channel'].replace(channel,'')
                    options['wave']=fallback;options['queue']=[x for x in options['queue'] if x['wave']!=key]
            if not cg['rule'][route+'_channel']:cg['rule'][route+'_enabled']=False;cg['rule'][route+'_channel']='A'
        self.selectWave(fallback);self._simulation_changed();self.toast.emit('波形已删除，引用它的反馈已关闭')

    @Slot(str)
    def saveWave(self,name):
        catalog=self._vibration_custom if self._editing_route=='vibration' else self._waves
        if sum(w['key'].startswith(('custom_','vib_custom_')) for w in catalog)>=20:self.toast.emit('自定义波形最多保存 20 个');return
        vibration=self._editing_route=='vibration';key=('vib_custom_' if vibration else 'custom_')+str(time.time_ns())
        (self._vibration_custom if vibration else self._waves).append({'key':key,'name':name.strip()[:32] or ('自定义负鼠波形' if vibration else '自定义波形'),'points':list(self._points)})
        self._selected=key;self.save();self.configChanged.emit();self._emit_changed();self.toast.emit('波形已保存，可在对应模拟策略中选用')

    @Slot()
    def startConnection(self):
        if self._sim_running:self.toast.emit('模拟期间不启动设备服务');return
        if self.offline:self.toast.emit('离线预览不打开设备服务');return
        if self._connection['pulse_backend']=='v4':
            self.startV4();self._service=self._v4.channel('pulse') if self._v4 else None;self._emit_changed();return
        if self._service and self._service.snapshot()['server_ready']:return
        from .dglab import ConnectionService
        if self._service:self._service.stop()
        local=self._connection['pulse_backend']=='mock'
        self.refreshNetwork()
        ip='127.0.0.1' if local else self._connection['lan_ip'] or (self._available_ips[0] if self._available_ips else '127.0.0.1')
        try:self._service=ConnectionService(port=0 if local else self._connection['v3_port'],host='127.0.0.1' if local else '0.0.0.0',lan_ip=ip);self._service.start()
        except (ValueError,OSError) as error:self.toast.emit('连接设置无效：'+str(error));return
        self.log('connection','已开启本机模拟 APP 服务' if local else '已开启 V3 扫码连接服务 · 输出暂停','系统')

    @Slot()
    def refreshNetwork(self):
        from .dglab import discover_lan_ips
        self._available_ips=discover_lan_ips();self.configChanged.emit()

    @Slot(str,'QVariant')
    def setConnectionSetting(self,key,value):
        if key=='pulse_backend':self.setPulseBackend(str(value));return
        if key not in self._connection:return
        if key=='auto_enable':
            value=bool(value)
            if not value:self._auto_pending.clear();self._auto_v3_pending=None
        elif key.endswith('_port'):value=int(self._clamp(value,1024,65535))
        elif key=='lan_ip':
            import ipaddress
            try:value=str(ipaddress.IPv4Address(value)) if str(value).strip() else ''
            except ValueError:self.toast.emit('请输入有效的局域网 IPv4 地址');return
        self._connection[key]=value;self.save();self.configChanged.emit()

    @Slot(str)
    def setPulseBackend(self,mode):
        if self._mock_session:self.stopMockBoth()
        if mode not in ('mock','v3','v4') or mode==self._connection['pulse_backend']:return
        self._armed=False
        if self._service:self._service.set_output_permission(False,'切换 Pulse 连接');self._service.stop()
        self._service=None
        if self._mock_app:self._mock_app.stop();self._mock_app=None
        self._connection['pulse_backend']=mode;self._qr='';self._qrurl=''
        if mode=='v4' and self._v4:self._service=self._v4.channel('pulse')
        self._reset_output(ovc=False);self.save();self.configChanged.emit();self._emit_changed()

    @Slot()
    def startV4(self):
        if self.offline:self.toast.emit('离线预览不连接设备');return
        if self._sim_running:self.toast.emit('请先暂停样例模拟');return
        if self._v4 and self._v4.snapshot().get('server_ready'):return
        from .v4 import V4ConnectionService
        self.refreshNetwork();ip=self._connection['lan_ip'] or (self._available_ips[0] if self._available_ips else '127.0.0.1')
        try:self._v4=V4ConnectionService(port=self._connection['v4_port'],host='0.0.0.0',lan_ip=ip);self._v4.start()
        except (ValueError,OSError) as error:self.toast.emit('V4 服务无法启动：'+str(error));return
        self._ovc_service=self._v4.channel('ovc')
        if self._connection['pulse_backend']=='v4':self._service=self._v4.channel('pulse')
        self.log('connection','已开启 DG-LAB 4 服务；扫码后自动选择设备，就绪后自动启用','系统');self._emit_changed()

    @Slot()
    def stopV4(self):
        if self._mock_session:self.stopMockBoth();return
        self._ovc_armed=False
        if self._connection['pulse_backend']=='v4':self._armed=False;self._service=None
        if self._v4:self._v4.stop();self._v4=None
        self._ovc_service=None;self._ovc_planner.reset();self._emit_changed()

    @Slot(str,str,str)
    def selectV4Device(self,role,client_id,slot_id):
        if role not in ('pulse','ovc','vibration'):return
        role='ovc' if role=='vibration' else role
        self._cancel_auto(role)
        self._select_v4_device(role,client_id,slot_id)

    def _select_v4_device(self,role,client_id,slot_id,*,automatic=False):
        if not self._v4:return False
        if role in ('ovc','vibration'):
            self._ovc_armed=False;self._ovc_warm=0;self._ovc_stamp=None;self._ovc_planner.reset()
            if self._ovc_service:self._ovc_service.set_output_permission(False,'切换负鼠设备')
        else:self._armed=False;self._reset_output(ovc=False)
        accepted=self._v4.select_device(role,client_id,slot_id)
        if accepted:self._requested_devices[role]=(client_id,slot_id)
        elif not automatic:self.toast.emit('设备类型不匹配，或该槽位已离线。请在 DG-LAB APP 中连接对应设备。')
        self._emit_changed();return accepted

    @Slot()
    def copyV4Connection(self):
        if self._v4:QGuiApplication.clipboard().setText(self._v4.snapshot().get('qr_url',''));self.toast.emit('V4 连接地址已复制')

    @Slot()
    def toggleOvcArm(self):
        self._cancel_auto('ovc')
        if not self._ovc_armed:self._enable_device('ovc');return
        self._ovc_armed=False;self._ovc_planner.reset();self._ovc_warm=0;self._ovc_stamp=None
        if self._ovc_service:self._ovc_service.set_output_permission(False,'负鼠已暂停')
        self._emit_changed()

    @Slot(str,bool)
    def setOvcChannelEnabled(self,channel,enabled):
        if channel not in ('A','B'):return
        self._ovc_channels[channel]=enabled
        if not enabled and self._ovc_service:self._ovc_service.stop_channel(channel)
        self._emit_changed()

    @Slot(str,int)
    def setOvcLimit(self,channel,value):
        if channel not in ('A','B'):return
        self._ovc_limits[channel]=int(self._clamp(value,0,200)//10)*10;self._simulation_changed()

    @Slot()
    def startMockBoth(self):
        if self.offline:self.toast.emit('离线预览不启动模拟 APP');return
        if self._mock_session:return
        from .v4 import V4ConnectionService
        from .mock_session import MockSession
        restore=dict(self._connection);self.stopConnection()
        self._mock_restore=restore;self._connection['pulse_backend']='v4'
        self._sim_running=False;self._sim_source='live';self._simulator.reset()
        self._v4=V4ConnectionService(port=0,host='127.0.0.1',lan_ip='127.0.0.1')
        self._service=self._v4.channel('pulse');self._ovc_service=self._v4.channel('ovc')
        self._mock_session=MockSession(self._v4,self.settings.parent/'mock-sessions')
        self._last_mock_path=str(self._mock_session.directory)
        self._mock_session.profile(self._sim_profile,self._channels,self._ovc_limits)
        self._v4.start();self._mock_session.start();self._mock_pending=True
        self.log('mock','已开启四通道本机模拟 APP 与持续记录 · 使用当前预设','系统');self._emit_changed()

    @Slot()
    def resumeMockBoth(self):
        if not self._mock_session or not self._mock_session.snapshot()['connected']:return
        for role in ('pulse','ovc'):self._enable_device(role)
        self._emit_changed()

    def _poll_mock_session(self):
        if not self._mock_session or not self._mock_pending:return
        m=self._mock_session.snapshot()
        if m['error']:
            self._armed=False;self._ovc_armed=False;self._reset_output();self._mock_pending=False;return
        if not m['connected']:return
        for role,slot in (('pulse','coyote'),('ovc','ovc')):
            if self._requested_devices.get(role)!=(m['client_id'],slot):self.selectV4Device(role,m['client_id'],slot)
        if all(self._v4.channel(r).snapshot().get('feedback_known') for r in ('pulse','ovc')):
            self._mock_pending=False;self.resumeMockBoth()

    @Slot()
    def stopMockBoth(self):
        if not self._mock_session:return
        self._armed=False;self._ovc_armed=False;self._mock_pending=False;self._reset_output()
        if self._v4:self._v4.stop()
        self._mock_session.stop();self._mock_session=None;self._v4=self._service=self._ovc_service=None
        if self._mock_restore:self._connection=dict(self._mock_restore)
        self._mock_restore=None;self.log('mock','模拟 APP 已归零并保存记录 · '+self._last_mock_path,'系统');self._emit_changed()

    @Slot()
    def openMockRecords(self):
        if self._last_mock_path:QDesktopServices.openUrl(QUrl.fromLocalFile(self._last_mock_path))

    @Property('QVariantMap',notify=changed)
    def mockValidation(self):
        session=self._mock_session.snapshot() if self._mock_session else {}
        notes=[];g=self._sim_profile.get('gallery') or {};rule=g.get('rule') or {}
        for route,name in (('pulse','Pulse'),('vibration','负鼠')):
            for c in 'AB':
                if c not in rule.get(route+'_channel','') or not rule.get(route+'_enabled'):notes.append(name+' '+c+'：图鉴通道未启用')
                elif self._sim_profile['channel_feedback'][route][c]=='damage':notes.append(name+' '+c+'：当前仅受伤，不输出 CG')
        return dict(session,active=bool(self._mock_session),preview=self._sim_running,path=session.get('directory',self._last_mock_path),
            status='模拟 APP 已连接 · 实际发送记录中' if session.get('connected') else '正在连接本机模拟 APP' if session.get('running') else '曲线预览 · 未连接模拟 APP' if self._sim_running else '尚未连接模拟 APP',
            notes=notes,pulseArmed=self._armed,ovcArmed=self._ovc_armed)

    @Slot()
    def startMockPulse(self):
        if self.offline:self.toast.emit('离线截图不启动本机测试');return
        if self._mock_session:self.stopMockBoth()
        if self._v4:self.stopV4()
        self._ovc_armed=False
        if self._connection['pulse_backend']!='mock':self.setPulseBackend('mock')
        if self._service and self._service.snapshot().get('connected'):self.toast.emit('已有本机 APP 已连接');return
        self._sim_running=False;self._sim_source='live';self._simulator.reset();self._armed=False;self._reset_output()
        if not self._service or not self._service.snapshot().get('server_ready'):self.startConnection()
        if self._service:
            from .mock_app import MockAppRunner
            if self._mock_app:self._mock_app.stop()
            self._mock_app=MockAppRunner(self._service,ROOT/'artifacts/pulse-validation/live-mock-app.json');self._mock_app.start()
        self._emit_changed()

    @Slot(str,bool)
    def setPulseChannelEnabled(self,channel,enabled):
        if channel not in ('A','B'):return
        self._pulse_channels[channel]=enabled
        if not enabled and self._service:self._service.stop_channel(channel)
        self._emit_changed()

    @Slot()
    def stopConnection(self):
        if self._mock_session:self.stopMockBoth();return
        if self._service:self._service.stop();self._service=None
        if self._mock_app:self._mock_app.stop();self._mock_app=None
        if self._v4:self._v4.stop();self._v4=None
        self._ovc_service=None;self._ovc_armed=False
        self._qr='';self._qrurl='';self._armed=False;self._reset_output();self._emit_changed()

    @Slot(str)
    def selectIp(self,ip):
        if self._service and hasattr(self._service,'set_lan_ip'):self._service.set_lan_ip(ip)
        if self._v4:self._v4.set_lan_ip(ip)
        self._ip=ip;self._connection['lan_ip']=ip;self.save();self.configChanged.emit();self._emit_changed()

    @Slot()
    def copyConnection(self):
        if self._qrurl:QGuiApplication.clipboard().setText(self._qrurl);self.toast.emit('连接地址已复制')

    @Slot(str,result=str)
    def qrImage(self,url):
        if not url:return ''
        if not hasattr(self,'_qr_cache'):self._qr_cache={}
        if url not in self._qr_cache:
            import qrcode
            image=qrcode.make(url);buf=io.BytesIO();image.save(buf,format='PNG')
            self._qr_cache={url:'data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode()}
        return self._qr_cache[url]

    @Slot()
    def toggleHud(self):self.setHudSetting('enabled',not self._hud)

    @Slot()
    def exportEvents(self):
        p=ROOT/'artifacts/events-export.json';p.write_text(json.dumps(self._events,ensure_ascii=False,indent=2),encoding='utf-8');QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)));self.toast.emit('事件已导出到 artifacts/events-export.json')

    @Slot()
    def openFolder(self):QDesktopServices.openUrl(QUrl.fromLocalFile(str(ROOT/'artifacts')))

    def tick(self):
        # Record every callback, then publish one display update per polling round.
        # Catalog invalidation is independent of the high-frequency event stream.
        self._event_batch=True
        try:self._tick()
        finally:
            self._event_batch=False
            lines,self._event_lines=self._event_lines,[]
            events,flows=self._events_dirty,self._flows_dirty
            self._events_dirty=self._flows_dirty=False
            self._write_event_lines(lines)
            if flows:self.flowsChanged.emit()
            if events:self.eventsChanged.emit()

    def _tick(self):
        if not self.offline:self._trainer.poll(self._game_directory/'BepInEx/plugins/SiNiSistarTrainer/ipc')
        self._poll_installer()
        self._probe_game_process()
        if self._observer:self._live=self._observer.snapshot()
        now=time.monotonic();callbacks=[]
        if self._observer:
            for _ in range(100):
                try:callbacks.append(self._observer.events.get_nowait())
                except queue.Empty:break
        self._live=self._locked_hp.update(self._live,callbacks,now=now)
        self._live=self._same_hp.update(self._live,callbacks,now=now)
        self._live.setdefault('feedback_evidence',{})['same_hp_timeout']=(self._sim_profile.get('cg') or {}).get('same_hp_timeout',3.)
        self._cg_info=describe_game_cg(self._live,now)
        self._live['feedback_evidence']['cg_detection']=dict(mode=self._sim_profile.get('cg_detection_mode','hybrid'),**self._cg_info)
        s=self._live;fresh=s.get('live') and now-s.get('sampled_at',0)<.6
        valid=bool(fresh and s.get('valid'))
        plugin_online=bool(fresh and s.get('observer_version') and self._install_state.get('selectedPath')==str(self._game_directory))
        interface_message=('游戏接口检查通过 · 可以进行联动测试' if plugin_online and s.get('compatibility') else s.get('error','') if str(s.get('error','')).startswith('游戏接口检查未通过') else '')
        if interface_message!=self._install_state.get('interfaceMessage',''):
            self._install_state.update(interfaceMessage=interface_message,interfaceError=interface_message.startswith('游戏接口检查未通过'));self.installChanged.emit()
        if plugin_online!=self._install_state.get('pluginOnline',False):
            self._install_state['pluginOnline']=plugin_online
            if plugin_online:self._install_state.update(needsRestart=False,gameRunning=True,message='观察插件已在线，正在读取当前游戏。')
            self.installChanged.emit()
        dialogue_identity=(s.get('session'),s.get('pid'),s.get('player'),s.get('scene_id'))
        if not fresh or dialogue_identity!=self._dialogue_identity:self._dialogue_until=0.;self._dialogue_identity=dialogue_identity
        if (s.get('flow') or {}).get('playing'):self._dialogue_until=0.
        if fresh and s.get('session') and self._monitor.session!=s['session']:
            self._monitor.begin_session(s['session'])
            history=self._observer.recent_events(s['session']) if self._observer else []
            for event in history:
                self._monitor.callback(event,TYPES['AbnormalType'],history=True)
            # Recover previously observed state edges for this plugin session for
            # display only. They never enter the output detector or event queue.
            if history:
                start=min(parse_time(x['utc']) for x in history)
                try:
                    path=ROOT/'artifacts/events.jsonl'
                    with path.open('rb') as f:
                        f.seek(max(0,path.stat().st_size-256000));lines=f.read().splitlines()
                    for line in lines:
                        try:
                            e=json.loads(line)
                            if e.get('key') in ('break','heal','hp0','escape','abnormal','same_hp_start','same_hp_end') and start<=parse_time(e['utc']):
                                self._monitor.add(e['key'],e['text'],'组合判定' if e['key']=='escape' else '状态边沿',e['utc'],history=True)
                        except (ValueError,KeyError,TypeError):continue
                except OSError:pass
            self._notify_events()
        gallery_rows=self._gallery.update(s,now)
        for row in gallery_rows:
            self._monitor.add(row['key'],row['text'],'图鉴只读');self.log(row['key'],row['text'],'图鉴只读')
        monitor_rows=self._monitor.snapshot(s if fresh and (valid or scripted_go_penalty(s)) else None)
        for row in monitor_rows:
            if row.get('key') in ('same_hp_start','same_hp_end'):self.log(row['key'],row['text'],'组合判定')
        sim_events=list(monitor_rows)
        if monitor_rows:self._notify_events()
        if fresh and self._flows.observe(s):self._notify_flows()
        self._status=('已暂停' if s.get('paused') else '同值 HP 演出' if same_hp_flow(s,(self._sim_profile.get('cg') or {}).get('same_hp_timeout',3.)) else '死亡惩罚阶段' if death_penalty_stage(s) else '正在观察') if valid else '独立战败 CG' if fresh and scripted_go_penalty(s) else '离线预览' if self.offline else '等待游戏就绪'
        if self._gallery.previous['inGallery']:self._status=self._gallery.previous['label']
        elif self._cg_info.get('recognized'):self._status='CG 播放 · '+self._cg_info['name']
        if valid:self._last=deepcopy(s)
        if self._v4:self._v4.snapshot()  # Drain shared APP status into route queues.
        self._poll_mock_session();self._sync_auto_devices()
        vibration_waves=VIBRATION_WAVES+self._vibration_custom
        if self._output_worker:
            self._publish_output_controls()
            output=self._output_worker.snapshot()
            self._pulse_plan=output['pulse'];self._ovc_plan=output['ovc'];self._reason=output['reason']
        else:
            from .output_runtime import plan_outputs
            plan_outputs(self,s,now)
        con=self._service.snapshot() if self._service else {}
        ovc=self._ovc_service.snapshot() if self._ovc_service else {}
        for e in self._detector.update(s):
            self.log(e['key'],e['text'],'已验证' if e['verified'] else '候选')
        if self._observer:
            for e in callbacks:
                try:
                    age=(datetime.now(timezone.utc)-parse_time(e['utc'])).total_seconds()
                    live_callback=valid and 0<=age<.6 and e.get('session')==s.get('session') and e.get('player')==s.get('player')
                    if live_callback:
                        if e.get('event_type')=='flow_request_callback':self._dialogue_until=now+1.5
                        elif e.get('event_type')=='flow_stop_callback':self._dialogue_until=0.
                except (KeyError,ValueError,TypeError):live_callback=False
                row=self._monitor.callback(e,TYPES['AbnormalType'])
                if row:
                    self.log('plugin',row['title']+' · '+row['text'],'插件回调')
                    # File history never enters the preview trigger stream.
                    try:
                        age=(datetime.now(timezone.utc)-parse_time(e['utc'])).total_seconds()
                        if valid and 0<=age<.6 and e.get('session')==s.get('session') and e.get('player')==s.get('player'):
                            sim_events.append(row)
                    except (KeyError,ValueError,TypeError):pass
                else:self._notify_events()
        sim_state=s;sim_profile=self._sim_profile
        if self._sim_source!='live':
            sim_state=demo_state(self._sim_source,now-self._demo_start,now);sim_events=[]
            if self._sim_source=='flow':
                sim_profile=deepcopy(self._sim_profile);sim_profile['flows']=[base_rule('DEMO|flow','演出样例',priority=60)]
        self._sim_plan=self._simulator.evaluate(sim_state,sim_profile,self._waves,now=now,enabled=self._sim_running,emergency=self._emergency,events=sim_events,demo=self._sim_source!='live',vibration_waves=vibration_waves)
        if self._service:
            url=(('ws://127.0.0.1:'+str(con['port'])+'/'+con['controller_id']) if con.get('local_only') else con.get('qr_url','')) if con.get('server_ready') else ''
            if url!=self._qrurl:
                self._qrurl=url;self._qr=''
                if url and not con.get('local_only'):
                    self._qr=self.qrImage(url)
            for _ in range(100):
                try:e=self._service.events.get_nowait()
                except queue.Empty:break
                if e['event']=='command_sent' and str(e.get('command','')).startswith(('pulse-A:','pulse-B:')):
                    try:
                        channel=e['command'][6];frames=json.loads(e['command'].split(':',1)[1]);samples=[]
                        for frame in frames:
                            if len(frame)!=16:raise ValueError('frame length')
                            samples.extend(min(1.,int(frame[j:j+2],16)/100) for j in range(8,16,2))
                        self._traces[channel]=(self._traces[channel]+samples)[-64:];self._trace_new.add(channel)
                    except (ValueError,TypeError,IndexError,KeyError):pass
                if e['event'] in ('connected','disconnected','error','feedback_started','feedback_end','zero_sent'):
                    if e['event']=='error' and not e.get('recoverable'):
                        self._armed=False;self._auto_pending.pop('pulse',None);self._reset_output(ovc=False)
                    self.log('device',{'connected':'APP 配对完成','disconnected':'APP 已断开','error':e.get('error') or e.get('detail') or e.get('reason') or '连接异常','feedback_started':'设备波形输出开始','feedback_end':'设备波形输出结束','zero_sent':'已发送归零和清队列'}.get(e['event'],e['event']),'设备')
        if self._ovc_service:
            for _ in range(100):
                try:e=self._ovc_service.events.get_nowait()
                except queue.Empty:break
                if e.get('event')=='command_sent' and str(e.get('command','')).startswith(('pulse-A:','pulse-B:')):
                    try:
                        channel=e['command'][6];frames=json.loads(e['command'].split(':',1)[1]);samples=[int(f[j:j+2],16)/100 for f in frames for j in range(8,16,2)]
                        self._ovc_traces[channel]=(self._ovc_traces[channel]+samples)[-64:];self._ovc_trace_new.add(channel)
                    except (ValueError,TypeError,IndexError,KeyError):pass
                elif e.get('event')=='error':
                    if not e.get('recoverable'):
                        self._ovc_armed=False;self._auto_pending.pop('ovc',None)
                    self._ovc_service.set_output_permission(False,'负鼠输出错误')
                    self.log('ovc',e.get('error') or e.get('detail') or e.get('reason') or '负鼠连接异常','设备')
        if now-self._trace_at>=.1:
            for channel in ('A','B'):
                if channel not in self._trace_new:self._traces[channel]=(self._traces[channel]+[0.0]*4)[-64:]
                if channel not in self._ovc_trace_new:self._ovc_traces[channel]=(self._ovc_traces[channel]+[0.0]*4)[-64:]
            self._ovc_trace_new.clear()
            self._trace_new.clear();self._trace_at=now
        if not self.offline and now-self._diagnostics_at>=1:
            self._diagnostics_at=now
            diagnostic=dict(utc=datetime.now(timezone.utc).isoformat(),pulse=con,ovc=ovc,devices=self.v4Devices,
                            ui=dict(language=self._language,emergencyHotkey=self.hotkeySettings,tutorial=self._tutorial),
                            pulseArmed=self._armed,ovcArmed=self._ovc_armed,pulseReason=self._reason,ovcReason=self._ovc_plan['reason'],
                            pulseSetup=self._device_setup('pulse',con),ovcSetup=self._device_setup('ovc',ovc),
                            game={k:s.get(k) for k in ('live','valid','paused','hp','scene','event_playing','feedback_evidence')},
                            galleryPlayback=describe_gallery(s,now),
                            cgPlayback=self._cg_info,cgDetectionMode=self._sim_profile.get('cg_detection_mode','hybrid'),
                            outputWorker={k:v for k,v in self._output_worker.snapshot().items() if k not in ('pulse','ovc')} if self._output_worker else {},
                            penaltyClassification=current_penalty_class(s)[0],penaltyLabel=current_penalty_class(s)[1])
            try:
                path=self.settings.parent/'connection-diagnostics.json';temp=path.with_suffix('.tmp')
                temp.write_text(json.dumps(diagnostic,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(path)
            except OSError:pass
        if self._mock_session:
            self._mock_session.record(s,self._pulse_plan,self._ovc_plan,
                self._service.snapshot().get('output_channels',{}) if self._service else {},
                self._ovc_service.snapshot().get('output_channels',{}) if self._ovc_service else {},self._armed,self._ovc_armed,compact=self._cg_batch.data is not None)
        if (self._developer_tools or self._cg_batch_active) and self._cg_batch.data is not None:
            self._cg_batch.observe(s,self._pulse_plan,self._ovc_plan,con.get('output_channels',{}),ovc.get('output_channels',{}),
                self._mock_session.snapshot() if self._mock_session else {},self._sim_profile.get('cg_detection_mode','hybrid'),now)
            self._cg_batch.save(now)
            if now-self._cg_batch_at>=.5:self._cg_batch_at=now;self._refresh_batch()
        if self._developer_tools:
            self._cg_coverage.observe(s,self._pulse_plan,self._ovc_plan,con.get('output_channels',{}),ovc.get('output_channels',{}),self._sim_profile.get('cg_detection_mode','hybrid'),now)
        if self._developer_tools and now-self._cg_coverage_at>=1 and self._cg_coverage.dirty:
            self._cg_coverage_at=now
            try:self._cg_coverage.save(now)
            except OSError:pass
            self._cg_coverage_rows=self._cg_coverage.rows();self.cgCoverageChanged.emit()
        self._emit_changed(live=True)

    @Slot()
    def requestExit(self):self.exitRequested.emit()

    def shutdown(self):
        if self._shutdown_started:return
        self._shutdown_started=True;self._timer.stop();self._armed=False;self._ovc_armed=False
        if self._output_worker:self._output_worker.close()
        try:self._cg_coverage.save(force=True)
        except OSError:pass
        self._cg_batch.close()
        if self._hotkey_manager:self._hotkey_manager.close()
        def cleanup(name,operation):
            try:operation()
            except Exception as error:self._shutdown_errors.append(name+'：'+str(error))
        hub=self._v4;service=self._service;ovc=self._ovc_service
        for name,route in (('Pulse',service),('负鼠',ovc)):
            if route and hasattr(route,'set_output_permission'):
                cleanup(name+' 停止输出',lambda route=route:route.set_output_permission(False,'控制中心正在退出'))
        # Keep V4 selections attached until the shared hub has sent zero to both
        # slots. Stopping the Pulse role first would discard its selected device.
        if service and (not hub or service is not hub.channel('pulse')):
            cleanup('Pulse 归零',service.emergency_zero);cleanup('Pulse 断开',service.stop)
        if hub:cleanup('V4 归零并断开',hub.stop)
        if self._mock_session:cleanup('四通道模拟记录',self._mock_session.stop);self._mock_session=None
        if self._mock_app:cleanup('模拟 APP',self._mock_app.stop)
        if self._observer:cleanup('观察读取',self._observer.stop)
        if self._install_thread and self._install_thread.is_alive():cleanup('安装线程',lambda:self._install_thread.join(timeout=3))
        self._service=self._ovc_service=self._v4=self._mock_app=self._observer=None
        if self._shutdown_errors:
            cleanup('退出日志',lambda:self.log('shutdown','；'.join(self._shutdown_errors),'系统'))
