"""Copy only the clothed default player layers for a small decorative UI walk.

Development-only UnityPy dependency. Reads the already audited local copies;
does not launch the game, edit game assets, or reproduce gameplay animations.
"""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.analysis/unitypy'))
import UnityPy
from PIL import Image

def main():
    source=ROOT/'artifacts/research/monster-textures/decoded'
    player_bundle='104a8d959d53eb7af4d1c247ed053'
    scene_bundle='2784cfee5c0182abdc119a819a1eb'
    env=UnityPy.load((source/player_bundle).read_bytes())
    sprites={o.path_id:o for o in env.objects if o.type.name=='Sprite'}
    scene=UnityPy.load((source/scene_bundle).read_bytes())
    go=next(o.read() for o in scene.objects if o.type.name=='GameObject' and o.path_id==769)
    transform=next(c.component.read() for c in go.m_Component if c.component.type.name=='Transform')
    rig=next(t.read() for t in transform.m_Children if t.read().m_GameObject.read().m_Name=='Root')
    target=ROOT/'src/sinisistar_dglab/assets/lilia';target.mkdir(exist_ok=True)
    parts=[];audit=[]
    for pointer in rig.m_Children:
        t=pointer.read();g=t.m_GameObject.read()
        for component in g.m_Component:
            if component.component.type.name!='SpriteRenderer':continue
            renderer=component.component.read()
            if not g.m_IsActive or not renderer.m_Enabled or not renderer.m_Sprite:continue
            if renderer.m_Sprite.m_PathID not in sprites:continue
            sprite=sprites[renderer.m_Sprite.m_PathID].read()
            # No broken, alternate body state, weapon or scene/CG images.
            assert sprite.m_Name in {n+'_000' for n in ('head','hair','body','chest','skirt','skirt2','arm_left','arm_right','shoulder_left','shoulder_right','leg_left','leg_right','foot_left','foot_right')},sprite.m_Name
            image=sprite.image.convert('RGBA');crop=image.getbbox()
            if not crop:continue
            offset=sprite.m_RD.textureRectOffset
            x=90+offset.x-sprite.m_Pivot.x*sprite.m_Rect.width+t.m_LocalPosition.x*100
            y=90-(offset.y-sprite.m_Pivot.y*sprite.m_Rect.height+image.height)-t.m_LocalPosition.y*100
            x+=crop[0];y+=crop[1];image=image.crop(crop);image.save(target/(g.m_Name+'.png'),optimize=True)
            parts.append(dict(name=g.m_Name,file=g.m_Name+'.png',x=round(x,4),y=round(y,4),width=image.width,height=image.height,z=renderer.m_SortingOrder))
            audit.append(dict(node=g.m_Name,sprite=sprite.m_Name,path_id=renderer.m_Sprite.m_PathID,sha256=hashlib.sha256((target/(g.m_Name+'.png')).read_bytes()).hexdigest()))
    assert len(parts)==13
    # The default Skirt2 layer is fully transparent and is not distributed.
    if (target/'Skirt2.png').exists():(target/'Skirt2.png').unlink()
    parts.sort(key=lambda p:p['z'])
    bounds=(min(p['x'] for p in parts),min(p['y'] for p in parts),max(p['x']+p['width'] for p in parts),max(p['y']+p['height'] for p in parts))
    for p in parts:p['x']=round(p['x']-bounds[0]+10,4);p['y']=round(p['y']-bounds[1]+4,4)
    width=round(bounds[2]-bounds[0]+20);height=round(bounds[3]-bounds[1]+8)
    (target/'parts.js').write_text('/* Clothed default player layers; decorative walk is authored in QML. */\nvar width='+str(width)+';\nvar height='+str(height)+';\nvar parts='+json.dumps(parts,separators=(',',':'))+';\n',encoding='utf8')
    (target/'source.json').write_text(json.dumps(dict(game='SiNiSistar2 v1.3.1',scene_bundle=scene_bundle,player_bundle=player_bundle,root_game_object=769,scope='13 visible clothed default player layers, UI decorative animation only',parts=audit),indent=2),encoding='utf8')
    preview=Image.new('RGBA',(width,height))
    for p in parts:preview.alpha_composite(Image.open(target/p['file']),dest=(round(p['x']),round(p['y'])))
    out=ROOT/'artifacts/ui/lilia-composite.png';preview.resize((width*4,height*4),Image.Resampling.NEAREST).save(out)
    print(json.dumps(dict(parts=len(parts),width=width,height=height,bytes=sum(p.stat().st_size for p in target.iterdir())),indent=2))

if __name__=='__main__':main()
