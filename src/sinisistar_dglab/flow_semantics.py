"""Evidence-labelled flow descriptions and review intentions, never output authority.

The game's identifiers are retained. Chinese descriptions are our interpretation;
matching a task name does not prove an executed phase, its duration or its ending.
"""
from copy import deepcopy
import csv
import json
from pathlib import Path

DECISIONS={'undecided':'待决定','ramp':'希望渐强','observe':'仅观察意向','skip':'不纳入计划'}
ENEMIES={
    'Zombie':'僵尸','ZombieTomb':'墓地僵尸','SwampLeech':'沼泽水蛭',
    'SwampLeech_Adult':'成年沼泽水蛭','LeechMan':'水蛭人','LeechGluttony':'贪食水蛭',
    'PigBG':'背景猪','PigDining':'进食中的猪','PigParasite':'寄生猪',
    'DemiHumanBoss':'亚人首领','DemiHumanL':'大型亚人','DemiHumanM':'中型亚人',
    'DemiHumanS':'小型亚人','DemiHumanS_Cart':'推车亚人',
    'Frog_L':'大蛙','Frog_M':'中型蛙','Rat':'鼠','JellyFish':'水母',
    'FlyBug':'飞虫','FlyBugRequiem':'飞虫变体','SpiderHuntsman':'猎蛛',
    'SpiderSuspension':'悬吊蜘蛛','MeatBoss':'血肉首领','MeatCeiling':'血肉天花板',
    'MeatTentacleCloudy':'血肉触手（Cloudy）','MeatTentacleWall':'墙壁触手',
    'MeatWorm':'血肉蠕虫','MeatWormVore':'吞噬蠕虫','MeatWombBaby':'血肉幼体',
    'ParasiteBullet':'寄生弹体','ParasiteTentacle':'寄生触手','PictureFrameBig':'大型画框',
    'PriestSlime':'神职史莱姆','PriestVillage':'村庄神职者',
    'BloodMagicHand':'血魔法之手','OnlyHoldEnemy':'仅抓取敌人（通用类）',
    'VillagerAges':'年长村民','VillagerFat':'肥胖村民','VillagerMale':'男性村民',
    'VillagerMiddleMale':'中年男性村民','VillagerMiddleMaleParasiteL':'寄生村民变体',
    'VillagerRegion':'村民（Region）','SlugM':'中型蛞蝓','SlugS':'小型蛞蝓',
    'SnailBrain':'脑蜗牛','SnailBrainS':'小型脑蜗牛','SnailBrainS_Ground':'地面脑蜗牛',
    'BolaBindExtension':'绳索束缚扩展（组件）','DebugScareLelia':'调试抓取类',
}

def enemy_name(name):
    return ENEMIES.get(name,name)

def symbol_meaning(symbol):
    """Translate symbol roles conservatively, retaining the complete raw symbol."""
    s=symbol.lower()
    if 'deadnotdefeat' in s:return '死亡但非战败（名称含义）'
    if 'release' in s or 'realse' in s:return '解除 / 释放'
    if 'cancel' in s:return '抓取取消 / 中断'
    if 'joinedhold' in s or 'otherhold' in s or 'otherbind' in s:return '其他参与者 / 协同受制'
    if 'hold' in s:
        if 'start' in s:return '抓取开始'
        if 'end' in s:return '抓取结束相关（未必已恢复控制）'
        if 'loop' in s:return '抓取循环'
        if 'attack' in s:return '抓取中的攻击'
        return '维持抓取 / 受制'
    if 'eat' in s or 'vore' in s:return '吞食相关'
    if 'bind' in s:return '束缚相关'
    if 'insert' in s:return '插入阶段相关'
    if 'threat' in s:return '威胁动作'
    if 'punish' in s:return '惩罚相关'
    return '相关动作符号 · 含义待核验'

def describe_runtime(row):
    r=deepcopy(row);scene_id=group=name=kind=None
    try:
        identity=json.loads(r['key'])
        if len(identity)==4:scene_id,group,name,kind=identity
    except (ValueError,TypeError,KeyError):pass
    category='含义待确认';family='unknown';title=r.get('name','未命名流程')
    evidence='实机已出现；中文解释待核验';boundary='尚无可靠的开始 / 结束语义。'
    if scene_id=='capture':
        family='zero_hp_capture';category='零血受制';title=enemy_name(name)+' · 零血仍被抓取'
        evidence='实机组合信号：HP=0、仍受制、抓取来源可读；不是精确动画身份'
        boundary='开始：零血且仍被抓取；结束：复活 / 脱离 / 状态失效；动画变体未区分。'
    elif scene_id==166 and group=='Continue' and name in ('StartGacha','Success') and kind=='HierarchyEventPlayer':
        family='recoverable';category='可恢复战败' if name=='StartGacha' else '恢复 / 挣脱'
        title='猪棚 · 战败后挣扎' if name=='StartGacha' else '猪棚 · 成功挣脱恢复'
        evidence='实机已对照；场景 + 分组 + 播放器类型精确匹配'
        boundary='StartGacha 开始惩罚 → Success 停止；恢复正血量不等于已脱离。'
    elif scene_id==166 and group=='BossAppear':
        family='ordinary';category='登场 / 剧情';title='猪棚 · 首领登场'
        evidence='实机对照：发生在战斗前，与战败后 Continue 分组不同'
        boundary='入场演出，不作为战败惩罚起点。'
    elif scene_id==166 and group=='Continue' and name in ('Failed Breast','Failed SuperBreast','ToGoScene','EnemyDeadForSuperBreast'):
        family='recoverable_branch';category='战败失败 / 转场分支'
        title={'Failed Breast':'猪棚 · 失败分支（Breast）','Failed SuperBreast':'猪棚 · 失败分支（SuperBreast）',
               'ToGoScene':'猪棚 · 转入 GO 场景','EnemyDeadForSuperBreast':'猪棚 · 敌人死亡条件后续（SuperBreast）'}[name]
        evidence='实机播放器已出现；中文分支含义由名称解释，触发条件与结束待核验'
        boundary='已记录 Failed Breast → Failed SuperBreast → ToGoScene → 场景 167 Main 的先后；不保证每次必经全部分支。'
        if name=='EnemyDeadForSuperBreast':
            category='条件后续 · 非玩家死亡'
            boundary='发生在 Success 之后，且有同名请求回调；EnemyDead 是敌人死亡，不能当作玩家死亡起点。'
    elif scene_id==167 and name=='Main' and kind=='HierarchyEventPlayer':
        family='regional_go';category='区域战败 GO'
        title='猪棚 · 独立 GO 场景主流程'
        evidence='实机场景 167 Main 已出现，BootGO1 请求已记录；结束边界待核验'
        boundary='位于场景 166 的 ToGoScene 之后，后续回到 166；完整自然时长和主动跳过尚未区分。'
    elif (scene_id==28 and group=='LeechBossEvent' and name in ('Start','Died')) or scene_id in (29,30):
        family='boss_defeat';category='Boss 战败链'
        title={29:'沼泽 Boss · GO1 阶段',30:'沼泽 Boss · GO2 阶段'}.get(scene_id,
              '沼泽 Boss · 战败开始' if name=='Start' else '沼泽 Boss · Died 阶段')
        evidence='实机时间线已对照；跨场景战败链，最终复活边界待核验'
        boundary='Start → Died → GO1 → GO2；无 GameOver 回调，不能仅靠 HP 或 Died 名称覆盖整段。'
    elif name in ('BossDead','AfterBossDead'):
        family='ordinary';category='胜利相关';title='Boss 被击败' if name=='BossDead' else 'Boss 击败后的后续演出'
        evidence='名称推断 + 实机出现；不等于玩家战败'
        boundary='BossDead / AfterBossDead 不作为玩家死亡惩罚起点。'
    elif name=='SaveDirector':
        family='ordinary';category='存档相关';title='存档点演出'
        evidence='名称推断 + 实机出现；尚未逐段对照';boundary='默认不纳入战败流程。'
    elif isinstance(name,str) and 'SwampLeechEggGO' in name:
        family='egg_go';category='状态 / GO 候选';title='水蛭卵相关 GO 流程 · 待核验'
        evidence='名称推断 + 实机出现；GO 不保证永久死亡'
        boundary='可能与状态后果相关；是否恢复、循环、何时结束仍需对照。'
    elif group=='Continue' and name=='StartGacha':
        family='recoverable_candidate';category='可恢复战败候选';title='战败后挣扎候选'
        evidence='同名结构推断；非猪棚身份尚未核验';boundary='需要配对恢复流程；同名不自动授权输出。'
    elif isinstance(name,str) and 'No Item' in name:
        category='条件分支';title='无道具分支 · '+name
        evidence='名称推断 + 实机出现；触发条件尚未对照'
    elif scene_id==165 and name in ('Main','Play Animation','WaitAndResume'):
        family='condition_followup';category='条件后续 / 恢复候选'
        title={'Main':'猪棚入口 · 条件后续主流程','Play Animation':'猪棚入口 · 动作播放子流程',
               'WaitAndResume':'猪棚入口 · 等待 / 恢复子流程'}[name]
        evidence='实机播放器已出现；同场景记录 RemoveBreastSuperBoot / RemoveBreastCollision 请求，子流程含义待核验'
        boundary='发生在返回入口时；不要因 Main / WaitAndResume 名称就认定为惩罚或已恢复自由操作。'
    r.update(semantic_title=title,semantic_category=category,semantic_family=family,
             semantic_evidence=evidence,semantic_boundary=boundary,
             semantic_source='游戏原始字段 + 人工对照 / 名称解释',
             semantic_symbols='\n'.join(r.get('labels',[])),
             semantic_limit='标签可能广播给多个组件，不代表每个动作都实际执行；时长不由名称确定。')
    return r

def describe_static(row):
    r=deepcopy(row);enemy=r['enemy']
    symbols=[('状态',x['name']) for x in r.get('states',[])]+[('任务',x) for x in r.get('tasks',[])]+[
        ('动画',x['name']) for x in r.get('animations',[])]+[('动画字段',x) for x in r.get('animation_fields',[])]
    roles=[]
    for _,symbol in symbols:
        role=symbol_meaning(symbol)
        if role not in roles:roles.append(role)
    r.update(key='static:'+enemy,name=enemy+' · 静态候选',scene='v1.3.1 静态定义',kind='static_candidate',
             semantic_title=enemy_name(enemy)+' · 抓取相关候选',semantic_category='敌人抓取候选',
             semantic_family='static_capture',semantic_evidence='仅静态符号；未核验触发、结束和实际动画',
             semantic_boundary='可见角色：'+'、'.join(roles)+'。任务定义不证明运行时顺序。',
             semantic_source='.analysis/il2cpp-v1.3.1/dump.cs:'+str(r.get('line','')),
             semantic_symbols='\n'.join(f'{role} · {symbol} → {symbol_meaning(symbol)}' for role,symbol in symbols),
             semantic_limit='中文敌人名为工作译名；候选家族不是 CG 数量，不能据此预测演出时长。',
             labels=[symbol for _,symbol in symbols])
    return r

SCENE_AREAS={
    'Dungeon_Cathedral_Hall':'圣堂大厅','Dungeon_Cave':'亚人洞窟','Dungeon_Sewage':'下水道',
    'Dungeon_Swamp':'沼泽','Dungeon_Village':'村庄','Road_TreeBoss':'街道树木首领',
    'Road_SpiderBoss':'街道蜘蛛首领','Road_2_2_Livestock':'猪棚','Road_2_1':'街道 2-1',
    'Road_TownUnder':'城镇地下','Road_Mountain':'山道','Road_Swamp':'沼泽入口',
    'Road':'街道','Town_Alley_House2':'城镇小巷房屋','Monastery_Raid':'修道院袭击',
    'Dream_Slug_Villager':'梦境 / 蛞蝓村民',
}

def describe_scene(row,runtime):
    r=deepcopy(row);name=r['scene'];sid=r['scene_id']
    area=next((v for k,v in SCENE_AREAS.items() if name.startswith(k)),name)
    seen=any(_scene_id(x.get('key',''))==sid for x in runtime)
    r.update(key='scene:'+str(sid),name=name,kind='static_scene',semantic_title=area+' · '+name.split('_')[-1]+' 场景候选',
        semantic_category='Boss GO 场景候选' if 'Boss' in name else '区域 GO 场景候选',semantic_family='static_scene',
        semantic_evidence='SceneID 枚举中的 GO 命名；'+('已在实机目录出现，仍需核验结束边界' if seen else '未在当前实机目录出现'),
        semantic_boundary='GO 场景名可作为定位线索；是否可挣脱、是否跨场景、何时复活均不能仅由名称确定。',
        semantic_source='.analysis/il2cpp-v1.3.1/dump.cs:'+str(r.get('line','')),
        semantic_symbols='SceneID '+name+' = '+str(sid),semantic_limit='候选地图不是一段已验证 CG；编号分支不等于自然播放顺序。',labels=[])
    return r

def _scene_id(key):
    try:
        identity=json.loads(key)
        return identity[1] if identity[0]=='capture' else identity[0]
    except (ValueError,IndexError,TypeError):return None

class FlowReview:
    """Separate review plan: marking a preference never changes live device output."""
    def __init__(self,path):
        self.path=Path(path);self.choices={}
        try:
            raw=json.loads(self.path.read_text(encoding='utf-8'))
            if isinstance(raw,dict):self.choices={k:v for k,v in raw.items() if isinstance(k,str) and isinstance(v,str) and v in DECISIONS}
        except (ValueError,OSError):pass

    def rows(self,runtime,static,scenes=()):
        rows=[describe_runtime(r) for r in runtime]+[describe_scene(r,runtime) for r in scenes]+[describe_static(r) for r in static]
        for r in rows:
            r['review_decision']=self.choices.get(r['key'],'undecided')
            r['review_label']=DECISIONS[r['review_decision']]
        return rows

    def choose(self,keys,decision,known):
        if decision not in DECISIONS:return 0
        chosen=set(keys)&set(known)
        for key in chosen:
            if decision=='undecided':self.choices.pop(key,None)
            else:self.choices[key]=decision
        if chosen:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps(self.choices,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(self.path)
        return len(chosen)

    def export(self,rows,target):
        target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
        fields=[('semantic_title','中文含义'),('semantic_category','分类'),('review_label','联动意向'),('scene','场景'),
                ('key','原始身份'),('semantic_evidence','依据与可信度'),('semantic_boundary','起止与流程'),
                ('semantic_symbols','标签或任务'),('semantic_limit','限制')]
        with target.open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.writer(f);writer.writerow([label for _,label in fields])
            writer.writerows([[r.get(key,'') for key,_ in fields] for r in rows])
        return target
