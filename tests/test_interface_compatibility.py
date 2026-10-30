"""Unknown channel builds require an actual current runtime contract report."""
from copy import deepcopy
from datetime import datetime,timezone
import json,struct,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from sinisistar_dglab.game_builds import CONTRACT_ID,CONTRACT_SHA256,compatible_snapshot,candidate_checks
from sinisistar_dglab.install_manager import InstallManager,EXPECTED_BUILD,ROOT
from sinisistar_dglab.plugin_bridge import PluginObserver
from sinisistar_dglab.cg_playback import fresh,describe_game_cg
from cg_fixture import event_state

def report(data):
    return dict(schema=1,contract=CONTRACT_ID,contract_sha256=CONTRACT_SHA256,status='compatible',fingerprint=data['fingerprint'],pid=data['pid'],session=data['session'],errors=[])

def candidate(root):
    pe=bytearray(256);pe[:2]=b'MZ';struct.pack_into('<I',pe,60,128);pe[128:132]=b'PE\0\0';struct.pack_into('<H',pe,132,0x8664);struct.pack_into('<H',pe,152,0x20b)
    for name in EXPECTED_BUILD:
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True)
        if name.endswith('.dat'):p.write_bytes(struct.pack('<II',0xfab11baf,31)+b'SiNiSistar2.Manager\0ManagerList\0Lelia\0EventManager\0GaTakePlayer\0')
        else:p.write_bytes(pe)
    with (root/'UnityPlayer.dll').open('ab') as f:f.write(b'2022.3.62f2')
    with (root/'GameAssembly.dll').open('ab') as f:f.write(b'il2cpp_domain_get\0il2cpp_class_from_name\0il2cpp_field_get_type\0il2cpp_method_get_return_type\0')
    return {name:root/name for name in EXPECTED_BUILD}

class InterfaceCompatibility(unittest.TestCase):
    def test_other_channel_live_heartbeat_and_cg_pass_current_contract(self):
        data=dict(schema=1,source='bepinex',fingerprint='a'*64,pid=42,session='test',sample_id=1,utc=datetime.now(timezone.utc).isoformat(),scene_id=19,valid=False,abnormals=[])
        data['compatibility']=report(data)
        state=PluginObserver.decode(data);self.assertTrue(state['live']);self.assertTrue(fresh(state,time.monotonic()))
        cg=event_state();cg['fingerprint']=data['fingerprint'];cg['compatibility']=report(cg)
        self.assertTrue(describe_game_cg(cg,10)['recognized'])
    def test_claimed_compatible_without_exact_contract_or_session_is_rejected(self):
        data=dict(fingerprint='a'*64,pid=1,session='one');data['compatibility']=report(data)
        for field,value in [('status','incompatible'),('contract_sha256','bad'),('errors',['missing HP']),('pid',2),('session','old'),('fingerprint','b'*64),('contract','other')]:
            with self.subTest(field=field):
                row=deepcopy(data);row['compatibility'][field]=value;self.assertFalse(compatible_snapshot(row))
        row=deepcopy(data);row.pop('compatibility');self.assertFalse(compatible_snapshot(row))
    def test_known_hash_cannot_override_failed_interface_probe(self):
        from sinisistar_dglab.telemetry import BUILD
        row=dict(fingerprint=BUILD,pid=1,session='test');row['compatibility']=report(row);row['compatibility']['status']='incompatible'
        self.assertFalse(compatible_snapshot(row))
    def test_candidate_is_installable_without_claiming_runtime_verified(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as tmp:
            root=Path(tmp);candidate(root);manager=InstallManager(_process_checker=lambda _:False)
            before={p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}
            result=manager.inspect_game(root)
            self.assertTrue(result['supported']);self.assertEqual(result['build_profile'],'interface-pending');self.assertFalse(result['interface_verified'])
            self.assertEqual(before,{p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()})
    def test_loader_checks_reject_wrong_engine_architecture_and_metadata(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as tmp:
            root=Path(tmp)
            for change in ('engine','arch','metadata','game','exports','missing'):
                with self.subTest(change=change):
                    paths=candidate(root)
                    if change=='engine':paths['UnityPlayer.dll'].write_bytes(paths['UnityPlayer.dll'].read_bytes().replace(b'2022.3.62f2',b'2021.3.62f2'))
                    if change=='arch':
                        value=bytearray(paths['GameAssembly.dll'].read_bytes());struct.pack_into('<H',value,132,0x14c);paths['GameAssembly.dll'].write_bytes(value)
                    if change=='metadata':paths[next(n for n in paths if n.endswith('.dat'))].write_bytes(b'corrupt')
                    if change=='game':paths[next(n for n in paths if n.endswith('.dat'))].write_bytes(struct.pack('<II',0xfab11baf,31)+b'OtherGame')
                    if change=='exports':paths['GameAssembly.dll'].write_bytes(paths['SiNiSistar2.exe'].read_bytes())
                    if change=='missing':paths['GameAssembly.dll'].unlink()
                    self.assertTrue(candidate_checks(paths));self.assertFalse(InstallManager().inspect_game(root)['supported'])
    def test_optional_mutation_helper_stays_pinned_for_unknown_channels(self):
        from sinisistar_dglab.trainer import install_trainer
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as tmp:
            candidate(Path(tmp))
            with self.assertRaisesRegex(ValueError,'游戏辅助接口'):install_trainer(tmp)
