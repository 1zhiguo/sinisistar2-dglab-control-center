"""Build-specific pigpen defeat chain; unrelated candidate names cannot authorize."""
from .locked_hp import locked_hp_penalty
from .scripted_go import scripted_go_penalty

PIGPEN_BRANCHES={
    'StartGacha':'猪棚 · 战败挣扎',
    'Failed Breast':'猪棚 · 挣扎失败分支',
    'Failed SuperBreast':'猪棚 · 挣扎失败后续',
    'ToGoScene':'猪棚 · 战败转场',
}

def flow_classification(scene,flow):
    identity=(scene,flow.get('group'),flow.get('name'),flow.get('type'))
    if scene==166 and flow.get('group')=='Continue' and flow.get('type')=='HierarchyEventPlayer' and flow.get('name') in PIGPEN_BRANCHES:
        return 'recoverable_penalty',PIGPEN_BRANCHES[flow['name']]
    if identity==(167,'Event','Main','HierarchyEventPlayer'):
        return 'regional_defeat','猪棚 · 战败 CG 主流程'
    if identity==(166,'Continue','Success','HierarchyEventPlayer'):
        return 'recoverable_recovery','猪棚 · 挣脱恢复'
    if flow.get('group')=='Continue' and flow.get('name')=='StartGacha':
        return 'recoverable_candidate','可恢复战败候选 · 待核验'
    return '',''

def current_penalty_class(s):
    f=s.get('flow') or {}
    known=flow_classification(s.get('scene_id'),f)
    if s.get('valid') and f.get('valid') and f.get('playing') and not s.get('loading') and known[0]=='recoverable_recovery':return known
    if scripted_go_penalty(s):return 'scripted_go','独立战败 CG · 1 HP 演出流程'
    if locked_hp_penalty(s) and not s.get('loading'):
        if (s.get('feedback_evidence') or {}).get('source')=='live_struggle':return 'struggle_penalty','战败挣扎 · 1 HP 可挣脱互动'
        return 'one_hp_penalty','锁血互动 · 1 HP 持续受伤'
    if not (s.get('valid') and f.get('valid') and f.get('playing')) or s.get('loading'):return '',''
    return known

def pigpen_penalty_identity(s):
    # Raw identity survives a loading snapshot, but never grants output by itself.
    if flow_classification(s.get('scene_id'),s.get('flow') or {})[0] in ('recoverable_penalty','regional_defeat'):
        return (s.get('session'),s.get('pid'),'pigpen-defeat')
    return None

def recoverable_penalty(s):return current_penalty_class(s)[0] in ('recoverable_penalty','regional_defeat','one_hp_penalty','struggle_penalty','scripted_go')
def recoverable_recovery(s):return current_penalty_class(s)[0]=='recoverable_recovery'
