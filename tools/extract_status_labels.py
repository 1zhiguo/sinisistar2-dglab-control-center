"""Extract matching status labels from the supplied build's Chinese localization.

Only exact LocalizeID name matches are used; unmatched enums retain their names.
"""
import json, re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
dump = (root/'.analysis/il2cpp-v1.3.1/dump.cs').read_text(encoding='utf-8')
strings = json.loads((root/'SiNiSistar2_v1_3_1/WIN/Mod/Localize/Sample_ZH_CN/LocalizeTable.json').read_text(encoding='utf-8'))['m_Array']
ids = {k: int(v) for k, v in re.findall(r'public const LocalizeID (ID_Ab_\w+) = (\d+);', dump)}
enums = json.loads((root/'src/sinisistar_dglab/assets/types.json').read_text())['AbnormalType']
target = root/'src/sinisistar_dglab/assets/status-labels.json'
prior=json.loads(target.read_text(encoding='utf-8')) if target.exists() else {}
labels = {}
for name in enums.values():
    key = 'ID_Ab_'+name
    if name == 'Defilement': key = 'ID_Ab_DefilementLv1'
    if key in ids:
        label = strings[ids[key]-1]
        # Level is displayed separately from the game's current LevelRp value.
        label = re.sub(r'\s+(?:\d+|■)/\d+$', '', label)
        labels[name] = {'label': label, 'localize_id': ids[key]}
    elif prior.get(name,{}).get('translation_source')=='internal':labels[name]=prior[name]
target = root/'src/sinisistar_dglab/assets/status-labels.json'
target.write_text(json.dumps(labels, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
runtime_names={str(value): strings[value-1] for key,value in ids.items() if not re.search(r'_(?:Desc|Log)',key,re.I)}
(target.parent/'status-name-ids.json').write_text(json.dumps(runtime_names,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(f'{len(labels)} labels written to {target}; internally translated names retain their source marker')
