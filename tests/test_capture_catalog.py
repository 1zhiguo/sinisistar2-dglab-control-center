import importlib.util,json,tempfile,unittest
from pathlib import Path
from sinisistar_dglab.flows import FlowCatalog
from sinisistar_dglab.simulation import demo_state

ROOT=Path(__file__).resolve().parents[1]

class CaptureCatalog(unittest.TestCase):
    def test_zero_hp_internal_capture_is_cataloged_without_claiming_an_exact_cg(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as temp:
            catalog=FlowCatalog(Path(temp)/'flows.json')
            state=demo_state('idle',0,10);state.update(bound=True,binder='Zombie',hp={'current':0,'max':100},flow={'playing':False})
            self.assertTrue(catalog.observe(state));self.assertFalse(catalog.observe(state))
            row=catalog.rows()[0]
            self.assertEqual(row['kind'],'capture_penalty');self.assertFalse(row['defeat_confirmed'])
            self.assertFalse(row['precise_cg_verified']);self.assertTrue(row['runtime_verified'])
            state.update(bound=False);self.assertFalse(catalog.observe(state))
            state.update(bound=True);self.assertTrue(catalog.observe(state))
            self.assertEqual(len(catalog.rows()),1)
    def test_static_definitions_stay_unverified_and_contain_zombie_variants(self):
        data=json.loads((ROOT/'src/sinisistar_dglab/assets/capture-candidates.json').read_text(encoding='utf-8'))
        zombie=next(r for r in data['candidates'] if r['enemy']=='Zombie')
        self.assertIn('m_AnimHold_End_Grave',zombie['animation_fields'])
        self.assertTrue(all(not r['runtime_verified'] and not r['precise_cg_verified'] for r in data['candidates']))
        self.assertGreater(data['gallery_symbol_count'],data['gallery_distinct_ids'])
    def test_metadata_inventory_does_not_count_ordinary_enemy_death_as_a_cg(self):
        spec=importlib.util.spec_from_file_location('capture_inventory',ROOT/'tools/catalog_capture_flows.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        text='''public enum GalleryEnemyID
{
 public const GalleryEnemyID GaID_Zombie = 0;
 public const GalleryEnemyID Alias = 0;
}
public class Zombie : EnemyObject
{
 private int m_AnimHold_Loop;
 private void TaskHold() { }
}
public class Rat : EnemyObject
{
 private int m_AnimDead;
}
'''
        result=module.inventory(text)
        self.assertEqual(result['candidate_count'],1);self.assertEqual(result['gallery_distinct_ids'],1)
        self.assertEqual(result['candidates'][0]['enemy'],'Zombie')
