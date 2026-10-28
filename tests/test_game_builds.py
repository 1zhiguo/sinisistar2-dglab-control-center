"""Distribution profiles preserve exact file sets and real IPC identities."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,tempfile,unittest
from sinisistar_dglab.game_builds import PROFILES,FINGERPRINTS
from sinisistar_dglab.install_manager import InstallManager,EXPECTED_BUILD,ROOT
from sinisistar_dglab.plugin_bridge import PluginObserver
from sinisistar_dglab.save_import import default_directory

class BuildProfiles(unittest.TestCase):
    def test_full_profile_is_preserved_and_shared_csharp_pairs_match(self):
        self.assertEqual(PROFILES[0]['files'],EXPECTED_BUILD)
        code=(ROOT/'observer/BuildCompatibility.cs').read_text(encoding='utf-8')
        for profile in PROFILES:
            files=profile['files'];self.assertEqual(set(files),set(EXPECTED_BUILD))
            self.assertIn(files['GameAssembly.dll'],FINGERPRINTS)
            self.assertIn('fingerprint=="'+files['GameAssembly.dll']+'" && metadata=="'+files['SiNiSistar2_Data/il2cpp_data/Metadata/global-metadata.dat']+'"',code)
    def test_lite_real_fingerprint_is_accepted_and_unknown_is_rejected(self):
        lite=next(p for p in PROFILES if p['id'].startswith('steam-'))
        data=dict(schema=1,source='bepinex',fingerprint=lite['files']['GameAssembly.dll'],pid=1,session='test',sample_id=1,utc=datetime.now(timezone.utc).isoformat(),scene_id=19,valid=False,abnormals=[])
        self.assertTrue(PluginObserver.decode(data)['live'])
        data['fingerprint']='0'*64
        with self.assertRaises(ValueError):PluginObserver.decode(data)
    def test_exact_profiles_reject_mixed_core_files(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as tmp:
            root=Path(tmp);first={k:('first:'+k).encode() for k in EXPECTED_BUILD};second={k:('second:'+k).encode() for k in EXPECTED_BUILD}
            hashes=lambda data:{k:hashlib.sha256(v).hexdigest() for k,v in data.items()}
            manager=InstallManager(_expected_build=hashes(first),_process_checker=lambda _:False)
            manager.build_profiles=[dict(id='first',label='First',files=hashes(first)),dict(id='second',label='Second',files=hashes(second))]
            for data in (first,second):
                for name,value in data.items():
                    p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(value)
                self.assertTrue(manager.inspect_game(root)['supported'])
            (root/'GameAssembly.dll').write_bytes(first['GameAssembly.dll'])
            result=manager.inspect_game(root);self.assertFalse(result['supported']);self.assertEqual(result['state'],'unsupported')
    def test_steam_saves_are_separate_from_original_distribution(self):
        self.assertEqual(default_directory().name,'SaveData')
        self.assertEqual(default_directory('steam-lite-1.3.1').name,'SaveData_S')
