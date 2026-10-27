"""Semantic exclusions for the pinned game build, shared by preview and Pulse.

The game's IsBlessingAbnormal also includes Blessing_Lost, which is adverse.
Do not use a name substring or that category alone to infer a positive buff.
"""
import json
from pathlib import Path
POSITIVE_STATUSES=frozenset(('InfertilityBlessing',))
STATUS_CATALOG=json.loads((Path(__file__).parent/'assets/status-catalog.json').read_text(encoding='utf-8'))
ABNORMAL_PULSE=10

def normalize_abnormal(rule):
    rule.update(pulse_strength=ABNORMAL_PULSE,pulse_level_step=0.,pulse_gain=0.,
                vibration_strength=0.,vibration_level_step=0.,vibration_gain=0.,vibration_enabled=False)
    if positive_status(rule['key']):rule.update(enabled=False,pulse_enabled=False)
    return rule

def positive_status(status):
    name=status if isinstance(status,str) else status.get('name')
    return name in POSITIVE_STATUSES or (isinstance(status,dict) and status.get('is_positive') is True)
