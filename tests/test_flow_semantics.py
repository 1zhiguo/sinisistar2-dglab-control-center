"""Review must preserve uncertainty and cannot alter live strategies or arming."""
from copy import deepcopy
import csv,json,tempfile,unittest
from pathlib import Path
from PySide6.QtGui import QGuiApplication
from sinisistar_dglab.backend import Backend
from sinisistar_dglab.flow_semantics import FlowReview,describe_runtime,describe_static,describe_scene,symbol_meaning
from sinisistar_dglab.telemetry import ROOT

def flow(scene,group,name,kind='HierarchyEventPlayer'):
    return dict(key=json.dumps([scene,group,name,kind]),name=name,scene='test',labels=['Portrait'])

class FlowSemantics(unittest.TestCase):
    def test_verified_recovery_not_confused_with_intro_or_other_scene(self):
        start=describe_runtime(flow(166,'Continue','StartGacha'))
        end=describe_runtime(flow(166,'Continue','Success'))
        self.assertEqual(start['semantic_category'],'可恢复战败')
        self.assertEqual(end['semantic_category'],'恢复 / 挣脱')
        self.assertEqual(describe_runtime(flow(166,'BossAppear','TriggerEvent'))['semantic_family'],'ordinary')
        self.assertEqual(describe_runtime(flow(28,'Continue','StartGacha'))['semantic_family'],'recoverable_candidate')
        self.assertNotEqual(describe_runtime(flow(166,'Continue','StartGacha','OtherPlayer'))['semantic_family'],'recoverable')

    def test_boss_death_chain_and_victory_are_different(self):
        for scene,group,name in [(28,'LeechBossEvent','Start'),(28,'LeechBossEvent','Died'),(29,'Event','Default'),(30,'Event','Default')]:
            r=describe_runtime(flow(scene,group,name));self.assertEqual(r['semantic_family'],'boss_defeat')
            self.assertIn('待核验',r['semantic_evidence']);self.assertIn('不能仅靠 HP',r['semantic_boundary'])
        self.assertEqual(describe_runtime(flow(28,'','BossDead'))['semantic_family'],'ordinary')
        self.assertEqual(describe_runtime(flow(3,'','DiedKeeper'))['semantic_family'],'unknown')

    def test_static_symbols_do_not_claim_runtime_order_or_official_names(self):
        r=describe_static(dict(enemy='Zombie',states=[dict(name='HoldEnd')],tasks=['TaskHoldCancel'],animations=[],animation_fields=[]))
        self.assertIn('工作译名',r['semantic_limit']);self.assertIn('不证明运行时顺序',r['semantic_boundary'])
        self.assertIn('未核验',r['semantic_evidence']);self.assertIn('HoldEnd',r['semantic_symbols'])
        self.assertNotEqual(symbol_meaning('HoldCancel'),symbol_meaning('HoldRelease'))
        capture=describe_runtime(dict(key='["capture",48,"Zombie","zero_hp"]'))
        self.assertEqual(capture['semantic_family'],'zero_hp_capture');self.assertIn('不是精确动画',capture['semantic_evidence'])

    def test_pigpen_scene167_is_candidate_even_after_scene166_was_seen(self):
        r=describe_scene(dict(scene='Road_2_2_Livestock_go',scene_id=167,line=30956),[flow(166,'Continue','StartGacha')])
        self.assertIn('未在当前实机目录出现',r['semantic_evidence']);self.assertEqual(r['key'],'scene:167')
        seen=describe_scene(dict(scene='Road_2_2_Livestock_go',scene_id=167),[flow(167,'Event','Main')])
        self.assertIn('已在实机目录出现',seen['semantic_evidence'])
        self.assertEqual(describe_runtime(flow(167,'Event','Main'))['semantic_family'],'regional_go')
        self.assertIn('非玩家死亡',describe_runtime(flow(166,'Continue','EnemyDeadForSuperBreast'))['semantic_category'])

    def test_bulk_only_known_keys_persist_and_export_with_reset(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as tmp:
            p=Path(tmp)/'review.json';review=FlowReview(p);a=flow(166,'Continue','StartGacha');b=flow(166,'Continue','Success')
            keys=[a['key'],b['key']]
            self.assertEqual(review.choose(keys+['unknown'], 'ramp',keys),2)
            self.assertEqual(FlowReview(p).choices,{k:'ramp' for k in keys})
            self.assertEqual(review.choose(keys,'bogus',keys),0)
            self.assertEqual(review.choose([keys[0]],'undecided',keys),1)
            rows=review.rows([a,b],[]);target=review.export(rows,Path(tmp)/'review.csv')
            with target.open(encoding='utf-8-sig',newline='') as f:data=list(csv.DictReader(f))
            self.assertEqual(data[0]['联动意向'],'待决定');self.assertEqual(data[1]['原始身份'],keys[1])
            p.write_text('{"broken":{},"valid":"observe"}',encoding='utf-8')
            self.assertEqual(FlowReview(p).choices,{'valid':'observe'})

    def test_backend_review_cannot_arm_or_reconfigure_outputs(self):
        qt=QGuiApplication.instance() or QGuiApplication([])
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as tmp:
            b=Backend(offline=True,settings=Path(tmp)/'settings.json');b._timer.stop()
            try:
                b._flows.items={'x':flow(166,'Continue','StartGacha')}
                before=deepcopy(b._sim_profile);b._armed=True;b._ovc_armed=False
                rows=b.semanticFlows;b.reviewFlows([rows[0]['key'],'bad'],'ramp')
                self.assertEqual(b._sim_profile,before);self.assertTrue(b._armed);self.assertFalse(b._ovc_armed)
                self.assertEqual(b.semanticFlows[0]['review_decision'],'ramp')
                self.assertFalse((Path(tmp)/'settings.json').exists())
                b.exportFlowReview();self.assertTrue((Path(tmp)/'flow-review/流程语义与联动意向.csv').exists())
            finally:b._armed=False;b.shutdown()

if __name__=='__main__':unittest.main()
