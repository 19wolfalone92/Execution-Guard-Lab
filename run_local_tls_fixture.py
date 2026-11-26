"""Synthetic loopback test entry only. Not copied into deployment image."""
import os
from secure_http import Settings,run_tls_server

if __name__=='__main__':
    cfg=Settings.from_env();port=int(os.environ['LAB_PORT'])
    if not (cfg.resource==f'https://127.0.0.1:{port}/mcp' and cfg.issuer=='https://issuer.example.invalid/' and cfg.subject=='synthetic-owner' and cfg.client_id=='synthetic-client' and cfg.kid=='fixture-1'):
        raise SystemExit('Synthetic loopback only')
    run_tls_server(cfg,os.environ['LAB_TLS_CERT'],os.environ['LAB_TLS_KEY'],'127.0.0.1',port)
