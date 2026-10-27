"""Display-only event interpretation. Nothing here authorizes device output."""
from __future__ import annotations
import json, re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from .status_policy import positive_status
from .penalty_flows import current_penalty_class
from .scripted_go import scripted_go_penalty
from .same_hp import same_hp_flow

LABELS = json.loads((Path(__file__).parent/'assets/status-labels.json').read_text(encoding='utf-8'))

def parse_time(value):
    return datetime.fromisoformat(re.sub(r'(\.\d{6})\d+(?=[+-]\d{2}:\d{2}$)', r'\1', value.replace('Z', '+00:00')))

def status_label(name):
    return LABELS.get(name, {}).get('label', name)

def statuses(items,profile=None):
    rows=[]
    for x in items:
        name=x.get('name','未知状态');positive=positive_status(x);rule=(profile or {}).get('abnormals',{}).get(name,{})
        level=x.get('level');eligible=bool(not positive and isinstance(level,(int,float)) and level>0 and rule.get('enabled'))
        pulse=bool(eligible and rule.get('pulse_enabled'));ovc=bool(eligible and rule.get('vibration_enabled'))
        rows.append(dict(name=name,label=x.get('localized_name') or status_label(name),
                         level=level,raw=x.get('type_raw'),translated=bool(x.get('localized_name') or name in LABELS),
                         timer=x.get('delete_timer'),delete_time=x.get('delete_time'),max_level=x.get('max_level'),
                         remove_on_scene_change=x.get('remove_on_scene_change'),positive=positive,feedback_excluded=positive,
                         configured=bool(rule),pulse_participates=pulse,ovc_participates=ovc,
                         pulse_channels=rule.get('pulse_channel','') if pulse else '',ovc_channels=rule.get('vibration_channel','') if ovc else ''))
    return rows

# Availability is distinct from actually seeing a callback in this game session.
CATALOG = [
    ('gallery_enter','进入图鉴','图鉴只读','实时场景身份进入 Gallery / Ga_；进入图鉴本身不代表正在播放。'),
    ('gallery_leave','退出图鉴','图鉴只读','实时场景离开图鉴范围；与读取信号失效分开记录。'),
    ('gallery_play_start','图鉴播放器开始','图鉴只读','图鉴中有效播放器正在播放，不依赖 HP、伤害回调或玩家对象可用。'),
    ('gallery_play_end','图鉴播放器结束 / 变化','图鉴只读','播放器停止、身份变化或读取失效；不把播放器名字当作唯一 CG 编号。'),
    ('gallery_play_state','图鉴播放状态变化','图鉴只读','区分游戏暂停、演出内部等待和时间停止；内部等待不等同手动暂停。'),
    ('gallery_signal_lost','图鉴信号失效','图鉴只读','心跳过期或会话不可用；不据此声称用户已退出图鉴。'),
    ('gallery_selection_change','图鉴选择片段','图鉴只读','独立读取怪物 ID 与 [1]/[2]/[3]；选择按钮先变化，实际片段可能稍后才载入。'),
    ('gallery_take_change','图鉴载入片段变化','图鉴只读','独立读取实际 Take 名称和身份，与选择按钮变化分开；返回列表后忽略残留指针。'),
    ('gallery_list','返回图鉴列表','图鉴只读','图鉴按钮面板关闭或片段索引为负数；保留的旧 Take 指针不表示仍在播放。'),
    ('gallery_controls','图鉴控制变化','图鉴只读','独立读取图鉴 Stop、慢放、DevMode 和隐藏界面的开关，不从演出内部等待推断手动暂停。'),
    ('same_hp_start','同值 HP 演出开始','组合判定','演出中重复的新鲜伤害通知，HP 前后相同；不使用普通快照、MP 变化或历史事件。'),
    ('same_hp_end','同值 HP 演出结束','组合判定','演出结束或同值通知断流；超时可在 CG 页调整。'),
    ('scripted_go','独立战败 CG · 1 HP','组合判定','GO 场景身份匹配、实时演出播放且显示 1 HP；允许没有玩家对象的 CG 使用死亡惩罚，不使用缓存异常状态。'),
    ('scripted_go_end','独立战败 CG 结束','组合判定','GO 演出停止、显示值不再为 1 HP、退出场景或心跳失效；停止这条演出反馈。'),
    ('one_hp_penalty','1 HP 锁血互动','组合判定','有效玩家处于抓取 / 演出，8 秒内两次独立的 1→1、扣血 0 伤害回调；沿用死亡惩罚策略。'),
    ('one_hp_end','1 HP 锁血互动结束','组合判定','恢复生命、离开互动或切换玩家 / 场景后清除判据；残留异常按独立策略处理。'),
    ('struggle_penalty','战败挣扎反馈','组合判定','实时玩家 HP=1、流程正在播放、可挣扎标志生效且阈值有效；不要求重复扣血回调，沿用 CG 策略。'),
    ('struggle_end','战败挣扎反馈结束','组合判定','成功回血、离开流程或玩家身份失效后停止这段惩罚；零血及独立 GO 按各自规则继续。'),
    ('recoverable_penalty','可恢复战败惩罚开始','已记录流程','猪棚挣扎、失败分支和战败转场；沿用战败渐强规则。'),
    ('regional_defeat','区域战败 CG','已记录流程','猪棚场景 167 Event / Main；正血量也继续战败反馈，返回正常游戏后停止。'),
    ('recoverable_recovery','战败挣脱恢复','已核验流程','猪棚 Continue / Success；停止战败持续反馈，挣脱本身不触发输出。'),
    ('flow_request','演出请求','流程回调','记录播放器对象名、类型和触发器；请求不等于已进入战败 CG。'),
    ('flow_label','流程阶段标签','流程回调','记录同步流程标签及执行组件；异步专用路径仍需对照。'),
    ('flow_stop','演出停止请求','流程回调','记录停止调用，真实演出结束以新鲜播放器状态为准。'),
    ('enemy_hit', '击中敌人', '伤害回调', '来源确认是当前玩家、敌人实际 HP 下降；记录实际伤害和剩余 HP。'),
    ('enemy_kill', '击杀敌人', '死亡回调关联', '敌人由存活进入死亡，并关联同一生命周期的玩家致命伤害；HP 归零本身不计击杀。'),
    ('enemy_damage', '敌人受伤（其他 / 未知来源）', '伤害回调', '实际 HP 下降，但来源无法确认是玩家；保留来源类名以便实测。'),
    ('enemy_death', '敌人死亡（归属未确认）', '死亡回调', '已进入死亡状态，但缺少玩家致命伤害证据；场景清理不计入。'),
    ('damage', '受伤通知', '直接回调', 'HP 前后值、HP / MP 消耗；−1 为未提供，不能当成回血。'),
    ('grab', '进入抓取', '直接回调', '敌人类名、是否替换抓取者。'),
    ('release', '抓取结束', '直接回调', '释放时敌人和 HP；相邻的重复释放回调合并。'),
    ('escape', '成功挣脱候选', '组合判定', '本次抓取内挣扎达标、随后脱困且存活；精确原因仍待回调验证。'),
    ('break', '服装破损 / 恢复', '状态边沿', 'broken 标志变化，并显示耐久；进入时已破损只显示当前状态。'),
    ('hp0', 'HP 归零', '状态边沿', '同一玩家由正数降至 0；不能据此认定 Game Over。'),
    ('heal', '生命恢复', '状态边沿', '同一玩家、同一场景 HP 上升；角色重绑不计回血。'),
    ('abnormal_add', '异常添加请求', '直接回调', '状态类型、请求等级；实际生效等级以顶部状态栏为准。'),
    ('abnormal_down', '异常降级请求', '直接回调', '已安装观察钩子；是否走这条路径需逐敌人验证。'),
    ('abnormal_remove', '异常移除请求', '直接回调', '已安装观察钩子；不将标题初始化清理计为玩家事件。'),
    ('abnormal', '生效异常 / 等级变化', '状态边沿', '对比实际异常列表，区分新增、移除和等级变化。'),
    ('pause', '暂停 / 恢复', '状态边沿', '游戏暂停标志变化；暂停期间继续显示插件心跳。'),
    ('scene', '场景切换 / 角色重绑', '状态边沿', '标识读取对象变化，不自动称为复活。'),
    ('release_reason', '精确释放原因', '待验证回调', 'setter 钩子已安装，本机构建尚未捕获；可能被内联绕过。'),
    ('gameover', 'Game Over 提示', '待验证回调', 'ShowGameOver 钩子已安装，尚未确认实机覆盖。'),
    ('gameover_label', '战败流程标签', '待验证回调', '可记录流程类型和重试参数；尚未确认实机覆盖。'),
]
TITLES = {key: name for key, name, _, _ in CATALOG}
CALLBACKS = {'damage_callback':'damage', 'bind_start_callback':'grab', 'bind_release_callback':'release',
             'abnormal_add_callback':'abnormal_add', 'abnormal_down_callback':'abnormal_down',
             'abnormal_remove_callback':'abnormal_remove', 'release_reason_callback':'release_reason',
             'show_gameover_callback':'gameover', 'gameover_label_callback':'gameover_label',
             'enemy_damage_callback':'enemy_damage','enemy_death_callback':'enemy_death',
             'flow_request_callback':'flow_request','flow_label_callback':'flow_label','flow_stop_callback':'flow_stop'}

class EventMonitor:
    def __init__(self):
        self.session = None
        self.rows = []
        self.counts = {}
        self._seen = set()
        self._previous = None
        self._grab = None
        self._release = None
        self._enemy_deaths = set()

    def begin_session(self, session):
        if self.session == session: return
        self.session = session
        self.rows.clear(); self.counts.clear(); self._seen.clear()
        self._previous = None; self._grab = None; self._release = None
        self._enemy_deaths.clear()

    def add(self, key, text, source, utc=None, history=False):
        stamp = parse_time(utc) if utc else datetime.now().astimezone()
        row = dict(key=key, title=TITLES.get(key, key), text=text, tag=source,
                   utc=stamp.astimezone(timezone.utc).isoformat(), time=stamp.astimezone().strftime('%H:%M:%S'),
                   history=history, rawCount=1)
        self.rows.append(row)
        self.rows.sort(key=lambda x: x['utc'], reverse=True)
        self.rows = self.rows[:120]
        self.counts[key] = self.counts.get(key, 0)+1
        return row

    def callback(self, e, type_names, history=False):
        if e.get('session') != self.session or (not e.get('player') and not str(e.get('event_type','')).startswith('flow_')): return None
        try:
            parse_time(e['utc'])
            if not isinstance(e.get('sequence'), int): return None
        except (ValueError,KeyError,TypeError,AttributeError): return None
        identity = (e.get('session'), e.get('sequence'))
        if identity in self._seen: return None
        self._seen.add(identity)
        kind = e.get('event_type'); key = CALLBACKS.get(kind)
        if not key: return None
        if kind == 'release_reason_callback' and not e.get('is_player_response'): return None
        if kind in ('enemy_damage_callback','enemy_death_callback'):
            return self.enemy_callback(e, history)
        # The native release method can recurse, emitting an empty-binder callback.
        if key == 'release':
            stamp = parse_time(e['utc']).timestamp()
            prior = self._release
            if prior and prior[0] == e.get('player') and 0 <= stamp-prior[1] < .15 and not e.get('binder'):
                prior[2]['rawCount'] += 1
                return None
        if key.startswith('flow_'):
            text=(str(e.get('label',''))+' · '+str(e.get('label_type',''))) if key=='flow_label' else str(e.get('name') or e.get('type') or '未命名播放器')
        elif key == 'damage':
            before, after = e.get('before_hp'), e.get('remain_hp')
            if isinstance(e.get('spend_mp'),int) and e['spend_mp']>0 and not (
                    isinstance(before,int) and isinstance(after,int) and before>after
                    or isinstance(e.get('spend_hp'),int) and e['spend_hp']>0):return None
            bits = [f'HP {before} → {after}']
            if before==0 and after==0 and isinstance(e.get('spend_hp'),int) and e['spend_hp']>0:
                bits.append('零血后受击请求（实际 HP 未再下降）')
            for field, label in [('spend_hp','HP 消耗'), ('spend_mp','MP 消耗')]:
                value = e.get(field)
                if isinstance(value, int) and value >= 0: bits.append(f'{label} {value}')
            if e.get('spend_mp', -1) >= 0: bits.append('剩余 MP '+str(e.get('remain_mp')))
            text = ' · '.join(bits)
        elif key == 'grab':
            self._release = None
            text = (e.get('binder') or '未知敌人')+(' · 替换抓取者' if e.get('swap') else '')
        elif key == 'release':
            text = (e.get('binder') or '未提供敌人')+' · HP '+str((e.get('hp') or {}).get('current', '—'))+' · 原因待确认'
        elif key.startswith('abnormal_'):
            name = type_names.get(str(e.get('type_raw')), '未知状态 #'+str(e.get('type_raw')))
            text = status_label(name)
            if 'requested_level' in e: text += ' · 请求等级 '+str(e['requested_level'])+'（非生效等级）'
        elif key == 'release_reason': text = str(e.get('reason', e.get('reason_raw')))+' · 仅为原因字段写入'
        elif key == 'gameover': text = '提示回调 · immediate='+str(e.get('immediate'))
        else: text = f"流程类型 {e.get('display_type')} · HP 控制 {e.get('hp_control_type')} · 重试时间 {e.get('has_retry_time')}"
        row = self.add(key, text, '插件回调', e.get('utc'), history)
        if key == 'release': self._release = (e.get('player'), parse_time(e['utc']).timestamp(), row)
        return row

    def enemy_callback(self, e, history):
        enemy=e.get('enemy_class') or '未知敌人'
        if isinstance(e.get('enemy_life'),int) and e['enemy_life']>0:enemy+=' #'+str(e['enemy_life'])
        if e['event_type']=='enemy_damage_callback':
            before,after=e.get('before_hp'),e.get('remain_hp')
            if not isinstance(before,int) or not isinstance(after,int) or not 0<=after<before:return None
            # Requested/overkill damage is not a substitute for actual HP loss.
            key='enemy_hit' if e.get('source_is_player') is True else 'enemy_damage'
            text=f'{enemy} · 伤害 {before-after} · HP {before} → {after}'
            if key=='enemy_damage':text+=' · 来源 '+(e.get('sender_class') or '未知')
            if after==0:text+=' · HP 归零'
            return self.add(key,text,'伤害回调',e['utc'],history)
        if e.get('not_defeat') is not False or e.get('dead_state_before')!=0 or e.get('dead_state_after') not in (1,2):return None
        life=e.get('enemy_life');target=e.get('enemy_object')
        if not isinstance(life,int) or life<=0 or not isinstance(target,int) or target<=0:return None
        identity=(self.session,target,life)
        if identity in self._enemy_deaths:return None
        self._enemy_deaths.add(identity)
        before=e.get('fatal_before_hp');damage=e.get('damage_id')
        credited=(e.get('source_is_player') is True and isinstance(before,int) and before>0
                  and e.get('fatal_after_hp')==0 and e.get('hp_current')==0
                  and isinstance(damage,int) and damage>0)
        key='enemy_kill' if credited else 'enemy_death'
        text=enemy+' · '+('死亡并保留尸体' if e['dead_state_after']==1 else '死亡并消失')
        if credited:text+=f' · 玩家致命伤害 HP {before} → 0'
        else:text+=' · 击杀归属未确认'
        return self.add(key,text,'死亡回调关联' if credited else '死亡回调',e['utc'],history)

    def snapshot(self, s):
        if s and scripted_go_penalty(s):
            previous=self._previous;self._previous=deepcopy(s);self._grab=None
            if current_penalty_class(previous or {})[0]!='scripted_go':
                return [self.add('scripted_go','GO 场景演出已确认 · 沿用死亡惩罚强度与波形','组合判定',s.get('utc'))]
            return []
        if not s or not s.get('valid'):
            ended=current_penalty_class(self._previous or {})[0]=='scripted_go'
            same_hp_ended=same_hp_flow(self._previous or {})
            self._previous = None; self._grab = None
            rows=[self.add('scripted_go_end','独立 GO 演出已结束 / 判据失效，停止该演出反馈','组合判定')] if ended else []
            if same_hp_ended:rows.append(self.add('same_hp_end','读取失效 / 玩家不可用，停止同值 HP 演出反馈','组合判定'))
            return rows
        p = self._previous
        if p and s.get('sample_id') == p.get('sample_id'): return []
        self._previous = deepcopy(s)
        if not p: return []
        rows = []
        def add(key, text, source='状态边沿'):
            row = self.add(key, text, source, s.get('utc')); rows.append(row)
        if same_hp_flow(s)!=same_hp_flow(p):add('same_hp_start' if same_hp_flow(s) else 'same_hp_end','同值 HP 演出已确认' if same_hp_flow(s) else '演出结束 / 同类通知已断流','组合判定')
        classification,label=current_penalty_class(s)
        if current_penalty_class(p)[0]=='scripted_go':add('scripted_go_end','独立 GO 演出已结束，后续互动重新按实时状态判断','组合判定')
        if current_penalty_class(p)[0]=='one_hp_penalty' and classification!='one_hp_penalty':
            add('one_hp_end','锁血互动已结束 / 判据已解除；死亡或残留异常仍按各自规则处理','组合判定')
        if current_penalty_class(p)[0]=='struggle_penalty' and classification!='struggle_penalty':
            add('struggle_end','挣扎流程已结束 / 判据已解除；零血或独立 GO 仍按各自规则处理','组合判定')
        if classification in ('recoverable_penalty','regional_defeat','recoverable_recovery','one_hp_penalty','struggle_penalty') and (classification,label)!=current_penalty_class(p):
            add(classification,label+' · '+('停止惩罚；挣脱本身不反馈' if classification=='recoverable_recovery' else '沿用战败渐强规则'),'已记录流程')
        if s.get('scene_id') != p.get('scene_id'):
            add('scene', str(p.get('scene', '—'))+' → '+str(s.get('scene', '—')))
        elif s.get('player') != p.get('player'):
            add('scene', '玩家对象重新绑定 · 重新建立数值基线')
        if (s.get('player'), s.get('scene_id'), s['hp']['max']) != (p.get('player'), p.get('scene_id'), p['hp']['max']):
            self._grab = None
            return rows
        if s.get('paused') != p.get('paused'): add('pause', '已暂停' if s.get('paused') else '继续游戏')
        if s.get('broken') != p.get('broken') and isinstance(s.get('broken'), bool) and isinstance(p.get('broken'), bool):
            add('break', '衣服由完整变为破损' if s['broken'] else '衣服由破损恢复完整')
        before = {x['name']:x.get('level') for x in p.get('abnormals', [])}
        after = {x['name']:x.get('level') for x in s.get('abnormals', [])}
        for name in sorted(before.keys() | after.keys()):
            if name not in before: add('abnormal', f'新增 {status_label(name)} Lv.{after[name]}')
            elif name not in after: add('abnormal', f'移除 {status_label(name)}（原 Lv.{before[name]}）')
            elif before[name] != after[name]: add('abnormal', f'{status_label(name)} Lv.{before[name]} → Lv.{after[name]}')
        # Do not infer resource changes across pauses, load gaps or actor replacement.
        if s.get('paused') or p.get('paused') or s.get('time_scale') != 1 or p.get('time_scale') != 1:
            self._grab = None
            return rows
        if s['hp']['current'] == 0 and p['hp']['current'] > 0: add('hp0', 'HP 归零 · 战败流程仍待确认')
        if s['hp']['current'] > p['hp']['current']: add('heal', f"HP {p['hp']['current']} → {s['hp']['current']}")
        if s.get('bound') and not p.get('bound'): self._grab = {'reached':False}
        if self._grab:
            g = s.get('gacha') or {}; value, threshold = g.get('value'), g.get('threshold')
            if isinstance(value, (int,float)) and isinstance(threshold, (int,float)) and threshold > 0 and value >= threshold: self._grab['reached'] = True
            if p.get('bound') and not s.get('bound'):
                if self._grab['reached'] and s['hp']['current'] > 0: add('escape', '本次挣扎达标后存活脱困 · 精确原因未确认', '组合判定')
                self._grab = None
        return rows

    def catalog(self,combat_hooks=None,flow_hooks=None):
        rows=[]
        hooks=combat_hooks or {}
        for k,n,s,d in CATALOG:
            count=self.counts.get(k,0)
            installed=(hooks.get('damage') and (hooks.get('death_exists') or hooks.get('death_remove'))) if k=='enemy_kill' else (hooks.get('death_exists') or hooks.get('death_remove')) if k=='enemy_death' else hooks.get('damage')
            status=f'本次会话已记录 {count}' if count else '待实机触发' if '回调' in s else '等待新状态变化'
            if k.startswith('enemy_') and not installed and not count:status='等待 0.2.0 插件钩子加载'
            if k.startswith('flow_') and not count:
                fh=flow_hooks or {};available=fh.get('request') if k=='flow_request' else fh.get('stop') if k=='flow_stop' else fh.get('receiver_label') or fh.get('execution_label')
                if not available:status='等待 0.3.0 流程钩子加载'
            rows.append(dict(key=k,name=n,source=s,detail=d,count=count,status=status))
        return rows
