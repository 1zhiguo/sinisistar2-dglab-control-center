"""Flow evidence for playerless 1-HP GO maps, not a cached-player bypass.

The build's GO SceneID catalog supplies map context. Runtime playing state,
matching identity and the 1-HP display are all required; ordinary maps and
inactive / stale / loading flows remain gated by the output adapters.
"""
import json
from pathlib import Path
try:
    GO_SCENES={r['scene_id']:r['scene'] for r in json.loads((Path(__file__).parent/'assets/flow-scene-candidates.json').read_text(encoding='utf-8'))['candidates']}
except (OSError,ValueError,KeyError):GO_SCENES={}

def scripted_go_penalty(s):
    f=s.get('flow') or {};hp=s.get('hp') or {};scene=s.get('scene_id')
    return (s.get('source')=='bepinex' and s.get('live') is True and not s.get('loading')
            and type(s.get('pid')) is int and s['pid']>0 and isinstance(s.get('session'),str) and bool(s['session'])
            and type(scene) is int and scene in GO_SCENES and s.get('scene')==GO_SCENES[scene]
            and type(hp.get('current')) is int and hp['current']==1 and type(hp.get('max')) is int and hp['max']>0
            and f.get('valid') is True and f.get('playing') is True
            and f.get('type') in ('HierarchyEventPlayer','PlayableDirectorPlayer') and bool(f.get('name')))

def scripted_go_identity(s):
    if scripted_go_penalty(s):return (s.get('session'),s.get('pid'),'scripted-go')
    return None
