"""Exact file sets for audited distribution builds; mixed builds are rejected."""
from pathlib import Path
import json
PROFILES=json.loads((Path(__file__).parent/'assets/game-builds.json').read_text(encoding='utf-8'))['profiles']
FINGERPRINTS=frozenset(p['files']['GameAssembly.dll'] for p in PROFILES)
