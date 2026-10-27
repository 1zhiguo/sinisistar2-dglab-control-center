"""Helper IPC contract tests; no live game writes or device services."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
import json,tempfile,time,unittest
from PySide6.QtGui import QGuiApplication
from sinisistar_dglab.trainer import TrainerBridge,decode_snapshot,install_trainer
from sinisistar_dglab.telemetry import BUILD,ROOT
from sinisistar_dglab.telemetry import TYPES

STATUS_IDS={name:int(raw) for raw,name in TYPES['AbnormalType'].items()}

def state(**changes):
    data=dict(schema=1,source='bepinex-trainer',fingerprint=BUILD,session='a'*32,pid=123,player=456,
              utc=datetime.now(timezone.utc).isoformat(),valid=True,can_edit=True,
              hp=dict(current=80,max=100),mp=dict(current=70,max=100),attack_multiplier=1.,attack_available=True)
    data.update(changes);return data

class TrainerContract(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp');self.directory=Path(self.temp.name)
        self.bridge=TrainerBridge();self.publish(state())
    def tearDown(self):self.temp.cleanup()
    def publish(self,data):
        (self.directory/'latest.json').write_text(json.dumps(data),encoding='utf-8');self.bridge.poll(self.directory)
    def reply(self,**changes):
        c=self.bridge.pending
        result={k:c[k] for k in ('id','session','pid','player','attribute')}
        result.update(ok=True,before=80,after=70,max=100);result.update(changes)
        (self.directory/'result.json').write_text(json.dumps(result),encoding='utf-8');self.bridge.poll(self.directory)
    def test_fresh_game_snapshot_is_required(self):
        for changes in [dict(utc=(datetime.now(timezone.utc)-timedelta(seconds=2)).isoformat()),dict(fingerprint='wrong'),dict(can_edit='false'),dict(pid=True),dict(hp=dict(current=101,max=100)),dict(attack_persistent='false')]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):decode_snapshot(state(**changes))
    def test_hp_mp_both_signed_directions_and_direct_values_use_expiring_identity(self):
        for attribute,mode,value in [('hp','add',10),('hp','add',-10),('mp','add',10),('mp','add',-10),('hp','set',0),('mp','set',100)]:
            with self.subTest(attribute=attribute,mode=mode,value=value):
                self.bridge.pending=None;self.bridge.send(attribute,mode,value)
                c=json.loads((self.directory/'command.json').read_text())
                self.assertEqual((c['attribute'],c['mode'],c['value']),(attribute,mode,value))
                self.assertEqual((c['session'],c['pid'],c['player']),('a'*32,123,456))
                self.assertLess((datetime.fromisoformat(c['expires_utc'])-datetime.now(timezone.utc)).total_seconds(),4.1)
    def test_attack_can_be_lowered_raised_zeroed_and_reset(self):
        for mode,value in [('add',-.25),('add',.25),('set',.5),('set',0),('set',10),('reset',0)]:
            self.bridge.pending=None;self.bridge.send('attack',mode,value)
            self.assertEqual(self.bridge.pending['value'],value)
    def test_invalid_values_and_unavailable_attack_do_not_write(self):
        for attribute,mode,value in [('hp','add',1.5),('mp','set',float('nan')),('attack','set',11),('attack','set',-1),('mp','reset',0),('unknown','set',1)]:
            with self.subTest(attribute=attribute,mode=mode,value=value),self.assertRaises(ValueError):self.bridge.send(attribute,mode,value)
        self.publish(state(attack_available=False))
        with self.assertRaises(ValueError):self.bridge.send('attack','set',2)
        self.assertFalse((self.directory/'command.json').exists())
    def test_single_pending_request_and_game_acknowledged_readback(self):
        self.bridge.send('hp','add',-10)
        with self.assertRaises(ValueError):self.bridge.send('hp','add',-10)
        self.reply();self.assertIsNone(self.bridge.pending);self.assertIn('80 → 70',self.bridge.message)
    def test_wrong_or_malformed_ack_cannot_claim_success(self):
        self.bridge.send('hp','add',-10)
        for changes in [dict(id='other'),dict(player=999),dict(attribute='mp'),dict(after=None),dict(after=1000)]:
            self.reply(**changes);self.assertIsNotNone(self.bridge.pending)
        self.reply();self.assertIsNone(self.bridge.pending)
    def test_game_error_is_reported_without_retry(self):
        self.bridge.send('mp','add',-10);original=(self.directory/'command.json').read_bytes()
        self.reply(ok=False,error='游戏拒绝');self.assertIsNone(self.bridge.pending);self.assertEqual(self.bridge.error,'游戏拒绝')
        self.bridge.poll(self.directory);self.assertEqual((self.directory/'command.json').read_bytes(),original)
    def test_new_player_cancels_old_request(self):
        self.bridge.send('hp','add',10);self.publish(state(player=999))
        self.assertIsNone(self.bridge.pending);self.assertIn('已取消',self.bridge.error)
    def test_timeout_never_resends_and_stale_state_blocks_mutation(self):
        self.bridge.send('hp','add',10);before=(self.directory/'command.json').read_bytes()
        self.bridge.deadline=time.monotonic()-1;self.bridge.poll(self.directory)
        self.assertIsNone(self.bridge.pending);self.assertIn('超时',self.bridge.error)
        self.assertEqual((self.directory/'command.json').read_bytes(),before)
        self.publish(state(utc=(datetime.now(timezone.utc)-timedelta(seconds=2)).isoformat()))
        with self.assertRaises(ValueError):self.bridge.send('hp','add',10)
    def test_old_helper_cannot_receive_status_removal_commands(self):
        with self.assertRaises(ValueError):self.bridge.send('abnormal','remove',STATUS_IDS['Poison'])
        self.assertFalse((self.directory/'command.json').exists())
    def test_current_statuses_are_chinese_and_bulk_count_excludes_blessing(self):
        self.publish(state(status_removal_available=True,abnormals=[dict(type_raw=STATUS_IDS['Poison'],level=3),dict(type_raw=STATUS_IDS['InfertilityBlessing'],level=1)]))
        rows=self.bridge.state['abnormals'];self.assertEqual(rows[0]['label'],'中毒')
        self.assertEqual(self.bridge.state['negative_count'],1);self.assertTrue(rows[1]['positive'])
    def test_title_screen_cached_statuses_are_not_current_player_statuses(self):
        self.publish(state(valid=False,can_edit=False,player=0,status_removal_available=True,
                           abnormals=[dict(type_raw=STATUS_IDS['Poison'],level=1)]))
        self.assertTrue(self.bridge.state['online']);self.assertEqual(self.bridge.state['abnormals'],[])
        self.assertEqual(self.bridge.state['negative_count'],0)
        with self.assertRaises(ValueError):self.bridge.send('abnormals','clear_negative',0)
    def test_remove_and_clear_requests_are_bound_to_current_types_and_player(self):
        self.publish(state(status_removal_available=True,abnormals=[dict(type_raw=STATUS_IDS['Poison'],level=3),dict(type_raw=STATUS_IDS['InfertilityBlessing'],level=1)]))
        self.bridge.send('abnormal','remove',STATUS_IDS['Poison'])
        self.assertEqual(self.bridge.pending['attribute'],'abnormal');self.assertEqual(self.bridge.pending['mode'],'remove')
        self.reply(before=1,after=0,removed_types=[STATUS_IDS['Poison']]);self.assertIn('已解除 1 种',self.bridge.message)
        self.bridge.send('abnormals','clear_negative',0);self.assertEqual(self.bridge.pending['value'],0)
        self.reply(before=1,after=0);self.assertIsNone(self.bridge.pending)
        self.bridge.send('abnormal','remove',STATUS_IDS['InfertilityBlessing']);self.assertIsNotNone(self.bridge.pending)
    def test_invalid_status_codes_and_modes_are_rejected(self):
        self.publish(state(status_removal_available=True,abnormals=[dict(type_raw=STATUS_IDS['Poison'],level=1)]))
        for attribute,mode,value in [('abnormal','remove',999),('abnormal','remove',.5),('abnormal','set',STATUS_IDS['Poison']),('abnormals','clear_negative',1),('abnormals','remove',0)]:
            with self.subTest(attribute=attribute,mode=mode,value=value),self.assertRaises(ValueError):self.bridge.send(attribute,mode,value)
        self.assertFalse((self.directory/'command.json').exists())
    def test_status_readback_must_confirm_absence_and_partial_failure_is_visible(self):
        self.publish(state(status_removal_available=True,abnormals=[dict(type_raw=STATUS_IDS['Poison'],level=1)]))
        self.bridge.send('abnormal','remove',STATUS_IDS['Poison']);self.reply(before=1,after=1)
        self.assertIsNotNone(self.bridge.pending)
        self.reply(ok=False,before=1,after=1,error='状态仍存在或被重新施加')
        self.assertIsNone(self.bridge.pending);self.assertIn('仍存在',self.bridge.error)

class TrainerBackend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QGuiApplication.instance() or QGuiApplication([])
    def test_modifying_game_values_disarms_both_routes_and_blocks_arm_until_ack(self):
        from sinisistar_dglab.backend import Backend
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as temp:
            b=Backend(offline=True,settings=Path(temp)/'settings.json');b._timer.stop();b.offline=False
            b._game_directory=Path(temp)/'game';ipc=b._game_directory/'BepInEx/plugins/SiNiSistarTrainer/ipc';ipc.mkdir(parents=True)
            (ipc/'latest.json').write_text(json.dumps(state()),encoding='utf-8')
            try:
                b._armed=True;b._ovc_armed=True;b.modifyGameValue('hp','add',-10)
                self.assertFalse(b._armed);self.assertFalse(b._ovc_armed);self.assertTrue(b.trainerState['pending'])
                b.toggleArm();b.toggleOvcArm();self.assertFalse(b._armed);self.assertFalse(b._ovc_armed)
            finally:b.shutdown()
    def test_offline_ui_never_writes_game_commands(self):
        from sinisistar_dglab.backend import Backend
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as temp:
            b=Backend(offline=True,settings=Path(temp)/'settings.json')
            try:
                with patch.object(b._trainer,'send') as send:b.modifyGameValue('hp','set',100);send.assert_not_called()
            finally:b.shutdown()

class TrainerInstall(unittest.TestCase):
    def test_optional_install_preserves_observer_and_saves_and_detects_reinstall(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as temp:
            root=Path(temp);(root/'BepInEx/core').mkdir(parents=True)
            (root/'BepInEx/core/BepInEx.Unity.IL2CPP.dll').write_bytes(b'fixture')
            observer=root/'BepInEx/plugins/observer.dll';observer.parent.mkdir(parents=True);observer.write_bytes(b'unchanged')
            save=root/'save.dat';save.write_bytes(b'progress')
            with patch('sinisistar_dglab.install_manager.InstallManager.inspect_game',return_value=dict(supported=True,errors=[],running=True)):
                self.assertIn('已安装',install_trainer(root));self.assertIn('已安装',install_trainer(root))
                target=root/'BepInEx/plugins/SiNiSistarTrainer/SiNiSistarDGLab.Trainer.dll';self.assertTrue(target.is_file())
                target.write_bytes(b'unknown')
                with self.assertRaises(ValueError):install_trainer(root)
            self.assertEqual(observer.read_bytes(),b'unchanged');self.assertEqual(save.read_bytes(),b'progress')
    def test_unsupported_build_is_rejected(self):
        with patch('sinisistar_dglab.install_manager.InstallManager.inspect_game',return_value=dict(supported=False,errors=['wrong'])):
            with self.assertRaises(ValueError):install_trainer(ROOT/'artifacts/test-temp')
    def test_known_old_helper_can_upgrade_only_when_game_closed_and_is_backed_up(self):
        import hashlib
        old=b'known old helper fixture';old_hash=hashlib.sha256(old).hexdigest()
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as temp:
            root=Path(temp);(root/'BepInEx/core').mkdir(parents=True)
            (root/'BepInEx/core/BepInEx.Unity.IL2CPP.dll').write_bytes(b'fixture')
            target=root/'BepInEx/plugins/SiNiSistarTrainer/SiNiSistarDGLab.Trainer.dll';target.parent.mkdir(parents=True);target.write_bytes(old)
            with patch('sinisistar_dglab.trainer.KNOWN_OLD_TRAINERS',frozenset((old_hash,))):
                with patch('sinisistar_dglab.install_manager.InstallManager.inspect_game',return_value=dict(supported=True,errors=[],running=True)):
                    with self.assertRaises(ValueError):install_trainer(root)
                self.assertEqual(target.read_bytes(),old)
                with patch('sinisistar_dglab.install_manager.InstallManager.inspect_game',return_value=dict(supported=True,errors=[],running=False)):
                    install_trainer(root)
                self.assertNotEqual(target.read_bytes(),old)
                self.assertEqual((target.parent/'backups'/f'{old_hash}.bak').read_bytes(),old)
    def test_malformed_status_snapshot_is_rejected(self):
        for item in [dict(type_raw=True,level=1),dict(type_raw=2**32,level=1),dict(type_raw=1,level=0),dict(type_raw=1,level='3')]:
            with self.subTest(item=item),self.assertRaises(ValueError):decode_snapshot(state(status_removal_available=True,abnormals=[item]))
