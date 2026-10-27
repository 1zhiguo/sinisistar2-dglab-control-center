"""Native installer workflow/reader rebinding; game mutation belongs to core tests."""
from pathlib import Path
import json,queue,tempfile,time,unittest,hashlib
from unittest.mock import patch
from PySide6.QtGui import QGuiApplication
from sinisistar_dglab.backend import Backend,ROOT
from sinisistar_dglab.monster_catalog import CATALOG

class Reader:
    def __init__(self,directory):self.directory=Path(directory);self.started=False;self.events=queue.Queue()
    def start(self):self.started=True
    def stop(self):self.started=False
    def snapshot(self):return {'source':'bepinex','live':False,'valid':False}
    def recent_events(self,session):return []

class Manager:
    def __init__(self,root):self.root=root;self.inspected=[];self.fail=False;self.running=False;self.installed='';self.install_calls=0
    def payload_info(self):return {'available':True}
    def inspect_game(self,path):
        self.inspected.append(str(path))
        return dict(game_dir=str(self.root),executable=str(self.root/'SiNiSistar2.exe'),telemetry_dir=str(self.root/'BepInEx/plugins/SiNiSistarDGLab/telemetry'),detected=True,supported=True,running=self.running,plugin_version=self.installed,errors=[],warnings=[])
    def discover_game_dirs(self,anchor=None,extra_roots=()):return [self.inspect_game(self.root)]
    def install(self,path,progress=None):
        self.install_calls+=1
        if self.fail:raise RuntimeError('fixture preflight failure')
        if self.running:raise RuntimeError('fixture game is running')
        progress(35,'checking');progress(100,'finished')
        self.installed='0.3.0'
        return dict(success=True,game_dir=str(self.root),telemetry_dir=str(self.root/'BepInEx/plugins/SiNiSistarDGLab/telemetry'),requires_restart=True)

class InstallWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.qt=QGuiApplication.instance() or QGuiApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp');self.root=Path(self.temp.name)/'fresh game with spaces'/'WIN';self.root.mkdir(parents=True)
        self.bundle_patch=patch('sinisistar_dglab.monster_catalog.BUNDLED',Path(self.temp.name)/'no-bundle');self.bundle_patch.start()
        self.b=Backend(offline=True,settings=Path(self.temp.name)/'settings.json');self.b._timer.stop();self.b._install_manager=Manager(self.root)
    def tearDown(self):self.b.shutdown();self.bundle_patch.stop();self.temp.cleanup()
    def settle(self):
        end=time.monotonic()+2
        while self.b.installState['busy'] and time.monotonic()<end:self.b.tick();time.sleep(.005)
        self.b.tick();self.assertFalse(self.b.installState['busy'])
    def test_folder_url_rebinds_reader_and_persists_selected_game(self):
        self.b.offline=False
        with patch('sinisistar_dglab.backend.PluginObserver',Reader):
            self.b.chooseGameDirectory(self.root.as_uri());self.settle()
        self.assertEqual([Path(x) for x in self.b._install_manager.inspected],[self.root])
        self.assertTrue(self.b._observer.started);self.assertEqual(self.b._observer.directory,self.root/'BepInEx/plugins/SiNiSistarDGLab/telemetry')
        self.assertEqual(json.loads(self.b.settings.read_text(encoding='utf-8'))['game_directory'],str(self.root))
    def test_discovery_prefills_candidate_without_installing(self):
        self.b.scanGameDirectories();self.settle()
        self.assertEqual(self.b.installState['selectedPath'],str(self.root));self.assertTrue(self.b.installState['payloadReady'])
        self.assertEqual(len(self.b.gameCandidates),1);self.assertEqual(list(self.root.iterdir()),[])
    def test_worker_success_disarms_both_and_waits_for_real_plugin_loading(self):
        self.b.chooseGameDirectory(str(self.root));self.settle();self.b._armed=True;self.b._ovc_armed=True
        self.b.installGamePlugin();self.settle()
        self.assertFalse(self.b.state['armed']);self.assertFalse(self.b.state['ovcArmed'])
        self.assertEqual(self.b.installState['progress'],100);self.assertTrue(self.b.installState['needsRestart']);self.assertFalse(self.b.installState.get('pluginOnline',False))
    def test_worker_failure_is_reported_without_claiming_install_success(self):
        self.b.chooseGameDirectory(str(self.root));self.settle();self.b._install_manager.fail=True
        self.b.installGamePlugin();self.settle()
        self.assertIn('preflight failure',self.b.installState['error']);self.assertFalse(self.b.installState['needsRestart'])
    def prepare_launch(self):
        (self.root/'SiNiSistar2.exe').write_bytes(b'not an executable; launch is mocked')
        self.b.offline=False
        with patch('sinisistar_dglab.backend.PluginObserver',Reader):
            self.b.chooseGameDirectory(str(self.root));self.settle()
        self.b._game_probe_at=time.monotonic()
    def test_install_then_launch_uses_verified_executable_and_working_directory(self):
        self.prepare_launch();self.b._armed=True;self.b._ovc_armed=True
        with patch('sinisistar_dglab.backend.QProcess.startDetached',return_value=(True,4242)) as launch:
            self.b.installAndLaunchGame();self.settle()
        launch.assert_called_once_with(str(self.root/'SiNiSistar2.exe'),[],str(self.root))
        self.assertEqual(self.b.installState['launchedPid'],4242);self.assertEqual(self.b.installState['installedVersion'],'0.3.0')
        self.assertFalse(self.b._armed);self.assertFalse(self.b._ovc_armed);self.assertFalse(self.b.installState.get('pluginOnline',False))
    def test_install_failure_does_not_launch_and_does_not_leave_a_pending_launch(self):
        self.prepare_launch();self.b._install_manager.fail=True
        with patch('sinisistar_dglab.backend.QProcess.startDetached') as launch:
            self.b.installAndLaunchGame();self.settle()
            self.b._install_manager.fail=False;self.b.installGamePlugin();self.settle()
        launch.assert_not_called();self.assertIsNone(self.b._launch_after_install)
    def test_running_game_is_never_relaunched_or_terminated(self):
        self.prepare_launch();self.b._install_manager.running=True
        with patch('sinisistar_dglab.backend.QProcess.startDetached') as launch:
            self.b.installAndLaunchGame();self.settle()
        launch.assert_not_called();self.assertIn('game is running',self.b.installState['error'])
    def test_launch_failure_preserves_installed_result_without_claiming_online(self):
        self.prepare_launch()
        with patch('sinisistar_dglab.backend.QProcess.startDetached',return_value=(False,0)):
            self.b.installAndLaunchGame();self.settle()
        self.assertEqual(self.b.installState['installedVersion'],'0.3.0');self.assertTrue(self.b.installState['error'])
        self.assertTrue(self.b.installState['needsRestart']);self.assertFalse(self.b.installState.get('pluginOnline',False))
    def test_offline_preview_cannot_install_and_launch(self):
        self.b.chooseGameDirectory(str(self.root));self.settle()
        with patch('sinisistar_dglab.backend.QProcess.startDetached') as launch:self.b.installAndLaunchGame()
        launch.assert_not_called();self.assertEqual(self.b._install_manager.install_calls,0)
    def test_executable_outside_selected_directory_is_not_launched(self):
        self.prepare_launch();info=self.b._install_manager.inspect_game(self.root)
        info['executable']=str(self.root.parent/'SiNiSistar2.exe')
        with patch.object(self.b._install_manager,'inspect_game',return_value=info),patch('sinisistar_dglab.backend.QProcess.startDetached') as launch:
            self.b.installAndLaunchGame();self.settle()
        launch.assert_not_called();self.assertTrue(self.b.installState['error'])

    def cache_result(self):
        cache=Path(self.temp.name)/'generated';cache.mkdir(exist_ok=True)
        key=next(f['id'] for r in self.b._monsters.families for g in r['groups'] for f in g['frames'])
        (cache/'sample.png').write_bytes(b'fixture; rendering is verified by UI integration')
        manifest=dict(schema=1,catalog_sha256=hashlib.sha256(CATALOG.read_bytes()).hexdigest(),images={key:dict(file='sample.png',width=1,height=1)})
        (cache/'manifest.json').write_text(json.dumps(manifest),encoding='utf8')
        return dict(success=True,path=str(cache),images=1,reused=False)

    def test_selection_and_install_both_load_generated_cache_without_import(self):
        result=self.cache_result()
        with patch('sinisistar_dglab.backend.build_monster_cache',return_value=result) as build:
            self.b.chooseGameDirectory(str(self.root));self.settle()
            self.assertTrue(self.b.monsterCacheState['ready']);self.assertEqual(self.b.monsterCatalogSummary['previews'],1)
            self.assertEqual(build.call_args.args[1],self.b.settings.parent/'monster-cache')
            self.b.installGamePlugin();self.settle();self.assertEqual(build.call_count,2)
        self.assertTrue(self.b.monsterCacheState['ready']);self.assertTrue(self.b.installState['needsRestart'])
        self.assertEqual(self.b._install_manager.install_calls,1)
        self.assertFalse(self.b._armed);self.assertFalse(self.b._ovc_armed)
        other=Backend(offline=True,settings=self.b.settings);other._timer.stop()
        try:self.assertEqual(other.monsterCatalogSummary['previews'],1)
        finally:other.shutdown()

    def test_cache_failure_is_separate_from_successful_plugin_install(self):
        with patch('sinisistar_dglab.backend.build_monster_cache',side_effect=RuntimeError('fixture missing resource')):
            self.b.chooseGameDirectory(str(self.root));self.settle()
            self.b.installGamePlugin();self.settle()
        self.assertFalse(self.b.monsterCacheState['ready']);self.assertIn('fixture missing resource',self.b.monsterCacheState['error'])
        self.assertEqual(self.b.installState['installedVersion'],'0.3.0');self.assertEqual(self.b.installState['error'],'')
        self.assertFalse(self.b.installState.get('pluginOnline',False))

    def test_preview_generation_progress_does_not_end_install_task_early(self):
        self.b._install_state.update(busy=True,phase='install')
        self.b._install_queue.put(('cache_progress',dict(progress=50,overall=88,message='generating')))
        self.b._poll_installer()
        self.assertTrue(self.b.installState['busy']);self.assertTrue(self.b.monsterCacheState['busy'])
        self.assertEqual(self.b.installState['progress'],88)

    def test_packaged_previews_make_directory_selection_and_install_skip_extraction(self):
        self.bundle_patch.stop();self.b._monsters.reload()
        self.assertTrue(self.b._monsters.bundled_complete)
        with patch('sinisistar_dglab.backend.build_monster_cache') as build:
            self.b.chooseGameDirectory(str(self.root));self.settle()
            self.assertTrue(self.b.monsterCacheState['ready']);self.assertEqual(self.b.monsterCatalogSummary['previews'],3571)
            self.b.installGamePlugin();self.settle();build.assert_not_called()
        self.assertTrue(self.b.monsterCacheState['reused'])

    def test_explicit_game_update_still_runs_and_failure_keeps_packaged_images(self):
        self.bundle_patch.stop();self.b._monsters.reload()
        result=self.cache_result()
        with patch('sinisistar_dglab.backend.build_monster_cache',return_value=result) as build:
            self.b.generateMonsterPreviews();self.settle()
            self.assertTrue(build.call_args.kwargs['force'])
            self.assertEqual(self.b.monsterCatalogSummary['previews'],3571)
            self.assertEqual(self.b.monsterCatalogSummary['local_previews'],1)
        with patch('sinisistar_dglab.backend.build_monster_cache',side_effect=RuntimeError('fixture update failure')):
            self.b.generateMonsterPreviews();self.settle()
        self.assertTrue(self.b.monsterCacheState['ready']);self.assertIn('fixture update failure',self.b.monsterCacheState['error'])
        self.assertEqual(self.b.monsterCatalogSummary['previews'],3571)
