"""Installer tests use tiny synthetic game/payload files under project temp."""
import hashlib,json,os,subprocess,tempfile,unittest,zipfile
from pathlib import Path
from sinisistar_dglab.install_manager import InstallManager,InstallError,normalize_game_dir,PLUGIN,CONFIG,CACHE,MANIFEST,OWNER,SOURCE_HASH

ROOT=Path(__file__).resolve().parents[1]
TMP=ROOT/'artifacts/test-temp';TMP.mkdir(parents=True,exist_ok=True)
def digest(data):return hashlib.sha256(data).hexdigest()

class Installer(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=TMP);self.root=Path(self.temp.name);self.game=self.root/'game_v1_3_1/WIN';self.game.mkdir(parents=True)
        self.build={'SiNiSistar2.exe':b'fake-exe','GameAssembly.dll':b'fake-game-assembly','UnityPlayer.dll':b'fake-unity',
                    'SiNiSistar2_Data/il2cpp_data/Metadata/global-metadata.dat':b'fake-metadata'}
        for relative,data in self.build.items():
            path=self.game/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        self.expected={key:digest(value) for key,value in self.build.items()}
        self.payload=self.root/'payload';self.payload.mkdir();self.runtime={'winhttp.dll':b'known-loader','doorstop_config.ini':b'known-doorstop',
                                '.doorstop_version':b'4.0','BepInEx/core/BepInEx.Core.dll':b'known-runtime','dotnet/coreclr.dll':b'known-dotnet'}
        self.package()
    def tearDown(self):self.temp.cleanup()
    def package(self,extra=None):
        entries=dict(self.runtime);entries.update(extra or {})
        with zipfile.ZipFile(self.payload/'bepinex-runtime.zip','w') as archive:
            for name,data in entries.items():archive.writestr(name,data)
        (self.payload/'SiNiSistarDGLab.Observer.dll').write_bytes(b'observer-v0.3')
        (self.payload/'unity-2022.3.62.zip').write_bytes(b'fixture-unity-cache')
        self.trusted={name:digest((self.payload/name).read_bytes()) for name in ('bepinex-runtime.zip','unity-2022.3.62.zip','SiNiSistarDGLab.Observer.dll')}
        manifest=dict(schema=1,owner=OWNER,plugin_version='0.3.0',runtime='fixture runtime',source_archive_sha256=SOURCE_HASH,
                      archives={name:dict(sha256=value) for name,value in self.trusted.items()},
                      runtime_files=[dict(path=name,sha256=digest(data),size=len(data)) for name,data in entries.items()])
        (self.payload/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    def manager(self,**kwargs):return InstallManager(self.payload,_expected_build=self.expected,_trusted_archives=self.trusted,_process_checker=kwargs.pop('_process_checker',lambda exe:False),**kwargs)
    def tree(self):return {str(p.relative_to(self.game)):p.read_bytes() for p in self.game.rglob('*') if p.is_file()}
    def test_select_executable_win_or_top_folder(self):
        for path in (self.game,self.game/'SiNiSistar2.exe',self.game.parent):self.assertEqual(normalize_game_dir(path),self.game.resolve())
    def test_fresh_install_is_self_contained_and_does_not_touch_game_or_save(self):
        saved=self.game/'SaveData/progress.dat';saved.parent.mkdir();saved.write_bytes(b'my-save')
        plugin=self.game/'BepInEx/plugins/Other/keep.dll';plugin.parent.mkdir(parents=True);plugin.write_bytes(b'other-plugin')
        progress=[];result=self.manager().install(self.game.parent,lambda p,text:progress.append(p))
        self.assertTrue(result['success']);self.assertFalse(result['load_verified']);self.assertTrue(result['requires_restart'])
        self.assertEqual((self.game/PLUGIN).read_bytes(),b'observer-v0.3')
        self.assertIn(b'UnityBaseLibrariesSource = 2022.3.62.zip',(self.game/CONFIG).read_bytes())
        self.assertTrue((self.game/CACHE).is_file());self.assertEqual(saved.read_bytes(),b'my-save');self.assertEqual(plugin.read_bytes(),b'other-plugin')
        for name,data in self.build.items():self.assertEqual((self.game/name).read_bytes(),data)
        installed=json.loads((self.game/MANIFEST).read_text());self.assertEqual(installed['owner'],OWNER)
        self.assertFalse(any('HeatSeekar' in x['path'] or '/patchers/' in x['path'] for x in installed['files']))
        self.assertEqual(progress[-1],100);self.assertEqual(progress,sorted(progress))
    def test_running_game_refuses_without_mutation(self):
        before=self.tree()
        with self.assertRaises(InstallError) as caught:self.manager(_process_checker=lambda exe:True).install(self.game)
        self.assertEqual(caught.exception.code,'game_running');self.assertEqual(self.tree(),before)
    def test_starting_game_while_staging_refuses_and_cleans_stage(self):
        checks=[0]
        def running(exe):checks[0]+=1;return checks[0]>=5
        before=self.tree()
        with self.assertRaises(InstallError):self.manager(_process_checker=running).install(self.game)
        self.assertEqual(self.tree(),before);self.assertFalse(list(self.game.glob('.sinisistar-dglab-install-*')))
    @unittest.skipUnless(os.name=='nt','Windows executable share modes')
    def test_commit_holds_a_read_only_exclusive_executable_lock(self):
        observed=[]
        def progress(percent,text):
            if percent!=75:return
            try:(self.game/'SiNiSistar2.exe').read_bytes();observed.append(False)
            except PermissionError:observed.append(True)
        self.manager().install(self.game,progress)
        self.assertEqual(observed,[True]);self.assertEqual((self.game/'SiNiSistar2.exe').read_bytes(),b'fake-exe')
    @unittest.skipUnless(os.name=='nt','Windows executable share modes')
    def test_busy_executable_prevents_commit_and_leaves_files_unchanged(self):
        before=self.tree()
        with (self.game/'SiNiSistar2.exe').open('rb'):
            with self.assertRaises(InstallError) as caught:self.manager().install(self.game)
        self.assertEqual(caught.exception.code,'game_locked');self.assertEqual(self.tree(),before)
    def test_wrong_build_refuses_before_install(self):
        (self.game/'GameAssembly.dll').write_bytes(b'other-build');before=self.tree()
        with self.assertRaises(InstallError) as caught:self.manager().install(self.game)
        self.assertEqual(caught.exception.code,'unsupported');self.assertEqual(self.tree(),before)
    def test_archive_checksum_failure_refuses_without_mutation(self):
        (self.payload/'bepinex-runtime.zip').write_bytes(b'altered-package');before=self.tree()
        with self.assertRaises(InstallError) as caught:self.manager().install(self.game)
        self.assertEqual(caught.exception.code,'payload_invalid');self.assertEqual(self.tree(),before)
    def test_existing_unknown_loader_conflict_is_preflighted(self):
        (self.game/'winhttp.dll').write_bytes(b'other-mod-loader');before=self.tree()
        with self.assertRaises(InstallError) as caught:self.manager().install(self.game)
        self.assertEqual(caught.exception.code,'conflict');self.assertEqual(self.tree(),before)
    def test_user_config_preserved_and_not_claimed_as_owned(self):
        config=self.game/CONFIG;config.parent.mkdir(parents=True);config.write_bytes(b'[MyCustomConfig]\nKeep=true')
        result=self.manager().install(self.game)
        self.assertTrue(result['preserved_config']);self.assertEqual(config.read_bytes(),b'[MyCustomConfig]\nKeep=true')
        manifest=json.loads((self.game/MANIFEST).read_text());self.assertNotIn(CONFIG,[x['path'] for x in manifest['files']])
    def test_idempotent_install_and_missing_file_repair(self):
        manager=self.manager();manager.install(self.game);before=self.tree()
        self.assertEqual(manager.install(self.game)['changed_files'],[]);self.assertEqual(self.tree(),before)
        (self.game/'dotnet/coreclr.dll').unlink();result=manager.install(self.game)
        self.assertEqual(result['changed_files'],['dotnet/coreclr.dll']);self.assertEqual((self.game/'dotnet/coreclr.dll').read_bytes(),b'known-dotnet')
    def test_owned_upgrade_creates_backup(self):
        target=self.game/PLUGIN;target.parent.mkdir(parents=True);target.write_bytes(b'old-observer')
        (self.game/MANIFEST).write_text(json.dumps(dict(owner=OWNER,plugin_version='0.2.0',files=[dict(path=PLUGIN,sha256=digest(b'old-observer'))])))
        result=self.manager().install(self.game);backup=Path(result['backup_dir'])
        self.assertEqual((backup/PLUGIN).read_bytes(),b'old-observer');self.assertEqual(target.read_bytes(),b'observer-v0.3')
    def test_commit_failure_rolls_back_prior_and_new_files(self):
        old=self.game/'winhttp.dll';old.write_bytes(b'old-owned-loader')
        manifest=self.game/MANIFEST;manifest.parent.mkdir(parents=True);manifest.write_text(json.dumps(dict(owner=OWNER,files=[dict(path='winhttp.dll',sha256=digest(old.read_bytes()))])))
        before=self.tree();counter=[0]
        def replace(source,target):
            counter[0]+=1
            if counter[0]==3:raise OSError('fixture disk failure')
            os.replace(source,target)
        with self.assertRaises(InstallError) as caught:self.manager(_replace=replace).install(self.game)
        self.assertEqual(caught.exception.code,'install_failed');self.assertEqual(self.tree(),before)
        self.assertFalse(list(self.game.glob('.sinisistar-dglab-install-*')))
    def test_zip_traversal_is_rejected_before_mutation(self):
        self.package({'../outside.dll':b'bad'});before=self.tree()
        with self.assertRaises(InstallError):self.manager().install(self.game)
        self.assertEqual(self.tree(),before);self.assertFalse((self.root/'outside.dll').exists())
    def test_nested_symlink_cannot_redirect_install(self):
        outside=self.root/'outside';outside.mkdir()
        try:(self.game/'BepInEx').symlink_to(outside,target_is_directory=True)
        except OSError:
            if os.name!='nt':self.skipTest('symlinks unavailable')
            # Windows junction creation does not require Developer Mode.
            # Both verified paths are within this test's temporary directory.
            self.assertTrue(self.game.resolve().is_relative_to(self.root.resolve()))
            self.assertTrue(outside.resolve().is_relative_to(self.root.resolve()))
            result=subprocess.run(['cmd','/c','mklink','/J',str(self.game/'BepInEx'),str(outside)],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode:self.skipTest('junction creation unavailable')
        with self.assertRaises(InstallError) as caught:self.manager().install(self.game)
        self.assertEqual(caught.exception.code,'unsafe_path');self.assertFalse(list(outside.iterdir()))
    def test_discovery_is_bounded_and_skips_development_directories(self):
        ignored=self.root/'.analysis/hidden';ignored.mkdir(parents=True);(ignored/'SiNiSistar2.exe').write_bytes(b'no')
        rows=self.manager().discover_game_dirs(self.root,extra_roots=[])
        self.assertIn(str(self.game.resolve()),[r['game_dir'] for r in rows]);self.assertNotIn(str(ignored),[r['game_dir'] for r in rows])
    def test_ambiguous_parent_needs_explicit_game_folder(self):
        second=self.root/'second/WIN';second.mkdir(parents=True);(second/'SiNiSistar2.exe').write_bytes(b'other')
        with self.assertRaises(InstallError) as caught:normalize_game_dir(self.root)
        self.assertEqual(caught.exception.code,'ambiguous')
