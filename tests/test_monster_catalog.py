from pathlib import Path
import hashlib,json,tempfile,unittest
from sinisistar_dglab.monster_catalog import MonsterCatalog,CATALOG
from unittest.mock import patch

TEMP=Path(__file__).resolve().parents[1]/'artifacts/test-temp'
TEMP.mkdir(parents=True,exist_ok=True)

class MonsterCatalogTests(unittest.TestCase):
    def test_missing_cache_keeps_complete_text_catalog(self):
        with tempfile.TemporaryDirectory(dir=TEMP) as directory,patch('sinisistar_dglab.monster_catalog.BUNDLED',TEMP/'no-bundled-package'):
            c=MonsterCatalog(directory)
            self.assertEqual(c.summary()['families'],115);self.assertEqual(c.summary()['images'],3571)
            self.assertEqual(c.summary()['previews'],0)
            self.assertEqual(sum(not r['image_count'] for r in c.rows()),4)
            self.assertLess(CATALOG.stat().st_size,120_000)
            for key in ('PigBG','PigParasite','VillagerMiddleMale_A_Pig'):
                row=next(r for r in c.rows() if r['key']==key)
                self.assertGreater(row['image_count'],0);self.assertTrue(row['aliases'])

    def test_favorites_persist_and_matching_is_conservative(self):
        with tempfile.TemporaryDirectory(dir=TEMP) as directory:
            c=MonsterCatalog(directory);c.toggle_favorite('Zombie');c.toggle_favorite('unknown')
            other=MonsterCatalog(directory);self.assertEqual(other.favorites,{'Zombie'})
            self.assertEqual(other.match('Zombie(Clone)'),'Zombie')
            self.assertEqual(other.match('DemiHumanBoss'),'DemiHuman_Boss')
            self.assertEqual(other.match('NotZombie'),'')
            other.toggle_favorite('Zombie');self.assertEqual(MonsterCatalog(directory).favorites,set())

    def test_cache_rejects_wrong_catalog_and_escaping_paths(self):
        with tempfile.TemporaryDirectory(dir=TEMP) as directory,patch('sinisistar_dglab.monster_catalog.BUNDLED',TEMP/'no-bundled-package'):
            root=Path(directory);cache=root/'cache';cache.mkdir()
            c=MonsterCatalog(root);key=next(f['id'] for r in c.families for g in r['groups'] for f in g['frames'])
            (root/'outside.png').write_bytes(b'not-an-image')
            manifest=dict(schema=1,catalog_sha256='bad',images={key:dict(file='../outside.png')})
            (cache/'manifest.json').write_text(json.dumps(manifest));self.assertFalse(c.reload(cache))
            manifest['catalog_sha256']=hashlib.sha256(CATALOG.read_bytes()).hexdigest()
            (cache/'manifest.json').write_text(json.dumps(manifest));self.assertTrue(c.reload(cache));self.assertEqual(c.images,{})
            c.images[key]=dict(url='existing');self.assertFalse(c.reload(root/'missing'))
            self.assertIn(key,c.images) # A failed import preserves the previous valid cache.

    def test_packaged_previews_work_without_a_game_or_cache_and_survive_stale_preferences(self):
        with tempfile.TemporaryDirectory(dir=TEMP) as directory:
            root=Path(directory)
            (root/'monster-catalog-preferences.json').write_text(json.dumps(dict(cache=str(root/'missing-old-cache'),favorites=['Rat'])))
            c=MonsterCatalog(root)
            self.assertTrue(c.bundled_complete);self.assertEqual(c.summary()['previews'],3571)
            self.assertEqual(c.summary()['local_previews'],0);self.assertIn('Rat',c.favorites)
            self.assertTrue(next(r for r in c.rows() if r['key']=='Rat')['preview'])
            self.assertFalse((root/'monster-cache').exists())

    def test_partial_local_cache_overlays_packaged_frames_without_hiding_other_images(self):
        with tempfile.TemporaryDirectory(dir=TEMP) as directory:
            root=Path(directory);c=MonsterCatalog(root);identifier=next(iter(c.images))
            cache=root/'cache';cache.mkdir();(cache/'override.png').write_bytes(b'fixture')
            (cache/'manifest.json').write_text(json.dumps(dict(schema=1,catalog_sha256=hashlib.sha256(CATALOG.read_bytes()).hexdigest(),images={identifier:dict(file='override.png',width=4,height=4)})))
            self.assertTrue(c.reload(cache));self.assertEqual(c.summary()['previews'],3571)
            self.assertEqual(c.summary()['local_previews'],1);self.assertIn('override.png',c.images[identifier]['url'])

if __name__=='__main__':unittest.main()
