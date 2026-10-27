"""Resolve audited enemy renderer/animation references into deduplicated previews."""
from pathlib import Path
import collections,gc,gzip,hashlib,json,re,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.analysis/unitypy'));sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'tools'))
import UnityPy
from UnityPy.helpers.MeshHelper import MeshHandler
from PIL import Image
from build_monster_catalog import NAMES,translated,normalize,category
from audit_monster_resources import ref

OUT=ROOT/'artifacts/research/monster-audit';DECODED=ROOT/'artifacts/research/monster-textures/decoded'

NAMES.update({'Rat':'鼠','Parasite2':'寄生体','Enenuth':'埃涅努斯 · 潜伏体','MeatBall':'血肉球','MeatWombBaby':'血肉幼体',
 'MiscarriedFetus':'胎儿残体','MeatEggMass':'血肉卵团','VillagerFemale':'女性村民','VillagerFemaleParasite':'寄生女性村民',
 'PriestRod_H':'持杖神职者 · H','PriestRod_C_Air':'浮空持杖神职者','Priest_Scythe':'持镰神职者','PriestSlimeHuman':'神职史莱姆 · 人形',
 'SnailBrain_WeakPoint':'脑蜗牛 · 弱点','Ga_Snail':'回想蜗牛','TreeBossIvy':'树木首领 · 藤蔓','SeereEye':'塞雷 · 眼部',
 'SpiderEgg':'蜘蛛卵','SpiderS':'小蜘蛛','FlyBug_Human':'人形飞虫','MeatWall_BurstChild':'血肉墙 · 子体',
 'PriestBossEye':'神职首领 · 眼部','Mother':'母体','MeatWomb1':'血肉子宫 · 生成体','RegionPart':'Region · 部件',
 'Babel_Dark':'暗色博贝尔','SistarTentacle':'触手修女（Sistar）','SlugW':'白色蛞蝓','NoActionEnemy':'无动作敌人 · 弱点',
 'Cluster2':'触手簇 · 第二部件','ClusterBase':'触手簇 · 基座','LeechBabySplash':'幼生水蛭 · 飞溅子体'})

def main():
    records=[json.loads(gzip.decompress(p.read_bytes())) for p in (OUT/'bundles').glob('*.json.gz')]
    sprites={};asset_owner={};enemy_rows=[]
    for r in records:
        for asset in r['assets']:asset_owner[asset['name'].lower()]=r['bundle']
        for s in r['sprites']:sprites[(s['asset'].lower(),s['id'])]=dict(s,bundle=r['bundle'])
        enemy_rows.extend(r['enemies'])
    key=lambda pointer:(pointer[0].lower(),pointer[1])
    player_assets={key(renderer['sprite'])[0] for e in enemy_rows for renderer in e['renderers'] if re.search(r'/(?:Lelia|Player)(?:/|$)',renderer['node'],re.I)}
    catalog=json.loads(gzip.decompress((ROOT/'src/sinisistar_dglab/assets/monster-catalog.json.gz').read_bytes()))['families']
    name_table=json.loads((ROOT/'artifacts/research/monster-textures/resource-name-table.json').read_text(encoding='utf8'))
    baseline_keys={re.search(r'/Enemy/([^/]+)/',r['m_VirtualPath'])[1] for r in name_table['m_EnemyAssetBundleInfoList']['m_AssetBundleInfoList']}|{'PigBG','PigParasite','VillagerMiddleMale_A_Pig'}
    catalog=[r for r in catalog if r['key'] in baseline_keys]
    known={normalize(r['key']):r['key'] for r in catalog}
    old_profile=json.loads(gzip.decompress((ROOT/'src/sinisistar_dglab/assets/monster-extract-profile.json.gz').read_bytes()))
    frame_family={f['id']:r['key'] for r in catalog for g in r['groups'] for f in g['frames'] if f['path'].startswith('Design/')}
    old_hashes=collections.defaultdict(set)
    for spec in old_profile['sprites']:
        if spec['id'] in frame_family:old_hashes[frame_family[spec['id']]].add(spec['rgba_sha256'])
    aliases={'MeatWorm':'MeatWorm1','SwampLeech':'Leech_Swanp','SwampLeech_Adult':'Leech_Adult',
             'PictureFrame':'PictureEnemy','PictureFrameBig':'PictureEnemy_Big','Cluster1':'MeatTentacleCluster','Cluster3':'MeatTentacleCluster'}
    def family(e):
        cls=e['class_name'];root=re.sub(r'\s*\(\d+\)$','',e['go_name']);root=re.sub(r'^(?:Enemy|Ememy)','',root)
        if cls=='OnlyHoldEnemy':return known.get(normalize(root),root)
        return known.get(normalize(cls)) or aliases.get(cls) or known.get(normalize(root)) or cls
    clip_keys={key(c) for e in enemy_rows for c in e['clips']};clip_bundles=collections.defaultdict(set)
    for identity in clip_keys:clip_bundles[asset_owner[identity[0]]].add(identity)
    clips={};errors=[]
    for bundle,wanted in clip_bundles.items():
        env=UnityPy.load((DECODED/bundle).read_bytes())
        for obj in env.objects:
            identity=(obj.assets_file.name.lower(),obj.path_id)
            if identity not in wanted:continue
            try:
                clip=obj.read();constant=clip.m_ClipBindingConstant
                pointers=constant.pptrCurveMapping if constant else []
                clips[identity]=dict(name=clip.m_Name,refs=[key(ref(p)) for p in pointers if p and key(ref(p)) in sprites])
            except Exception as exc:errors.append(dict(kind='clip',bundle=bundle,id=obj.path_id,error=str(exc)))
        del env;gc.collect()
    families={};candidates=collections.defaultdict(dict)
    for e in enemy_rows:
        f=family(e);info=families.setdefault(f,dict(key=f,name=NAMES.get(f) or translated.get(normalize(f)) or f,
                 runtime_classes=set(),source_assets=set(),instances=0,images=[],cover=''))
        info['runtime_classes'].add(e['class_name']);info['source_assets'].add(e['asset']);info['instances']+=1
        direct={key(r['sprite']) for r in e['renderers'] if not re.search(r'/(?:Lelia|Player)(?:/|$)',r['node'],re.I)}
        for renderer in e['renderers']:
            identity=key(renderer['sprite'])
            if identity not in direct or identity not in sprites:continue
            candidates[f].setdefault(identity,dict(action='场景默认素材',direct=True,active=renderer['active'],node=renderer['node']))
        for c in e['clips']:
            clip=clips.get(key(c))
            if not clip:continue
            for identity in clip['refs']:
                if identity[0] in player_assets and identity not in direct:continue
                candidates[f].setdefault(identity,dict(action=clip['name'],direct=False,active=False,node='动画引用'))
    wanted_bundles=collections.defaultdict(list)
    for f,items in candidates.items():
        for identity,origin in items.items():wanted_bundles[sprites[identity]['bundle']].append((f,identity,origin))
    missing=[b for b in wanted_bundles if not (DECODED/b).exists()]
    if missing:
        file=OUT/'supplement-bundle-files.txt';file.write_text('\n'.join(missing),encoding='utf8')
        subprocess.run(['C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe','-NoProfile','-File',str(ROOT/'.analysis/probe-resource-bundles.ps1'),'-ListFile',str(file)],check=True,stdout=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    (OUT/'previews').mkdir(exist_ok=True);seen=collections.defaultdict(set);stats=collections.Counter()
    for index,(bundle,items) in enumerate(wanted_bundles.items()):
        env=UnityPy.load((DECODED/bundle).read_bytes());objects={(o.assets_file.name.lower(),o.path_id):o for o in env.objects}
        for f,identity,origin in items:
            try:
                sprite=objects[identity].read();image=sprite.image.convert('RGBA');original=list(image.size)
                image.thumbnail((160,160),Image.Resampling.NEAREST);pixel_hash=hashlib.sha256(image.tobytes()).hexdigest()
                if pixel_hash in old_hashes[f] or pixel_hash in seen[f]:stats['duplicates_skipped']+=1;continue
                texture=sprite.m_RD.texture.read();stream=texture.m_StreamData
                if stream and stream.size:blob=stream.path.rsplit('/',1)[-1];offset=stream.offset;size=stream.size
                else:
                    texture_bytes=bytes(texture.image_data);position=texture.object_reader.get_raw_data().find(texture_bytes)
                    assert texture_bytes and position>=0
                    blob=texture.object_reader.assets_file.name;offset=texture.object_reader.byte_start+position;size=len(texture_bytes)
                rd=sprite.m_RD;rect=rd.textureRect;mesh=MeshHandler(rd,sprite.object_reader.version);mesh.process()
                assert not sprite.m_SpriteAtlas and not rd.alphaTexture
                assert not mesh.m_UV0 or not any(x or y for x,y in mesh.m_UV0)
                identifier=hashlib.sha256((f+':'+pixel_hash+':'+str(original)).encode()).hexdigest()[:24]
                spec=dict(id=identifier,bundle=bundle,blob=blob,offset=offset,size=size,format=texture.m_TextureFormat,
                     texture_size=[texture.m_Width,texture.m_Height],rect=[rect.x,rect.y,rect.width,rect.height],
                     rotation=(rd.settingsRaw>>2)&15 if rd.settingsRaw&1 else 0,rgba_sha256=pixel_hash)
                if ((rd.settingsRaw>>1)&1)==0:
                    vertices=mesh.m_Vertices;minimum=[min(v[i] for v in vertices) for i in (0,1)]
                    points=[[(v[i]-minimum[i])*sprite.m_PixelsToUnits for i in (0,1)] for v in vertices]
                    spec['triangles']=[[points[a],points[b],points[c]] for submesh in mesh.get_triangles() for a,b,c in submesh]
                image.save(OUT/'previews'/(identifier+'.png'),optimize=True)
                frame=dict(id=identifier,name=sprite.m_Name+'.png',path='场景引用 / '+sprites[identity]['asset']+' / '+sprite.m_Name,
                           source_kind='scene_embedded',action=origin['action'],category=category(origin['action']),spec=spec,width=original[0],height=original[1],
                           source_asset=sprites[identity]['asset'],source_sprite_id=identity[1])
                families[f]['images'].append(frame);seen[f].add(pixel_hash);stats['added']+=1
                if not families[f]['cover'] and origin['direct']:
                    families[f]['cover']=identifier
            except Exception as exc:errors.append(dict(kind='sprite',family=f,bundle=bundle,identity=identity,error=type(exc).__name__+': '+str(exc)))
        del env;gc.collect()
        if index%40==0:print(json.dumps(dict(bundles=index,total=len(wanted_bundles),**stats)),flush=True)
    for f in families.values():
        f['runtime_classes']=sorted(f['runtime_classes']);f['source_assets']=sorted(f['source_assets'])
        if not f['cover'] and f['images']:f['cover']=f['images'][0]['id']
    result=dict(schema=1,families=list(families.values()),errors=errors,stats=dict(stats),clip_count=len(clips),
                total_audited_bundles=len(records),sprite_reference_candidates=sum(len(v) for v in candidates.values()))
    (OUT/'supplements.json').write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')),encoding='utf8')
    print(json.dumps(dict(stats=dict(stats),family_records=len(families),new_family_keys=sorted(set(families)-{r['key'] for r in catalog}),errors=errors[:10],error_count=len(errors)),ensure_ascii=False),flush=True)

if __name__=='__main__':main()
