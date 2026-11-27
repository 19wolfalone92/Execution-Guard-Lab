"""No-network tests of the exact authorized static-probe control flow."""
import datetime as dt, json, os, uuid
from unittest.mock import patch
import unittest
from cloud_runtime import write_probe as probe

ACCOUNT='a'*32
V1=str(uuid.UUID(int=1)); V2=str(uuid.UUID(int=2)); D1=str(uuid.UUID(int=3)); D2=str(uuid.UUID(int=4))
class Reply:
    def __init__(self,body,status=200): self.body=body; self.status=status; self.headers={}
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,n): return self.body[:n]
class Fake:
    def __init__(self,extra=False): self.extra=extra; self.writes=[]; self.version=V1; self.enabled=False; self.uploads=0
    def open(self,req,timeout):
        url=req.full_url; method=req.get_method(); path=url.split('/client/v4')[-1]
        if 'workers.dev/health' in url: return Reply(b'eglab-static-v1' if self.version==V1 else b'eglab-static-v2')
        if method!='GET': self.writes.append((method,path))
        info=None
        if path.endswith('/tokens/verify'): result={'status':'active','expires_on':(dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=1)).isoformat()}
        elif path=='/accounts/'+ACCOUNT: result={'id':ACCOUNT}
        elif path=='/accounts?per_page=50':
            result=[{'id':ACCOUNT}]+([{'id':'b'*32}] if self.extra else []); info={'total_count':len(result),'total_pages':1}
        elif path.endswith('/workers/scripts'): result=[]
        elif path.endswith('/workers/subdomain'): result={'subdomain':'synthetic-lab'}
        elif path.endswith('/deployments') and method=='GET': result={'deployments':[{'id':D1 if self.version==V1 else D2,'versions':[{'version_id':self.version,'percentage':100}]}]}
        elif path.endswith('/deployments') and method=='POST': self.version=json.loads(req.data)['versions'][0]['version_id']; result={'id':D1}
        elif path.endswith('/settings'): result={'bindings':[]}
        elif path.endswith('/subdomain'):
            if method=='POST': self.enabled=json.loads(req.data)['enabled']
            result={'enabled':self.enabled}
        elif method=='PUT' and '/workers/scripts/eglab-probe-' in path:
            self.uploads+=1; self.version=V1 if self.uploads==1 else V2; result={'id':'synthetic'}
        else: raise AssertionError('unexpected mock path')
        body={'success':True,'result':result}
        if info: body['result_info']=info
        return Reply(json.dumps(body).encode())

def run(fake):
    with patch.dict(os.environ,{'CF_TOKEN':'synthetic-token','CF_ACCOUNT':ACCOUNT,'GITHUB_REPOSITORY':'19wolfalone92/Execution-Guard-Lab','GITHUB_REF':'refs/heads/qualification/cloud-runtime-oauth-20261127','GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1','GITHUB_SHA':'c'*40}),patch.object(probe,'opener',fake),patch.object(probe,'report',{'steps':[],'status':'PARTIAL'}) as r:
        probe.main(); return r

class WriteProbeTests(unittest.TestCase):
    def test_static_write_happy_path(self):
        f=Fake(); r=run(f)
        self.assertTrue(r['status']=='PASS' and len(f.writes)==5 and f.version==V1 and not f.enabled)
        self.assertTrue(all('/workers/scripts/eglab-probe-123-1' in path for _,path in f.writes))
        self.assertNotIn('synthetic-token',json.dumps(r)); self.assertNotIn(ACCOUNT,json.dumps(r))

    def test_extra_visible_account_fails_before_mutation(self):
        f=Fake(extra=True)
        with self.assertRaisesRegex(probe.Stop,'isolation read guard failed'): run(f)
        self.assertEqual(f.writes,[])
