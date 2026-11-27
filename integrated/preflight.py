"""Local verification of release HOLD, not a deployment command.
External criteria need provider evidence and independent qualification before any
new release workflow may be authorized. No boolean override and no network.
"""
import json
from pathlib import Path

def assess(root):
    root=Path(root);cfg=json.loads((root/'integrated/production-config.example.json').read_text());core=json.loads((root/'integrated/core/wrangler.jsonc').read_text());gateway=json.loads((root/'integrated/gateway/wrangler.jsonc').read_text());hold=(root/'.github/workflows/cloud-write-qualification.yml').read_text()
    local={'production_config_held':cfg['status']=='HOLD_NOT_DEPLOYABLE','core_not_public':core.get('workers_dev') is False and core.get('preview_urls') is False and not core.get('routes') and not core.get('custom_domains'), 'gateway_fixture_not_public':gateway.get('workers_dev') is False and gateway.get('preview_urls') is False and gateway.get('main')=='fixture.mjs', 'admission_sqlite':any('Admission' in m.get('new_sqlite_classes',[]) for m in gateway.get('migrations',[])), 'cloud_workflow_held':'workflow_dispatch:' in hold and 'exit 1' in hold and 'secrets.' not in hold and 'push:' not in hold}
    blocked=['historical HTTPS attribution and authorized recovery','real owner identity','distributed OAuth replay and revocation','deployed core isolation','cloud CPU/RAM and Free feasibility','cloud recovery and rollback','remote MCP and ChatGPT']
    return {'status':'BLOCKED' if all(local.values()) else 'FAIL','local':local,'external_blockers':blocked,'release_allowed':False}
if __name__=='__main__':
    print(json.dumps(assess(Path(__file__).resolve().parents[1]),indent=2));raise SystemExit(1)
