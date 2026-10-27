"""Small packaged metadata plus optional local previews; no Unity parser at runtime."""
from copy import deepcopy
import gzip, hashlib, json, re
from pathlib import Path

CATALOG=Path(__file__).parent/'assets/monster-catalog.json.gz'
BUNDLED=Path(__file__).parent/'assets/monster-previews'
_BUNDLED_CACHE={}

class MonsterCatalog:
    def __init__(self,directory):
        self.directory=Path(directory)
        self.preferences=self.directory/'monster-catalog-preferences.json'
        try:self.data=json.loads(gzip.decompress(CATALOG.read_bytes()))
        except (OSError,ValueError):self.data={'families':[]}
        self.families=self.data['families'];self.keys={r['key'] for r in self.families}
        self.favorites=set();self.cache=self.directory/'monster-cache';self.images={};self.bundled_images={};self.local_count=0;self.error=''
        try:
            prefs=json.loads(self.preferences.read_text(encoding='utf8'))
            self.favorites={k for k in prefs.get('favorites',[]) if k in self.keys}
            if isinstance(prefs.get('cache'),str):self.cache=Path(prefs['cache'])
        except (OSError,ValueError,TypeError):pass
        self.reload()

    def _read_images(self,candidate):
        raw=candidate/'manifest.json'
        if raw.stat().st_size>8_000_000:raise ValueError('预览索引过大')
        m=json.loads(raw.read_text(encoding='utf8'))
        if m.get('schema')!=1 or m.get('catalog_sha256')!=hashlib.sha256(CATALOG.read_bytes()).hexdigest():
            raise ValueError('预览缓存与当前怪物目录版本不匹配')
        images={};base=candidate.resolve();known={f['id'] for r in self.families for g in r['groups'] for f in g['frames']}
        for key,item in m.get('images',{}).items():
            if key not in known:continue
            target=(base/str(item.get('file',''))).resolve()
            if not target.is_relative_to(base) or target.suffix.lower()!='.png' or not target.is_file():continue
            images[key]=dict(url=target.as_uri(),width=item.get('width',0),height=item.get('height',0))
        return images

    def reload(self,path=None):
        candidate=Path(path) if path is not None else self.cache
        try:
            stat=(BUNDLED/'manifest.json').stat()
            token=(str(BUNDLED.resolve()),CATALOG.stat().st_mtime_ns,stat.st_mtime_ns,stat.st_size)
            if token not in _BUNDLED_CACHE:_BUNDLED_CACHE[token]=self._read_images(BUNDLED)
            bundled=_BUNDLED_CACHE[token]
        except (OSError,ValueError,TypeError,AttributeError):bundled={}
        try:
            images=self._read_images(candidate)
            self.cache=candidate;self.images={**bundled,**images};self.bundled_images=bundled
            self.local_count=len(images) if candidate.resolve()!=BUNDLED.resolve() else 0;self.error=''
        except (OSError,ValueError,TypeError,AttributeError) as exc:
            if path is not None:self.error='无法导入预览缓存：'+str(exc);return False
            self.images=dict(bundled);self.bundled_images=bundled;self.local_count=0;self.error=''
        return True

    @property
    def bundled_complete(self):
        expected={f['id'] for r in self.families for g in r['groups'] for f in g['frames']}
        return bool(expected) and expected<=self.bundled_images.keys()

    def save(self):
        self.directory.mkdir(parents=True,exist_ok=True)
        target=self.preferences.with_suffix('.tmp')
        target.write_text(json.dumps(dict(favorites=sorted(self.favorites),cache=str(self.cache)),ensure_ascii=False),encoding='utf8')
        target.replace(self.preferences)

    def toggle_favorite(self,key):
        if key not in self.keys:return
        if key in self.favorites:self.favorites.remove(key)
        else:self.favorites.add(key)
        self.save()

    def rows(self):
        rows=deepcopy(self.families)
        for row in rows:
            row['favorite']=row['key'] in self.favorites
            row['preview']=self.images.get(row['cover'],{}).get('url','')
            for group in row['groups']:
                for frame in group['frames']:frame.update(self.images.get(frame['id'],{}))
        return rows

    def summary(self):
        return dict(families=len(self.families),images=sum(r['image_count'] for r in self.families),
                    previews=len(self.images),covers=sum(r['cover'] in self.images for r in self.families),
                    metadata_bytes=CATALOG.stat().st_size,cache=str(self.cache),error=self.error,bundled_previews=len(self.bundled_images),local_previews=self.local_count,
                    version=self.data.get('game_version','—'))

    def match(self,binder):
        # Name match is only a browsing aid; never an output-policy identity.
        normalize=lambda s:re.sub('[^a-z0-9]','',s.lower())
        raw=str(binder or '').split('.')[-1].removesuffix('(Clone)').strip()
        key=normalize(raw)
        if not key:return ''
        exact=next((r['key'] for r in self.families if normalize(r['key'])==key),'')
        if exact:return exact
        matches=[r['key'] for r in self.families if any(normalize(c)==key for c in r.get('runtime_classes',[]))]
        return matches[0] if len(matches)==1 else ''
