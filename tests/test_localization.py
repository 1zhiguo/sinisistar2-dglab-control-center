from copy import deepcopy
from pathlib import Path
import tempfile,unittest,json,re
from PySide6.QtGui import QGuiApplication
from sinisistar_dglab.backend import Backend,ROOT
from sinisistar_dglab.localization import Localizer
from sinisistar_dglab.tutorial import steps

class Localization(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QGuiApplication.instance() or QGuiApplication([])
    def test_catalog_pair_covers_existing_ui_sources(self):
        loc=Localizer();self.assertEqual(set(loc.catalogs['en']),set(loc.catalogs['ja']))
        for lang in ('en','ja'):
            self.assertGreater(len(loc.catalogs[lang]),1000)
            for source in ('总览','设备与游戏','CG 反馈','新手教程','保存快捷键','本机模拟 APP · 使用当前预设'):
                self.assertNotEqual(loc.translate(source,lang),source)
        self.assertEqual(loc.translate('Ctrl+F12','en'),'Ctrl+F12')
        self.assertEqual(loc.translate('APP 中','en'),'APP 中') # Never replace 中 inside an unknown phrase with Medium.
        self.assertEqual(loc.translate('游戏已暂停','ja'),'ゲームは一時停止中')
    def test_language_tutorial_and_custom_names_persist_without_strategy_changes(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as folder:
            b=Backend(offline=True,settings=Path(folder)/'settings.json');b._timer.stop()
            try:
                original=deepcopy(b._sim_profile);b._armed=b._ovc_armed=True
                b._waves.append(dict(key='custom_test',name='我的波形',points=[0,1]))
                b.setLanguage('en');self.assertEqual(b.translate('我的波形','en'),'我的波形')
                self.assertEqual(b._sim_profile,original);self.assertTrue(b._armed and b._ovc_armed)
                b.saveTutorial(3,False);self.assertTrue(b._armed and b._ovc_armed)
                other=Backend(offline=True,settings=b.settings);other._timer.stop()
                try:self.assertEqual(other.language,'en');self.assertEqual(other.tutorialState['step'],3)
                finally:other.shutdown()
                b.setLanguage('invalid');self.assertEqual(b.language,'en')
            finally:b.shutdown()
    def test_all_tutorial_steps_are_localized_and_have_safe_navigation_targets(self):
        for lang in ('zh-CN','en','ja'):
            rows=steps(lang);self.assertEqual(len(rows),5)
            self.assertEqual([r['page'] for r in rows],[1,1,1,2,2])
            self.assertTrue(all(r['title'] and r['body'] for r in rows))
            if lang=='en':self.assertFalse(any(re.search('[\u4e00-\u9fff]',r['body'])for r in rows))
    def test_old_tutorial_progress_restarts_with_five_steps(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as folder:
            settings=Path(folder)/'settings.json'
            settings.write_text(json.dumps(dict(tutorial=dict(step=8,seen=True,completed=True))),encoding='utf-8')
            b=Backend(offline=True,settings=settings);b._timer.stop()
            try:
                self.assertEqual(b.tutorialState['step'],0);self.assertFalse(b.tutorialState['completed'])
                self.assertEqual(b.tutorialState['version'],2)
                b.saveTutorial(99,False);self.assertEqual(b.tutorialState['step'],4)
            finally:b.shutdown()
