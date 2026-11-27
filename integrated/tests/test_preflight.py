from pathlib import Path
from integrated.preflight import assess

def test_release_hold():
    r=assess(Path(__file__).resolve().parents[2]);assert r['status']=='BLOCKED' and all(r['local'].values()) and r['release_allowed'] is False
