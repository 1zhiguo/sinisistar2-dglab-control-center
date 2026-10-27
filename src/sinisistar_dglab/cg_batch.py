"""Automatic gallery visit journal with explicit human feedback, never output authority."""
from pathlib import Path
from datetime import datetime,timezone
from copy import deepcopy
import csv,io,json,time,uuid,zipfile,os
from .cg_playback import fresh
from .gallery import describe_gallery
from .flow_semantics import enemy_name

ALIASES={r['value']:r['name'].removeprefix('GaID_') for r in json.loads((Path(__file__).parent/'assets/capture-candidates.json').read_text(encoding='utf-8'))['gallery']}
LABELS={'MidasTouch':'米达斯之触','Bobel_Barnacle':'博贝尔 · 藤壶','BobelDarktacle':'博贝尔 · 暗触须','Demihuman_Prison':'亚人 · 牢狱'}
CHANNELS=('pulseA','pulseB','vibrationA','vibrationB')
VERDICTS={'':'待标记','yes':'有反馈','no':'无反馈'}
def utc():return datetime.now(timezone.utc).isoformat()
def clean_profile(profile):
    # No connections, IPs, game paths, helper commands or account data.
    result=deepcopy({k:profile[k] for k in ('channels','ovc_limits','custom_waves','custom_vibration_waves') if k in profile})
    source=profile.get('simulation') or {}
    result['simulation']=deepcopy({k:v for k,v in source.items() if k in ('cg','gallery','cg_detection_mode','channel_feedback','mix','quick_active_preset') or k.startswith(('pulse_cap_','vibration_cap_'))})
    result['simulation']['death_rule']=deepcopy((source.get('rules') or {}).get('defeat_hold',{}));return result

class CgBatchRecorder:
    def __init__(self,root):
        self.root=Path(root);self.data=None;self.dirty=False;self.error='';self.last_save=0.
        self.active_visit=None;self.live_case='';self.last_case='';self.last_at=None;self.sample_at=0.;self.change_key=None;self.maturity_at=0.;self.writer=None;self.blocked=False
        try:
            current=json.loads((self.root/'current.json').read_text(encoding='utf-8'))['round']
            if not isinstance(current,str) or Path(current).name!=current or current in ('.','..') or not (self.root/current).resolve().is_relative_to(self.root.resolve()):raise ValueError('Invalid round')
            data=json.loads((self.root/current/'round.json').read_text(encoding='utf-8'))
            if data.get('schema')!=1 or data.get('id')!=current or data.get('status') not in ('recording','paused','finished') or not isinstance(data.get('cases'),dict) or not data.get('profiles') or not isinstance(data.get('visits'),list):raise ValueError('Invalid journal')
            self.data=data
            for visit in data.get('visits',[]):
                if not visit.get('end'):visit.update(end=utc(),end_reason='上次窗口关闭 / 记录中断')
            self.last_case=data.get('last_case','');self.dirty=True
        except (OSError,ValueError,KeyError,TypeError):pass
    @property
    def recording(self):return bool(self.data and self.data['status']=='recording' and not self.blocked)
    def _writer(self):
        if self.blocked:return False
        if self.writer is not None:return True
        try:
            self.root.mkdir(parents=True,exist_ok=True);stream=(self.root/'writer.lock').open('a+b')
            if stream.tell()==0:stream.write(b'0');stream.flush()
            stream.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.writer=stream;return True
        except OSError:
            if 'stream' in locals():stream.close()
            self.blocked=True;self.error='已有批量测试窗口正在记录，请先关闭重复窗口后重新打开';return False
    def ensure(self,profile):
        if not self._writer():return
        if self.data is None:self.new(profile)
    def new(self,profile):
        if not self._writer():return
        if self.data is not None:self.finish()
        key=datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]
        self.data=dict(schema=1,id=key,created=utc(),updated=utc(),status='recording',cases={},visits=[],last_case='',profiles=[dict(at=utc(),data=clean_profile(profile))])
        self.active_visit=None;self.live_case=self.last_case='';self.last_at=None;self.change_key=None;self.dirty=True
        self.root.mkdir(parents=True,exist_ok=True);temp=self.root/'current.tmp';temp.write_text(json.dumps(dict(round=key)),encoding='utf-8');temp.replace(self.root/'current.json');self.save(force=True)
    def profile(self,profile):
        if self.data is None or self.data['status']=='finished':return
        data=clean_profile(profile)
        if self.data['profiles'][-1]['data']!=data:
            self.data['profiles'].append(dict(at=utc(),data=data));self.dirty=True
    def _close(self,reason):
        if self.active_visit is not None:
            self.active_visit.update(end=utc(),end_reason=reason);self.dirty=True
        self.active_visit=None;self.live_case='';self.last_at=None;self.change_key=None
    def pause(self):
        if self.data is None:return
        self._close('暂停记录');self.data['status']='paused';self.dirty=True;self.save(force=True)
    def resume(self):
        if self.data is None or self.data['status']=='finished':return
        self.data['status']='recording';self.dirty=True;self.save(force=True)
    def finish(self):
        if self.data is None:return
        self._close('本轮完成');self.data.update(status='finished',finished=utc());self.dirty=True;self.save(force=True)
    def _case(self,enemy,index,count):
        raw=ALIASES.get(enemy,'#'+str(enemy));label=LABELS.get(raw,enemy_name(raw));key=f'gallery:{enemy}:{index}'
        if key not in self.data['cases']:
            self.data['cases'][key]=dict(id=key,enemy_id=enemy,enemy=label,raw_enemy=raw,index=index,take_count=count,name='',kind='',verdict='',note='',visits=0,
                observed_seconds=0.,recognized=False,planned=[],sent=[],received=[],counts={c:0 for c in CHANNELS},reason='',latest_visit=None)
        self.data['cases'][key]['take_count']=count;return self.data['cases'][key]
    def observe(self,s,pulse,ovc,pulse_wire,ovc_wire,mock,mode,now):
        if not self.recording:return
        view=describe_gallery(s,now);g=s.get('gallery') or {}
        if not fresh(s,now) or not view['inGallery'] or not view['selectionActive']:
            self._close('数据中断' if not fresh(s,now) else '返回列表 / 离开图鉴');return
        enemy=g.get('enemy_id');index=g.get('selected_index_raw');count=g.get('take_count')
        if type(enemy) is not int or enemy<0 or type(count) is not int or not 0<index<=count<=256:self._close('片段索引尚未就绪');return
        for n in range(1,count+1):self._case(enemy,n,count)
        case=self._case(enemy,index,count);key=case['id'];identity=(s.get('session'),s.get('pid'),key)
        if self.active_visit is None and self.data['visits']:
            previous=self.data['visits'][-1]
            if previous['identity']==list(identity) and previous.get('end_reason') in ('数据中断','控制中心关闭','上次窗口关闭 / 记录中断','暂停记录'):
                previous.update(end=None,end_reason='',resumed=previous.get('resumed',0)+1,
                    counter_offsets=dict(previous['counts']),initial_counters={c:mock.get('receipts',{}).get(c,{}).get('count',0) for c in CHANNELS})
                self.active_visit=previous;self.live_case=self.last_case=key;self.maturity_at=now;self.last_at=None;self.sample_at=0.
        if self.active_visit is None or self.active_visit['identity']!=list(identity):
            self._close('切换片段')
            visit=dict(id=len(self.data['visits'])+1,case_id=key,identity=list(identity),start=utc(),end=None,end_reason='',seconds=0.,verdict='',note=case['note'],
                observer_version=s.get('observer_version',''),mode=mode,mock_only=bool(mock.get('connected')),mock_session=Path(mock.get('directory') or '').name,
                planned=[],sent=[],received=[],counts={c:0 for c in CHANNELS},evidence=[],initial_counters={c:mock.get('receipts',{}).get(c,{}).get('count',0) for c in CHANNELS})
            self.data['visits'].append(visit);self.active_visit=visit;case.update(visits=case['visits']+1,latest_visit=visit['id'],verdict='')
            self.live_case=self.last_case=key;self.data['last_case']=key;self.maturity_at=now;self.sample_at=0.;self.dirty=True
        visit=self.active_visit;delta=max(0.,min(.6,now-self.last_at)) if self.last_at is not None else 0.;self.last_at=now
        visit['seconds']=round(visit['seconds']+delta,3);case['observed_seconds']=round(case['observed_seconds']+delta,3)
        # UI identity is enemy + numbered button. A leftover old take name must
        # not rename the new button during its initial loading frames.
        if now-self.maturity_at>=.4:
            case['name']=str(g.get('take_name') or '');case['kind']=view['playType']
        recognized=bool(view['playing']);case['recognized']|=recognized
        planned=set(visit['planned']);sent=set(visit['sent']);received=set(visit['received']);details={}
        receipts=mock.get('receipts') or {}
        for route,plan,wire in (('pulse',pulse,pulse_wire),('vibration',ovc,ovc_wire)):
            for c in 'AB':
                channel=route+c;frame=plan.get(route+'_stream',{}).get(c);active=bool(recognized and plan.get('hp_used') is False and frame and frame.get('peak',0)>0)
                if active:planned.add(channel)
                if active and now-self.maturity_at>=.25:
                    if (wire.get(c) or {}).get('active') and (wire[c].get('deadline') or 0)>now:sent.add(channel)
                    receipt=receipts.get(channel) or {};base=visit['initial_counters'][channel]
                    if mock.get('connected') and receipt.get('at',0)>=self.maturity_at+.25 and receipt.get('count',0)>base:
                        received.add(channel);visit['counts'][channel]=max(visit['counts'][channel],visit.get('counter_offsets',{}).get(channel,0)+receipt['count']-base)
                details[channel]=dict(planned=active,strength=round((frame or {}).get('peak',0),1),wire=bool((wire.get(c) or {}).get('active')),receipts=visit['counts'][channel])
        visit.update(planned=sorted(planned),sent=sorted(sent),received=sorted(received),mode=mode)
        for field in ('planned','sent','received'):case[field]=sorted(set(case[field])|set(visit[field]))
        case['counts']={c:sum(v['counts'][c] for v in self.data['visits'] if v['case_id']==key) for c in CHANNELS}
        reason='；'.join(dict.fromkeys(filter(None,(pulse.get('reason'),ovc.get('reason')))));case['reason']=reason
        case['live_channels']=details;case['playback_evidence']=view.get('playbackEvidence','');case['last_mode']=mode;case['mock_only']=bool(mock.get('connected'))
        marker=(key,view['phase'],view.get('playbackEvidence'),reason,tuple(visit['received']))
        if marker!=self.change_key or now-self.sample_at>=1:
            sample=dict(utc=s.get('utc') or utc(),visit=visit['id'],case_id=key,elapsed=visit['seconds'],mode=mode,
                observer_version=s.get('observer_version'),gallery=deepcopy(g),cg_playback=deepcopy(s.get('cg_playback') or {}),
                pulse={k:deepcopy(pulse.get(k)) for k in ('reason','source','pulse_stream','gallery_age','hp_used')},
                vibration={k:deepcopy(ovc.get(k)) for k in ('reason','source','vibration_stream','gallery_age','hp_used')},receipts=deepcopy(receipts))
            try:
                directory=self.root/self.data['id'];directory.mkdir(exist_ok=True)
                with (directory/'samples.jsonl').open('a',encoding='utf-8') as stream:stream.write(json.dumps(sample,ensure_ascii=False)+'\n')
            except OSError as error:self.error=str(error)
            if len(visit['evidence'])<6:visit['evidence'].append(dict(utc=sample['utc'],elapsed=visit['seconds'],playback=view.get('playbackEvidence'),reason=reason,received=sorted(received)))
            self.change_key=marker;self.sample_at=now
        self.dirty=True
    def mark(self,key,verdict):
        if self.blocked or self.data is None or key not in self.data['cases'] or verdict not in VERDICTS:return False
        case=self.data['cases'][key]
        if not case['visits']:return False
        case.update(verdict=verdict,marked_at=utc())
        visit=next(v for v in reversed(self.data['visits']) if v['case_id']==key);visit.update(verdict=verdict,marked_at=utc())
        self.dirty=True;return self.save(force=True)
    def note(self,key,note):
        if self.blocked or self.data is None or key not in self.data['cases']:return False
        note=str(note)[:2000];self.data['cases'][key]['note']=note
        visit=next((v for v in reversed(self.data['visits']) if v['case_id']==key),None)
        if visit is not None:visit['note']=note
        self.dirty=True;return self.save(force=True)
    def save(self,now=None,force=False):
        now=time.monotonic() if now is None else now
        if self.data is None or not self.dirty or not force and now-self.last_save<1:return False
        if not self._writer():return False
        try:
            directory=self.root/self.data['id'];directory.mkdir(parents=True,exist_ok=True);self.data['updated']=utc()
            temp=directory/'round.tmp';temp.write_text(json.dumps(self.data,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(directory/'round.json')
            self.dirty=False;self.error='';self.last_save=now;return True
        except OSError as error:self.error=str(error);return False
    def rows(self):
        if self.data is None:return []
        latest_by_case={visit['case_id']:visit for visit in self.data['visits']}
        rows=[]
        for case in self.data['cases'].values():
            latest=latest_by_case.get(case['id'],{})
            received=latest.get('received',[])
            automatic='模拟 APP 已收到四通道' if len(received)==4 else '模拟 APP 收到部分通道' if received else '已生成波形' if latest.get('planned') else '已识别播放' if case['recognized'] else '未识别播放' if case['visits'] else '未打开'
            rows.append(dict(case,title=case['enemy']+' · ['+str(case['index'])+']',manual_label=VERDICTS[case['verdict']],automatic=automatic,current=case['id']==self.live_case,latest_received=received,latest_counts=latest.get('counts',{})))
        return sorted(rows,key=lambda r:(r['enemy_id'],r['index']))
    def snapshot(self):
        rows=self.rows();seen=[r for r in rows if r['visits']]
        return dict(exists=self.data is not None,round=self.data['id'] if self.data else '',recording=self.recording,status='blocked' if self.blocked else self.data['status'] if self.data else 'idle',
            current=self.live_case,focus=self.live_case or self.last_case,known=len(rows),observed=len(seen),unopened=len(rows)-len(seen),yes=sum(r['verdict']=='yes' for r in seen),
            no=sum(r['verdict']=='no' for r in seen),unmarked=sum(not r['verdict'] for r in seen),rows=rows,error=self.error,saved=not self.dirty)
    def export(self):
        if self.data is None:raise ValueError('尚无测试记录')
        if self.dirty and not self.save(force=True):raise OSError(self.error)
        out=self.root/'exports';out.mkdir(parents=True,exist_ok=True)
        target=out/('CG-test-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]+'.zip');temporary=target.with_suffix('.tmp')
        rows=self.rows();summary=dict(self.data,notes='有/无反馈为用户标记；机器识别、波形计划、发送及模拟 APP 收包独立记录。图鉴结果不代表实战覆盖。')
        observed_enemies={r['enemy_id'] for r in rows if r['visits']}
        summary['coverage_scope']=dict(known_numbered_cases=len(rows),unopened_known_cases=[r['id'] for r in rows if not r['visits']],
            unvisited_enum_candidates=[dict(enemy_id=key,name=name) for key,name in ALIASES.items() if key>=0 and key not in observed_enemies],
            note='编号总数仅覆盖已访问怪物；未访问枚举可能包含隐藏或未使用条目，不等同于实际缺失 CG 数。')
        stream=io.StringIO(newline='');writer=csv.writer(stream);writer.writerow(['怪物','编号','片段','类型','用户反馈','备注','观察秒数','播放识别','累计生成通道','累计发送通道','累计模拟收到通道','模式','次数'])
        for r in rows:writer.writerow([r['enemy'],r['index'],r['name'],r['kind'],r['manual_label'],r['note'],r['observed_seconds'],r['recognized'],'/'.join(r['planned']),'/'.join(r['sent']),'/'.join(r['received']),r.get('last_mode',''),r['visits']])
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('report.json',json.dumps(summary,ensure_ascii=False,indent=2));z.writestr('results.csv','\ufeff'+stream.getvalue())
            source=self.root/self.data['id']/'samples.jsonl'
            if source.exists():
                # The recorder/exporter run on the same GUI thread; no writer
                # can append or split a JSON line while this snapshot is made.
                z.write(source,'samples.jsonl')
            z.writestr('READ_ME.txt','CG 批量测试报告\nreport.json：用户选择、每次访问、预设及证据。\nresults.csv：便于查看的结果表。\nsamples.jsonl：切换/状态变化及每秒采样，包含模拟 APP 实际收包计数。\n用户的“有/无反馈”和机器结果分别保存。未打开、待标记和失败不混淆。\n')
        temporary.replace(target);return target
    def close(self):
        self._close('控制中心关闭');self.save(force=True)
        if self.writer is not None:self.writer.close();self.writer=None
