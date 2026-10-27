"""Build-bound local thumbnails. Standard library + existing Pillow only.

The shipped profile contains byte locations, sprite geometry and hashes, never
pixels. Game data is read-only. Work and published caches stay outside the game.
"""
import gzip, hashlib, io, json, os, struct, subprocess, tempfile
from pathlib import Path
from PIL import Image, ImageDraw
from .monster_catalog import CATALOG

PROFILE=Path(__file__).parent/'assets/monster-extract-profile.json.gz'
HELPER=Path(__file__).parent/'assets/decode-preview-bundles.ps1'

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for part in iter(lambda:f.read(1024*1024),b''):h.update(part)
    return h.hexdigest()

def lz4_block(data,size):
    """Decode one bounded raw LZ4 block, including overlapping matches."""
    if not 0<=size<=512*1024*1024:raise ValueError('资源块过大')
    out=bytearray();at=0
    def length(value):
        nonlocal at
        if value==15:
            while True:
                if at>=len(data):raise ValueError('资源压缩块不完整')
                extra=data[at];at+=1;value+=extra
                if extra!=255:break
        return value
    while at<len(data):
        token=data[at];at+=1;n=length(token>>4)
        if at+n>len(data) or len(out)+n>size:raise ValueError('资源压缩块长度无效')
        out.extend(data[at:at+n]);at+=n
        if at==len(data):break
        if at+2>len(data):raise ValueError('资源压缩块偏移缺失')
        offset=data[at]|data[at+1]<<8;at+=2;n=length(token&15)+4
        if offset==0 or offset>len(out) or len(out)+n>size:raise ValueError('资源压缩块偏移无效')
        pattern=out[-offset:];out.extend((pattern*((n+offset-1)//offset))[:n])
    if len(out)!=size:raise ValueError('资源解压长度不匹配')
    return bytes(out)

class Reader:
    def __init__(self,data):self.data=data;self.at=0
    def read(self,n):
        end=self.at+n
        if n<0 or end>len(self.data):raise ValueError('资源包不完整')
        value=self.data[self.at:end];self.at=end;return value
    def number(self,fmt):return struct.unpack('>'+fmt,self.read(struct.calcsize('>'+fmt)))[0]
    def string(self):
        end=self.data.find(b'\0',self.at)
        if end<0 or end-self.at>4096:raise ValueError('资源包名称无效')
        value=self.read(end-self.at);self.read(1);return value.decode('utf8')
    def align(self):self.read((-self.at)%16)

def unpack_bundle(data):
    r=Reader(data)
    if r.string()!='UnityFS' or r.number('I')!=8:raise ValueError('资源包格式不匹配')
    r.string();r.string();total=r.number('Q');compressed=r.number('I');plain=r.number('I');flags=r.number('I')
    if total!=len(data):raise ValueError('资源包长度不匹配')
    r.align();start=r.at
    if flags&128:r.at=len(data)-compressed
    info=r.read(compressed)
    if flags&128:r.at=start
    def decode(value,size,mode):
        if mode==0:
            if len(value)!=size:raise ValueError('资源块大小不匹配')
            return value
        if mode in (2,3):return lz4_block(value,size)
        raise ValueError('此构建出现了未支持的资源压缩格式')
    header=Reader(decode(info,plain,flags&63));header.read(16)
    count=header.number('I')
    if count>100000:raise ValueError('资源块数量无效')
    blocks=[(header.number('I'),header.number('I'),header.number('H')) for _ in range(count)]
    count=header.number('I')
    if count>100000:raise ValueError('资源条目数量无效')
    entries=[]
    for _ in range(count):
        offset=header.number('Q');size=header.number('Q');header.number('I');name=header.string();entries.append((name,offset,size))
    if sum(b[0] for b in blocks)>512*1024*1024:raise ValueError('资源包展开后过大')
    if flags&512:r.align()
    payload=b''.join(decode(r.read(packed),size,mode&63) for size,packed,mode in blocks)
    result={}
    for name,offset,size in entries:
        if offset+size>len(payload):raise ValueError('资源条目越界')
        result[name]=memoryview(payload)[offset:offset+size]
    return result

def sprite_image(spec,blobs):
    b=blobs[spec['blob']];offset=spec['offset'];size=spec['size']
    if offset<0 or offset+size>len(b):raise ValueError('贴图数据越界')
    raw=bytes(b[offset:offset+size]);w,h=spec['texture_size'];fmt=spec['format']
    if fmt==4:image=Image.frombytes('RGBA',(w,h),raw[:w*h*4])
    elif fmt==3:image=Image.frombytes('RGB',(w,h),raw[:w*h*3]).convert('RGBA')
    elif fmt==12:image=Image.frombytes('RGBA',(w,h),raw,'bcn',(3,'DXT5'))
    else:raise ValueError('此构建出现了未支持的贴图格式')
    x,y,cw,ch=spec['rect'];image=image.crop((x,y,x+cw,y+ch))
    rotation=spec.get('rotation',0)
    transpose={1:Image.Transpose.FLIP_LEFT_RIGHT,2:Image.Transpose.FLIP_TOP_BOTTOM,3:Image.Transpose.ROTATE_180,4:Image.Transpose.ROTATE_270}
    if rotation in transpose:image=image.transpose(transpose[rotation])
    if spec.get('triangles'):
        mask=Image.new('1',image.size);draw=ImageDraw.Draw(mask)
        for triangle in spec['triangles']:draw.polygon([tuple(p) for p in triangle],fill=1)
        image=Image.composite(image,Image.new('RGBA',image.size),mask)
    image=image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    original=list(image.size);image.thumbnail((160,160),Image.Resampling.NEAREST)
    return image,original

def build_cache(game_dir,cache_root,progress=None,*,force=False):
    root=Path(game_dir).resolve();cache_root=Path(cache_root).resolve()
    if cache_root==root or cache_root.is_relative_to(root):raise ValueError('预览缓存必须保存在游戏目录之外')
    p=json.loads(gzip.decompress(PROFILE.read_bytes()))
    if p.get('schema')!=1:raise ValueError('贴图提取配置不兼容')
    def notify(n,message):
        if progress:progress(n,message)
    notify(1,'正在核对本地游戏贴图资源…')
    for relative,expected in p['game_files'].items():
        if digest(root/relative)!=expected:raise ValueError('所选游戏资源与已验证的 v1.3.1 构建不符：'+relative)
    source=root/'SiNiSistar2_Data/StreamingAssets/game_bin'
    for name,expected in p['bundles'].items():
        if not __import__('re').fullmatch('[a-f0-9]{29}',name):raise ValueError('资源包名称无效')
        if digest(source/name)!=expected:raise ValueError('游戏资源包缺失或已被修改：'+name)
    catalog_hash=hashlib.sha256(CATALOG.read_bytes()).hexdigest()
    signature=hashlib.sha256(PROFILE.read_bytes()).hexdigest()
    generation=catalog_hash[:16]+'-'+signature[:12]
    target=cache_root/'versions'/generation
    pointer=cache_root/('active-'+generation+'.json')
    try:
        selected=(cache_root/json.loads(pointer.read_text(encoding='utf8'))['path']).resolve()
        if selected.is_relative_to(cache_root/'versions'):target=selected
    except (OSError,ValueError,KeyError,TypeError):pass
    def complete():
        try:
            m=json.loads((target/'manifest.json').read_text(encoding='utf8'))
            if m.get('source_signature')!=signature or m.get('catalog_sha256')!=catalog_hash:return False
            if set(m['images'])!={s['id'] for s in p['sprites']}:return False
            return all((target/v['file']).resolve().is_relative_to(target) and digest(target/v['file'])==v['sha256'] for v in m['images'].values())
        except (OSError,ValueError,KeyError,TypeError):return False
    if not force and complete():
        notify(100,'怪物图鉴缓存已就绪，无需重复生成')
        return dict(success=True,path=str(target),images=len(p['sprites']),reused=True)
    cache_root.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='preview-work-',dir=cache_root) as temporary:
        work=Path(temporary);decoded=work/'decoded';decoded.mkdir();output=work/'cache';(output/'images').mkdir(parents=True)
        request=dict(game=str(root),output=str(decoded),resources='SiNiSistar2_Data/resources.assets',crypto=p['crypto'],bundles=list(p['bundles']))
        request_file=work/'request.json';request_file.write_text(json.dumps(request,ensure_ascii=False),encoding='utf8')
        powershell=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
        notify(7,'正在读取游戏本地资源包…')
        flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
        result=subprocess.run([str(powershell),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(HELPER),'-Request',str(request_file)],capture_output=True,encoding='utf8',errors='replace',timeout=120,creationflags=flags)
        if result.returncode:raise RuntimeError('无法读取游戏资源：'+(result.stderr or result.stdout)[-700:])
        by_bundle={}
        for spec in p['sprites']:by_bundle.setdefault(spec['bundle'],[]).append(spec)
        images={}
        for index,(bundle,specs) in enumerate(by_bundle.items()):
            notify(12+int(82*index/len(by_bundle)),'正在生成怪物图鉴预览 · '+str(len(images))+' / '+str(len(p['sprites'])))
            blobs=unpack_bundle((decoded/bundle).read_bytes())
            for spec in specs:
                image,original=sprite_image(spec,blobs)
                if hashlib.sha256(image.tobytes()).hexdigest()!=spec['rgba_sha256']:
                    raise ValueError('贴图解码验证失败：'+spec['id'])
                filename='images/'+spec['id']+'.png';image.save(output/filename,optimize=True)
                images[spec['id']]=dict(file=filename,width=original[0],height=original[1],sha256=digest(output/filename))
        manifest=dict(schema=1,game_version='1.3.1',catalog_sha256=catalog_hash,source_signature=signature,images=images)
        (output/'manifest.json').write_text(json.dumps(manifest,separators=(',',':')),encoding='utf8')
        target.parent.mkdir(parents=True,exist_ok=True)
        # Publish to a fresh generation directory; existing cache remains intact
        # until all PNGs and their manifest have passed validation.
        if target.exists():target=target.with_name(target.name+'-'+__import__('uuid').uuid4().hex[:8])
        output.replace(target)
        pointer_tmp=work/'active.json'
        pointer_tmp.write_text(json.dumps(dict(path=target.relative_to(cache_root).as_posix())),encoding='utf8')
        pointer_tmp.replace(pointer)
    notify(100,'怪物图鉴预览已生成 · '+str(len(images))+' 张')
    return dict(success=True,path=str(target),images=len(images),reused=False)
