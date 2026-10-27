"""Pin dormant treatment scene roots and their serialized treatment actions."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'.analysis/unitypy'))
import UnityPy
DEFINITIONS={
    'BreastCure':'哈妮亚治疗 · 胀乳 / 泌乳',
    'BreastCure_Leech':'医用水蛭治疗 · 胀乳 / 泌乳',
    'Cure_Parasite':'寄生治疗 · 互动过程',
    'Cure_Parasite_Go':'寄生治疗 · 失败后续',
    'Pregnant_Op':'妊娠治疗 · 开始流程',
    'Pregnant_End':'妊娠治疗 · 后续流程'}
def main():
    bundle='44df1100e313fc2ff14ca5974867b'
    path=ROOT/'artifacts/research/monster-textures/decoded'/bundle
    env=UnityPy.load(path.read_bytes());objects=list(env.objects)
    def hierarchy(g):
        t=next(e.component.read() for e in g.m_Component if e.component.type.name=='Transform');names=[g.m_Name]
        while t.m_Father:t=t.m_Father.read();names.append(t.m_GameObject.read().m_Name)
        return '/'.join(reversed(names))
    roots=[];actions=[]
    for o in objects:
        if o.type.name=='GameObject':
            g=o.read()
            if g.m_Name in DEFINITIONS:
                p=hierarchy(g)
                if p=='Root/Event/'+g.m_Name:
                    assert not g.m_IsActive
                    roots.append(dict(key=g.m_Name,name=DEFINITIONS[g.m_Name],scene_id=7,path='/'+p,default_active=False,game_object_id=o.path_id,
                        evidence='静态场景激活节点；新版插件实时起止仍待实测'))
        elif o.type.name=='MonoBehaviour':
            m=o.read(check_read=False);name=m.m_Script.read().m_ClassName
            if name not in ('AllActiveLabel','AbnormalConditionLabel'):continue
            p=hierarchy(m.m_GameObject.read())
            if '/Chose : Cure/' not in p:continue
            actions.append(dict(path=p,component=name,parameters=o.read_typetree().get('m_Parameters',[])))
    assert len(roots)==6
    data=dict(schema=1,game_version='1.3.1',bundle=bundle,decoded_bundle_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        roots=sorted(roots,key=lambda x:list(DEFINITIONS).index(x['key'])),actions=actions,
        notes='精确匹配场景和原本关闭的治疗根节点；Sequence、HP 刷新、MP 下降、普通对话和回想不作为授权依据。')
    out=ROOT/'artifacts/treatment-validation/static-treatment-flows.json';out.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(roots=len(roots),serialized_actions=len(actions))))
if __name__=='__main__':main()
