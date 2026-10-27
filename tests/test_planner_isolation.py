"""Route filtering and cap views must never modify saved or other-route rules."""
from copy import deepcopy
import unittest
from sinisistar_dglab.simulation import initial_profile,demo_state,VIBRATION_WAVES,sanitize_profile
from sinisistar_dglab.pulse import PulsePlanner
from sinisistar_dglab.ovc_plan import OvcPlanner
from sinisistar_dglab.backend import WAVES

class PlannerIsolation(unittest.TestCase):
    def test_both_planners_share_settings_without_mutating_them(self):
        p=initial_profile();p['cg']['inherit_death']=False
        before=deepcopy(p)
        for case in ('grab_hp','abnormals','flow'):
            state=demo_state(case,1,10)
            for planner,catalog in ((PulsePlanner(),WAVES),(OvcPlanner(),VIBRATION_WAVES)):
                view=dict(p);view['pulse_cap_a']=5;view['vibration_cap_a']=10
                planner.update(state,view,catalog,now=10,enabled=True)
                state.update(sampled_at=10.2,sample_id=11)
                planner.update(state,view,catalog,now=10.2,enabled=True)
                self.assertEqual(p,before)

    def test_new_defaults_preserve_explicit_user_opt_out(self):
        p=sanitize_profile({})
        self.assertTrue(p['cg']['same_hp_enabled']);self.assertTrue(p['gallery']['rule']['enabled'])
        p['cg']['same_hp_enabled']=False;p['gallery']['rule']['enabled']=False
        loaded=sanitize_profile(p)
        self.assertFalse(loaded['cg']['same_hp_enabled']);self.assertFalse(loaded['gallery']['rule']['enabled'])
