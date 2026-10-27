"""Build the small catalog and an optional LOCAL preview cache from research copies.

UnityPy is a development-only dependency; neither it nor decoded bundles belong
in the control-center distribution. No source game files or settings are changed.
"""
from pathlib import Path
import shutil
import collections, gzip, hashlib, json, re, sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT/'.analysis/unitypy'))
import UnityPy
from PIL import Image
from UnityPy.helpers.MeshHelper import MeshHandler
from sinisistar_dglab.flow_semantics import ENEMIES
from sinisistar_dglab.telemetry import BUILD

RESEARCH=ROOT/'artifacts/research/monster-textures'
CACHE=ROOT/'artifacts/monster-cache'
NAMES={
 'Bobel':'博贝尔','Bobel_Barnacle':'博贝尔 · 藤壶','Bobel_Shadow':'博贝尔 · 暗影',
 'Gravekeeper':'守墓人','Pendulum_Stone':'石质摆锤','TreeBoss':'树木首领',
 'Enenuth_Mother':'埃涅努斯母体','Enenuth_Tentacle':'埃涅努斯触手','Enenuth_JellyFish':'埃涅努斯水母',
 'Enenuth_Nest':'埃涅努斯巢穴','Enenuth_Mollusk':'埃涅努斯软体',
 'Funghoul':'菌尸','Funghoul_Base':'菌尸 · 基体','MeatEgg':'血肉卵',
 'MeatTentacleCeiling':'天花板触手','MeatTentacleCluster':'触手簇','MeatWall':'血肉墙',
 'MeatWomb':'血肉子宫','MeatWorm1':'血肉蠕虫','MeatWormShooter':'喷射蠕虫',
 'Leech_Man':'水蛭人','Leech_Baby':'幼生水蛭','Leech_Boss':'水蛭首领',
 'Leech_Gluttony':'贪食水蛭','Leech_Adult':'成年水蛭','Leech_Swanp':'沼泽水蛭',
 'Priest_Town':'城镇神职者','Priest_Cathedral':'教堂神职者','Slug_Boss':'蛞蝓首领',
 'Zombie_G':'僵尸 · G 变体','Zombie_Spawner':'僵尸生成体','Zombie_Cru':'僵尸 · Crucifix 变体',
 'Zombie_Coffin':'棺中僵尸','Zombie_Coffin2':'棺中僵尸 · 变体','MidasTouch':'米达斯之触',
 'PictureEnemy':'画中怪物','PictureEnemy_Big':'大型画中怪物','LesserVampire':'次级吸血鬼',
 'SisterOAC':'修女 · OAC','SisterTentacle':'触手修女','Mother_of_the_Outer_One':'外界之母',
 'Seere':'塞雷','Spider_Nest':'蜘蛛巢穴','Hag':'女巫','Region':'Region · 特殊敌人',
 'VillagerParasite_MM_B':'寄生村民 · B 变体',
 'PigBG':'普通猪','PigParasite':'寄生猪','VillagerMiddleMale_A_Pig':'猪人 · 变身村民',
}
normalize=lambda s:re.sub('[^a-z0-9]','',s.lower())
translated={normalize(k):v for k,v in ENEMIES.items()}
def category(path):
    s=path.lower()
    if any(x in s for x in ('hold','bind','gacha','capture')):return '抓取 / 受制'
    if any(x in s for x in ('death','dead','defeat','punish','vore','end_','gameover')):return '战败相关'
    if any(x in s for x in ('attack','shot','shoot','threat')):return '攻击'
    if any(x in s for x in ('damage','hurt','hit')):return '受击'
    if any(x in s for x in ('walk','move','run','jump','fly')):return '移动'
    if any(x in s for x in ('idle','wait','stand')):return '待机'
    return '其他 / 部件'

def main():
    table=json.loads((RESEARCH/'resource-name-table.json').read_text(encoding='utf8'))
    rows=table['m_EnemyAssetBundleInfoList']['m_AssetBundleInfoList']
    # These enemies are scene-embedded and absent from the Enemy name table.
    scene_bundle='2784cfee5c0182abdc119a819a1eb'
    scene=UnityPy.load(str(RESEARCH/'decoded'/scene_bundle))
    embedded={}
    for obj in scene.objects:
        if obj.type.name=='Sprite':
            sprite=obj.read();embedded.setdefault(sprite.m_Name,obj)
    pigman_parts={}
    def parts(transform):
        go=transform.m_GameObject.read()
        for entry in go.m_Component:
            obj=entry.component.deref()
            if obj.type.name=='SpriteRenderer':
                sprite=obj.read().m_Sprite
                if sprite:
                    value=sprite.read();pigman_parts.setdefault(value.m_Name,sprite.deref())
        for child in transform.m_Children:parts(child.read())
    for obj in scene.objects:
        if obj.type.name=='GameObject':
            go=obj.read()
            if go.m_Name=='VillagerMiddleMale_A_Pig':
                for entry in go.m_Component:
                    component=entry.component.deref()
                    if component.type.name=='Transform':parts(component.read())
    extra_objects={}
    for family in ('PigBG','PigParasite','VillagerMiddleMale_A_Pig'):
        selected={n:o for n,o in embedded.items() if (n.startswith('head_pig_') if family=='VillagerMiddleMale_A_Pig' else n.startswith('pig_') and (family=='PigParasite' or not n.startswith('pig_baby_')))}
        if family=='VillagerMiddleMale_A_Pig':selected.update(pigman_parts)
        for name,obj in selected.items():
            action=re.sub(r'_\d+$','',name)
            path='Design/Character/Enemy/'+family+'/'+action+'/'+name+'.png'
            rows.append(dict(m_VirtualPath=path,m_AssetBundleName=scene_bundle,scene_embedded=True))
            extra_objects[path]=obj
    by_family=collections.defaultdict(list)
    for row in rows:by_family[re.search(r'/Enemy/([^/]+)/',row['m_VirtualPath'])[1]].append(row)
    by_bundle=collections.defaultdict(list)
    catalog=[];cache=dict(schema=1,game_version='1.3.1',images={})
    CACHE.mkdir(parents=True,exist_ok=True);(CACHE/'images').mkdir(exist_ok=True)
    for family,items in sorted(by_family.items()):
        grouped=collections.defaultdict(list)
        for item in items:
            if not item['m_VirtualPath'].endswith('.png'):continue
            path=item['m_VirtualPath'];relative=path.split('/Enemy/'+family+'/',1)[1]
            action=str(Path(relative).parent).replace('\\','/')
            image_id=hashlib.sha256(path.encode()).hexdigest()[:24]
            frame=dict(id=image_id,name=Path(path).name,path=path)
            if item.get('scene_embedded'):frame['source_kind']='scene_embedded'
            grouped[action].append(frame);by_bundle[item['m_AssetBundleName']].append(frame)
        groups=[dict(key=key,name='素材根目录' if key=='.' else key,category=category(key),frames=sorted(frames,key=lambda f:f['name'])) for key,frames in grouped.items()]
        rank={'待机':0,'移动':1,'攻击':2,'其他 / 部件':3,'受击':4,'抓取 / 受制':5,'战败相关':6}
        groups.sort(key=lambda g:(rank[g['category']],g['name'].lower()))
        frames=[f for g in groups for f in g['frames']]
        layered=sum(bool(re.match(r'(?:arm|head|chest|body|shoulder|foot|leg)[_\.]',f['name'],re.I)) for f in frames)>5
        cover=groups[0]['frames'][0]['id'] if groups else ''
        if layered and not any(g['category']=='待机' for g in groups):
            cover=next((f['id'] for f in frames if re.match(r'head(?:_pig)?_000\.',f['name'],re.I)),cover)
        name=NAMES.get(family) or translated.get(normalize(family)) or family
        aliases={'PigBG':['猪','普通猪','背景猪','猪棚'],'PigParasite':['猪','寄生猪','猪棚'],'VillagerMiddleMale_A_Pig':['猪人','村民猪人','猪棚'],'Pig_Dining':['猪','餐厅猪','进食猪']}.get(family,[])
        catalog.append(dict(key=family,name=name,aliases=aliases,scene_embedded=any(x.get('scene_embedded') for x in items),translation='工作译名 / 原始资源名',resources=len(items),
                            image_count=sum(len(g['frames']) for g in groups),groups=groups,
                            cover=cover,layered=layered,
                            has_defeat=any(g['category'] in ('抓取 / 受制','战败相关') for g in groups)))
    profile=dict(schema=1,game_files={'GameAssembly.dll':BUILD},bundles={},sprites=[])
    game=ROOT/'SiNiSistar2_v1_3_1/WIN'
    resource=game/'SiNiSistar2_Data/resources.assets'
    profile['game_files']['SiNiSistar2_Data/resources.assets']=hashlib.sha256(resource.read_bytes()).hexdigest()
    resources=UnityPy.load(str(resource));unique=next(o for o in resources.objects if o.path_id==1073)
    profile['crypto']=dict(iv_offset=unique.byte_start+36,iv_length=16,key_offset=unique.byte_start+56,key_length=17,iv_suffix='01127802CDEF00BC',key_suffix='06789412023ED45')
    for bundle,frames in by_bundle.items():
        profile['bundles'][bundle]=hashlib.sha256((game/'SiNiSistar2_Data/StreamingAssets/game_bin'/bundle).read_bytes()).hexdigest()
        env=UnityPy.load(str(RESEARCH/'decoded'/bundle));objects={p.lower():o for p,o in env.container.items()}
        for frame in frames:
            obj=extra_objects.get(frame['path']) or objects[('assets/'+frame['path']).lower()]
            sprite=obj.read();image=sprite.image.convert('RGBA')
            texture=sprite.m_RD.texture.read();stream=texture.m_StreamData
            if stream and stream.size:
                blob=stream.path.split('/')[-1];offset=stream.offset;size=stream.size
            else:
                texture_bytes=bytes(texture.image_data);raw=texture.object_reader.get_raw_data();position=raw.find(texture_bytes)
                assert texture_bytes and position>=0
                blob=texture.object_reader.assets_file.name;offset=texture.object_reader.byte_start+position;size=len(texture_bytes)
            rd=sprite.m_RD;rect=rd.textureRect
            spec=dict(id=frame['id'],bundle=bundle,blob=blob,offset=offset,size=size,format=texture.m_TextureFormat,
                      texture_size=[texture.m_Width,texture.m_Height],rect=[rect.x,rect.y,rect.width,rect.height],
                      rotation=(rd.settingsRaw>>2)&15 if rd.settingsRaw&1 else 0)
            mesh=MeshHandler(rd,sprite.object_reader.version);mesh.process()
            assert not sprite.m_SpriteAtlas and not rd.alphaTexture
            assert not mesh.m_UV0 or not any(x or y for x,y in mesh.m_UV0)
            if ((rd.settingsRaw>>1)&1)==0:
                positions=mesh.m_Vertices;minimum=[min(v[i] for v in positions) for i in (0,1)]
                points=[[(v[i]-minimum[i])*sprite.m_PixelsToUnits for i in (0,1)] for v in positions]
                spec['triangles']=[[points[a],points[b],points[c]] for submesh in mesh.get_triangles() for a,b,c in submesh]
            # Retain original framing and alpha; scale down only, never upscale source.
            original=list(image.size);image.thumbnail((160,160),Image.Resampling.NEAREST)
            filename='images/'+frame['id']+'.png';image.save(CACHE/filename,optimize=True)
            cache['images'][frame['id']]=dict(file=filename,width=original[0],height=original[1])
            spec['rgba_sha256']=hashlib.sha256(image.tobytes()).hexdigest();profile['sprites'].append(spec)
    supplements_path=ROOT/'artifacts/research/monster-audit/supplements.json'
    if supplements_path.is_file():
        supplemental=json.loads(supplements_path.read_text(encoding='utf8'))
        assert not supplemental['errors'],supplemental['errors'][:3]
        by_key={r['key']:r for r in catalog}
        old_hashes=collections.defaultdict(set);id_family={f['id']:r['key'] for r in catalog for g in r['groups'] for f in g['frames']}
        for spec in profile['sprites']:old_hashes[id_family[spec['id']]].add(spec['rgba_sha256'])
        for extra in supplemental['families']:
            key=extra['key'];row=by_key.get(key)
            if row is None:
                row=dict(key=key,name=extra['name'],aliases=[],scene_embedded=True,translation='工作译名 / 真实敌人组件引用',resources=0,image_count=0,groups=[],cover='',layered=True,has_defeat=False)
                catalog.append(row);by_key[key]=row
            row['runtime_classes']=extra['runtime_classes'];row['source_assets']=extra['source_assets']
            row['kind']='part' if any(re.search('WeakPoint|Eye|Ivy|RegionPart|BurstChild|ClusterBase|Cluster2|Splash',c) for c in extra['runtime_classes']) else 'enemy'
            grouped={g['key']:g for g in row['groups']}
            for frame in extra['images']:
                spec=frame['spec']
                if spec['rgba_sha256'] in old_hashes[key]:continue
                old_hashes[key].add(spec['rgba_sha256'])
                group_key='场景补充 / '+frame['action']
                if group_key not in grouped:
                    group=dict(key=group_key,name=group_key,category=frame['category'],frames=[]);row['groups'].append(group);grouped[group_key]=group
                grouped[group_key]['frames'].append({k:frame[k] for k in ('id','name','path','source_kind')})
                row['image_count']+=1;row['resources']+=1;row['scene_embedded']=True
                profile['sprites'].append(spec);profile['bundles'][spec['bundle']]=hashlib.sha256((game/'SiNiSistar2_Data/StreamingAssets/game_bin'/spec['bundle']).read_bytes()).hexdigest()
                filename='images/'+frame['id']+'.png';shutil.copy2(ROOT/'artifacts/research/monster-audit/previews'/(frame['id']+'.png'),CACHE/filename)
                cache['images'][frame['id']]=dict(file=filename,width=frame['width'],height=frame['height'])
            if not row['cover']:
                row['cover']=extra['cover'] if extra['cover'] in cache['images'] else next((f['id'] for g in row['groups'] for f in g['frames']),'')
            if not row['image_count']:row['preview_note']='未找到可直接读取的 Sprite；可能由共享材质、网格或程序生成'
        catalog.sort(key=lambda r:r['key'].lower())
    manifest=dict(schema=1,game_version='1.3.1',families=catalog)
    target=ROOT/'src/sinisistar_dglab/assets/monster-catalog.json.gz'
    payload=(json.dumps(manifest,ensure_ascii=False,separators=(',',':'))+'\n').encode('utf8')
    target.write_bytes(gzip.compress(payload,mtime=0))
    (target.parent/'monster-extract-profile.json.gz').write_bytes(gzip.compress(json.dumps(profile,separators=(',',':')).encode(),mtime=0))
    cache['catalog_sha256']=hashlib.sha256(target.read_bytes()).hexdigest()
    (CACHE/'manifest.json').write_text(json.dumps(cache,separators=(',',':')),encoding='utf8')
    sizes=dict(metadata_bytes=target.stat().st_size,metadata_uncompressed_bytes=len(payload),preview_count=len(cache['images']),
               preview_png_bytes=sum(p.stat().st_size for p in (CACHE/'images').glob('*.png')),
               cache_manifest_bytes=(CACHE/'manifest.json').stat().st_size,
               parser_shipped=False,source_bundles_shipped=False,cache_shipped=False)
    (RESEARCH/'catalog-size.json').write_text(json.dumps(sizes,indent=2)+'\n',encoding='utf8')
    from copy_monster_previews import copy_previews
    sizes['bundled']=copy_previews();print(json.dumps(sizes))

if __name__=='__main__':main()
