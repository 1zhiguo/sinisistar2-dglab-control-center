import unittest
from sinisistar_dglab.backend import WAVES
from sinisistar_dglab.dglab import stream_frame
from sinisistar_dglab.simulation import Simulator,default_profile,sanitize_profile,wave_samples,demo_state
from sinisistar_dglab.pulse import has_pulse_abnormal

class PresetsAndPolicy(unittest.TestCase):
    def test_original_preset_frequency_and_amplitude_bytes_round_trip(self):
        presets=[w for w in WAVES if w.get('frames')]
        self.assertEqual(len(presets),9)
        for wave in presets:
            for i,expected in enumerate(wave['frames']):
                amplitudes,hz=wave_samples(wave,i*.1+1e-8,wave['native_period'],30)
                self.assertEqual(stream_frame([17*v for v in amplitudes],hz,17),expected,(wave['key'],i))
    def test_positive_buff_is_not_output_or_a_kind_bonus_even_in_legacy_configuration(self):
        profile=default_profile();profile['abnormals']['Defilement']['enabled']=True;profile['abnormals']['InfertilityBlessing'].update(enabled=True,pulse_enabled=True,vibration_enabled=True)
        state=demo_state('idle',0,10);state['abnormals']=[{'name':'InfertilityBlessing','level':1}]
        self.assertFalse(has_pulse_abnormal(state,profile))
        self.assertFalse(Simulator().evaluate(state,profile,WAVES,now=10)['active'])
        state['abnormals'].append({'name':'Defilement','level':3})
        result=Simulator().evaluate(state,profile,WAVES,now=10)
        self.assertEqual(result['abnormal_count'],1);self.assertEqual(result['peaks']['pulseA'],10)
    def test_loss_of_blessing_is_adverse_and_survives_positive_filter(self):
        profile=sanitize_profile({'version':2,'abnormals':{'InfertilityBlessing':{'enabled':True}}})
        self.assertFalse(profile['abnormals']['InfertilityBlessing']['enabled'])
        state=demo_state('idle',0,10);state['abnormals']=[{'name':'Blessing_Lost','level':1}];profile['abnormals']['Blessing_Lost']['enabled']=True
        self.assertEqual(Simulator().evaluate(state,profile,WAVES,now=10)['peaks']['pulseA'],10)
    def test_death_caps_are_independent_and_original_wave_owns_both_channels(self):
        profile=default_profile();profile.update(mix='sum',pulse_cap_a=9,pulse_cap_b=17)
        state=demo_state('idle',0,10);state['hp']['current']=0;state['abnormals']=[{'name':'Poison','level':1}]
        engine=Simulator();engine.evaluate(state,profile,WAVES,now=10)
        state.update(sampled_at=10.1,sample_id=2)
        result=engine.evaluate(state,profile,WAVES,now=10.1)
        self.assertEqual(result['pulse_stream']['A']['peak'],9);self.assertEqual(result['pulse_stream']['B']['peak'],17)
        for c in ('A','B'):
            frame=result['pulse_stream'][c]
            self.assertEqual(stream_frame(frame['samples'],frame['frequencies'],frame['peak'])[:8],'48484848')
            self.assertEqual(result['selected']['pulse'+c],[profile['rules']['defeat_hold']['name']])
