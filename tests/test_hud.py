import math,tempfile,unittest
from copy import deepcopy
from pathlib import Path
from PySide6.QtCore import QObject,QRect
from PySide6.QtGui import QGuiApplication
from sinisistar_dglab.hud_settings import sanitize_hud,HUD_DEFAULTS
from sinisistar_dglab.hud_window import GameViewport,hud_geometry,hud_dialogue_hidden,logical_client_rect,screen_for_viewport

class Preferences(unittest.TestCase):
    def test_ranges_invalid_values_and_legacy_defaults(self):
        r=sanitize_hud(dict(scale=900,opacity=-1,x=float('nan'),layout='bad',show_pulse=False,show_vibration=False,show_a=False,show_b=False))
        self.assertEqual(r['scale'],150);self.assertEqual(r['opacity'],30);self.assertEqual(r['x'],50)
        self.assertTrue(r['show_pulse']);self.assertTrue(r['show_a']);self.assertEqual(r['layout'],'player')
    def test_non_bool_visibility_does_not_hide_a_module(self):
        r=sanitize_hud({'show_resources':'false','scale':True})
        self.assertFalse(r['show_resources']);self.assertEqual(r['scale'],100)
    def test_legacy_debug_position_does_not_clip_the_new_panels(self):
        r=sanitize_hud(dict(anchor='custom',x=0,y=0,show_vibration=False,show_resources=True))
        self.assertEqual(r['anchor'],'bottom_center');self.assertNotIn('ovc_anchor',r)
        self.assertTrue(r['show_vibration']);self.assertFalse(r['show_resources'])
    def test_all_anchors_stay_inside_client_including_oversize_hud(self):
        rect=QRect(-1000,50,1280,720)
        for anchor in ('auto','top_left','top_center','top_right','bottom_left','bottom_center','bottom_right','custom'):
            for size in ((480,300),(2000,1200)):
                result=hud_geometry(rect,*size,dict(version=3,anchor=anchor,x=100,y=100))
                self.assertTrue(rect.contains(result),str((anchor,size,result)))
    def test_default_single_strip_is_bottom_center(self):
        client=QRect(0,0,1920,1080)
        strip=hud_geometry(client,812,116,{})
        self.assertEqual(strip.x(),554);self.assertEqual(strip.bottom(),1059)
    def test_channel_toggles_and_legacy_two_panel_settings_migrate(self):
        old=sanitize_hud(dict(version=2,show_a=False,show_b=True,show_pulse=True,show_vibration=True))
        self.assertFalse(old['pulse_a']);self.assertFalse(old['ovc_a']);self.assertTrue(old['pulse_b']);self.assertTrue(old['ovc_b'])
        current=sanitize_hud(dict(version=3,pulse_a=False,pulse_b=False,ovc_a=True,ovc_b=False))
        self.assertFalse(current['show_pulse']);self.assertTrue(current['show_vibration'])
        self.assertEqual(sum(current[k] for k in ('pulse_a','pulse_b','ovc_a','ovc_b')),1)
        empty=sanitize_hud(dict(version=3,pulse_a=False,pulse_b=False,ovc_a=False,ovc_b=False))
        self.assertFalse(any(empty[k] for k in ('pulse_a','pulse_b','ovc_a','ovc_b')))
    def test_custom_strip_position_is_clamped(self):
        p=dict(version=3,anchor='custom',x=10,y=90)
        client=QRect(-1000,0,1000,800)
        strip=hud_geometry(client,812,116,p)
        self.assertTrue(client.contains(strip));self.assertEqual(strip.x(),-981)
    def test_dialogue_request_and_playing_hide_but_current_death_does_not(self):
        s=dict(pluginFresh=True,valid=True,hp=100,hudDialogueActive=True,flow={})
        self.assertTrue(hud_dialogue_hidden(s,{}))
        s.update(hudDialogueActive=False,eventPlaying=True,flow={'playing':True})
        self.assertTrue(hud_dialogue_hidden(s,{}))
        s['hp']=0;self.assertFalse(hud_dialogue_hidden(s,{}))
        s.update(hp=100,flow={'playing':True,'defeat_confirmed':True})
        self.assertFalse(hud_dialogue_hidden(s,{}))
        s.update(hp=1,flow={'playing':True},penaltyClassification='struggle_penalty')
        self.assertFalse(hud_dialogue_hidden(s,{}))
        s.pop('penaltyClassification')
        s.update(flow={},pluginFresh=False);self.assertFalse(hud_dialogue_hidden(s,{}))
        s.update(pluginFresh=True);self.assertFalse(hud_dialogue_hidden(s,dict(version=3,hide_dialogue=False)))
    def test_mixed_dpi_negative_monitor_client_conversion(self):
        class Screen:
            def devicePixelRatio(self):return 1.5
            def geometry(self):return QRect(-1280,0,1280,720)
            def name(self):return 'screen'
        screen=Screen();v=GameViewport(-1770,150,1200,900,-1920,0,'screen',1920,1080)
        self.assertIs(screen_for_viewport(v,[screen]),screen)
        self.assertEqual(logical_client_rect(v,screen),QRect(-1180,100,800,600))

class BackendPreferences(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QGuiApplication.instance() or QGuiApplication([])
    def test_hud_starts_enabled_and_remembers_explicit_switch_without_arming(self):
        from sinisistar_dglab.backend import Backend,ROOT
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as temp:
            path=Path(temp)/'settings.json';b=Backend(offline=True,settings=path)
            try:
                self.assertTrue(b.state['hud']);self.assertTrue(b.hudSettings['enabled'])
                b.setHudAdjusting(True);b.setHudSetting('enabled',False)
                self.assertFalse(b.hudAdjusting);self.assertFalse(b.state['hud'])
                other=Backend(offline=True,settings=path)
                try:
                    self.assertFalse(other.state['hud']);other.toggleHud()
                    self.assertTrue(other.state['hud']);self.assertTrue(other.hudSettings['enabled'])
                    self.assertFalse(other._armed);self.assertFalse(other._ovc_armed)
                finally:other.shutdown()
            finally:b.shutdown()
    def test_display_changes_do_not_disarm_or_reset_pulse(self):
        from sinisistar_dglab.backend import Backend
        root=Path(__file__).resolve().parents[1]/'artifacts/test-temp';root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as temp:
            b=Backend(offline=True,settings=Path(temp)/'settings.json')
            try:
                b._armed=True;b._warm=5;sentinel={'sample_id':10};b._pulse_planner.engine.previous=sentinel
                profile=deepcopy(b._sim_profile)
                b.setHudSetting('opacity',60);b.setHudSetting('scale',110);b.setHudAdjusting(True)
                self.assertTrue(b._armed);self.assertEqual(b._warm,5);self.assertIs(b._pulse_planner.engine.previous,sentinel)
                self.assertEqual(b._sim_profile,profile)
                b.saveHudPosition(200,100,0,0,1000,800,500,400)
                self.assertEqual(b.hudSettings['anchor'],'custom');self.assertEqual(b.hudSettings['x'],40)
                b.setHudSetting('ovc_b',False)
                other=Backend(offline=True,settings=b.settings)
                try:
                    self.assertEqual(other.hudSettings['opacity'],60);self.assertEqual(other.hudSettings['scale'],110)
                    self.assertFalse(other.hudSettings['ovc_b']);self.assertEqual(other.hudSettings['x'],40)
                finally:other.shutdown()
            finally:b.shutdown()
    def test_single_qml_strip_hides_for_dialogue_and_remains_for_death(self):
        import time
        from PySide6.QtCore import QUrl
        from PySide6.QtQml import QQmlApplicationEngine
        from sinisistar_dglab.backend import Backend
        from sinisistar_dglab.hud_window import HudWindowController
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=root/'artifacts/test-temp') as temp:
            b=Backend(offline=True,settings=Path(temp)/'settings.json');b._timer.stop();b._hud=True
            b._live=dict(live=True,valid=True,pid=123,player=456,sampled_at=time.monotonic(),hp={'current':100,'max':100},event_playing=False,flow={})
            engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',b)
            engine.load(QUrl.fromLocalFile(str(root/'src/sinisistar_dglab/qml/Monitor.qml')))
            self.assertEqual(len(engine.rootObjects()),1)
            controller=HudWindowController(b,engine.rootObjects()[0],viewport_reader=lambda pid:GameViewport(0,0,1280,720))
            def live_tick():
                # QML cold compilation is not a game tick. Present a fresh
                # synthetic heartbeat for each scenario, even on a busy host.
                b._live['sampled_at']=time.monotonic();controller.tick()
            try:
                live_tick();self.assertEqual(set(controller.panels),{'strip'})
                self.assertIsNone(engine.rootObjects()[0].findChild(QObject,'ovcOutputHud'))
                self.assertTrue(all(window.isVisible() for window in controller.panels.values()))
                b._live['event_playing']=True;live_tick()
                self.assertFalse(any(window.isVisible() for window in controller.panels.values()))
                b._live['hp']['current']=0;live_tick()
                self.assertTrue(all(window.isVisible() for window in controller.panels.values()))
                for key in ('pulse_a','pulse_b','ovc_a','ovc_b'):b.setHudSetting(key,False)
                live_tick();self.assertFalse(engine.rootObjects()[0].isVisible())
                b.setHudSetting('ovc_b',True);controller.tick()
                live_tick();self.assertTrue(engine.rootObjects()[0].isVisible())
            finally:controller.shutdown();b.shutdown()
