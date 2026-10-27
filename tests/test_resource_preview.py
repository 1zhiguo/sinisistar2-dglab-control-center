"""Synthetic UnityFS and cache transactions; production uses actual pinned data."""
from pathlib import Path
from unittest.mock import patch
import gzip,hashlib,json,struct,tempfile,types,unittest
from PIL import Image
from sinisistar_dglab.resource_preview import build_cache,lz4_block,unpack_bundle,sprite_image

TMP=Path(__file__).resolve().parents[1]/'artifacts/test-temp';TMP.mkdir(parents=True,exist_ok=True)
hashbytes=lambda b:hashlib.sha256(b).hexdigest()
def bundle(data,name='texture.resS'):
    info=bytes(16)+struct.pack('>IIIH',1,len(data),len(data),0)+struct.pack('>IQQI',1,0,len(data),0)+name.encode()+b'\0'
    header=b'UnityFS\0'+struct.pack('>I',8)+b'5.x.x\0'+b'2022.3.62f2\0'
    header+=struct.pack('>QIII',0,len(info),len(info),64)
    header+=bytes((-len(header))%16)
    final=bytearray(header+info+data)
    offset=final.index(b'2022.3.62f2\0')+len(b'2022.3.62f2\0')
    struct.pack_into('>Q',final,offset,len(final));return bytes(final)

class ResourcePreviewTests(unittest.TestCase):
    def test_bounded_lz4_overlapping_matches_and_truncated_data(self):
        self.assertEqual(lz4_block(bytes([0x32])+b'abc'+bytes([3,0]),9),b'abcabcabc')
        self.assertEqual(lz4_block(bytes([0x50])+b'hello',5),b'hello')
        for data,n in [(b'\xff',20),(b'\x00\x00\x00',4),(b'\x10a\x02\x00',5),(b'\x50hi',5)]:
            with self.assertRaises(ValueError):lz4_block(data,n)

    def test_uncompressed_bundle_and_sprite_crop_flip(self):
        raw=bytes([255,0,0,255,0,255,0,255,0,0,255,255,255,255,0,255])
        blobs=unpack_bundle(bundle(raw))
        spec=dict(blob='texture.resS',offset=0,size=len(raw),texture_size=[2,2],format=4,rect=[0,0,2,2])
        image,size=sprite_image(spec,blobs)
        self.assertEqual(size,[2,2]);self.assertEqual(image.getpixel((0,0)),(0,0,255,255))
        self.assertEqual(image.getpixel((1,1)),(0,255,0,255))
        spec['size']=99
        with self.assertRaises(ValueError):sprite_image(spec,blobs)
        with self.assertRaises(ValueError):unpack_bundle(b'not a bundle')

    def fixture(self,root):
        game=root/'新游戏 with spaces';source=game/'SiNiSistar2_Data/StreamingAssets/game_bin';source.mkdir(parents=True)
        (game/'GameAssembly.dll').write_bytes(b'game');name='a'*29;raw=bytes([1,2,3,255])*4;packed=bundle(raw)
        (source/name).write_bytes(packed)
        spec=dict(id='a'*24,bundle=name,blob='texture.resS',offset=0,size=len(raw),texture_size=[2,2],format=4,rect=[0,0,2,2],rgba_sha256=hashbytes(raw))
        profile=dict(schema=1,game_files={'GameAssembly.dll':hashbytes(b'game')},bundles={name:hashbytes(packed)},sprites=[spec],crypto={})
        path=root/'profile.gz';path.write_bytes(gzip.compress(json.dumps(profile).encode()))
        def helper(command,**kwargs):
            request=json.loads(Path(command[-1]).read_text(encoding='utf8'))
            for item in request['bundles']:(Path(request['output'])/item).write_bytes((source/item).read_bytes())
            return types.SimpleNamespace(returncode=0,stdout='',stderr='')
        return game,path,helper,source,name

    def test_build_reuses_cache_repairs_damage_and_preserves_existing_on_failure(self):
        with tempfile.TemporaryDirectory(dir=TMP) as directory:
            root=Path(directory);game,profile,helper,source,name=self.fixture(root);cache=root/'cache'
            with patch('sinisistar_dglab.resource_preview.PROFILE',profile),patch('sinisistar_dglab.resource_preview.subprocess.run',side_effect=helper) as process:
                events=[];one=build_cache(game,cache,lambda n,m:events.append(n));self.assertFalse(one['reused'])
                two=build_cache(game,cache);self.assertTrue(two['reused']);self.assertEqual(process.call_count,1)
                png=next((Path(one['path'])/'images').glob('*.png'));png.write_bytes(b'corrupt')
                repaired=build_cache(game,cache);self.assertNotEqual(repaired['path'],one['path'])
                self.assertTrue(build_cache(game,cache)['reused']);self.assertEqual(process.call_count,2)
                with patch('sinisistar_dglab.resource_preview.subprocess.run',return_value=types.SimpleNamespace(returncode=1,stderr='fixture helper failure',stdout='')):
                    with self.assertRaisesRegex(RuntimeError,'fixture helper failure'):build_cache(game,cache,force=True)
                self.assertTrue(build_cache(game,cache)['reused'])
                self.assertFalse(list(cache.glob('preview-work-*')))
                (source/name).write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError,'已被修改'):build_cache(game,cache)
                with self.assertRaisesRegex(ValueError,'游戏目录之外'):build_cache(game,game/'cache')
                self.assertEqual(events[-1],100);self.assertEqual(events,sorted(events))

if __name__=='__main__':unittest.main()
