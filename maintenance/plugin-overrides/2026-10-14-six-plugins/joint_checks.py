import argparse
import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'core'))
home=Path(tempfile.mkdtemp(prefix='six-plugins-joint-'))
os.environ['HERMES_HOME']=str(home)
try:
 names=json.loads((ROOT/'pins.json').read_text())
 for item in names:
  shutil.copytree(ROOT/'staged'/item['name'],home/'plugins'/item['name'],ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
 (home/'config.yaml').write_text(json.dumps({'_config_version':51,'plugins':{'enabled':[x['name'] for x in names]}}))
 (home/'memories').mkdir()
 (home/'memories/MEMORY.md').write_text('PRIVATE_JOINT_SENTINEL')
 from hermes_cli import plugins as P
 from hermes_cli.lifecycle import invoke_hook
 from hermes_constants import set_hermes_home_override,reset_hermes_home_override
 from agent import redact
 P.discover_plugins(force=True)
 manager=P.get_plugin_manager()
 for item in names:
  entry=manager._plugins.get(item['name'])
  assert entry is not None and not entry.error,(item['name'],getattr(entry,'error',None))
 print('PASS six plugins discovered together without errors')
 pattern_sources=redact._PLUGIN_PREFIX_PATTERNS
 assert len(pattern_sources['plugin:redaction-pack'])==71,len(pattern_sources.get('plugin:redaction-pack',[]))
 dummy='hvs.'+'A'*100
 assert dummy not in redact.redact_sensitive_text(dummy,force=True)
 baseline='sk-proj-'+'A'*80
 assert baseline not in redact.redact_sensitive_text(baseline,force=True)
 ordinary='验收：普通产品文案，没有凭证。'*10000
 start=time.perf_counter(); assert redact.redact_sensitive_text(ordinary,force=True)==ordinary
 print('PASS 71 patterns admitted, dummy credential and builtin credential masked; ordinary text preserved',round(time.perf_counter()-start,4))
 def profile_run(i):
  h=home/f'isolated-{i}'
  h.mkdir()
  shutil.copytree(home/'plugins',h/'plugins')
  shutil.copy2(home/'config.yaml',h/'config.yaml')
  token=set_hermes_home_override(h)
  try:
   P.discover_plugins(force=True)
   for j in range(20):
    invoke_hook('pre_llm_call',session_id='same',turn_id=str(j),conversation_history=[],user_message='PRIVATE_INPUT',is_first_turn=True,model='test',platform='cli')
    invoke_hook('pre_tool_call',tool_name='terminal',args={'command':'PRIVATE_ARGS'},session_id='same',turn_id=str(j),tool_call_id=str(j))
    invoke_hook('post_tool_call',tool_name='terminal',result='中文',session_id='same',turn_id=str(j),tool_call_id=str(j),status='ok')
    invoke_hook('post_auxiliary_call',session_id='same',aux_task='title_generation',model=f'model-{i}',ended_at=time.time(),usage={'input_tokens':7},request='PRIVATE_AUX',response='PRIVATE_AUX')
    invoke_hook('api_request_error',session_id='same',model=f'model-{i}',error={'type':'RateLimitError','message':'PRIVATE_ERROR'},reason='rate_limit',status_code=429,retry_count=2,retryable=True,ended_at=time.time())
    invoke_hook('pre_approval_request',surface='terminal',session_key='same',pattern_key='test-only',command='PRIVATE_COMMAND')
    invoke_hook('post_approval_response',surface='terminal',session_key='same',pattern_key='test-only',choice='deny',decided_by='user',command='PRIVATE_COMMAND')
    invoke_hook('post_llm_call',session_id='same',turn_id=str(j),conversation_history=[],assistant_response='PRIVATE_OUTPUT',model=f'model-{i}',platform='cli')
  finally:reset_hermes_home_override(token)
  db=sqlite3.connect(h/'plugin-data/context-audit/audit.db')
  assert db.execute('select count(*),min(result_bytes),max(result_bytes) from tool_calls').fetchone()==(20,6,6)
  assert db.execute('select count(*) from turns').fetchone()[0]==20
  db.close()
  for n in ['aux-ledger','error-ledger','approval-ledger']:
   logs=list((h/'plugin-data'/n).glob('*.jsonl')); assert len(logs)==1,(n,logs)
   content=logs[0].read_text(); rows=[json.loads(x) for x in content.splitlines()]
   assert len(rows)==20,(n,len(rows))
   assert 'PRIVATE_' not in content,(n,'raw body leaked')
   if n=='approval-ledger':assert all(r['choice']=='deny' and r['outcome']=='denied' and r['decided_by']=='user' for r in rows)
   if n=='error-ledger':assert all(r['error_type']=='RateLimitError' and r['reason']=='rate_limit' and r['status']==429 and r['retry_count']==2 and r['retryable'] is True for r in rows)
   if n!='approval-ledger':assert all(r['model']==f'model-{i}' for r in rows),(n,'cross profile')
  assert b'PRIVATE_' not in (h/'plugin-data/context-audit/audit.db').read_bytes()
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(profile_run,range(2)))
 print('PASS real hook dispatch in two simultaneous profiles: 40 tool/turn rows, 120 ledger rows, UTF8 bytes, no raw-body persistence')
 # Real PluginManager commands are read-only checks below; mutation is tested only in tmp home.
 print('COMMANDS',sorted(manager._plugin_commands))
 invoke_hook('on_session_start',session_id='joint',platform='cli')
 modules=[e for e in sys.modules.values() if getattr(e,'PLUGIN_NAME',None)=='memory-rewind' and hasattr(e,'take_snapshot')]
 m=modules[-1]
 cli=sys.modules[m.__name__+'.cli'] if m.__name__+'.cli' in sys.modules else __import__(m.__name__+'.cli',fromlist=['run_cli'])
 class C:
  def __init__(self,**kw):self.kw=kw
  def get_config(self,k,d=None):return self.kw.get(k,d)
 rev=m.take_snapshot(home,home/'plugin-data/memory-rewind',m.TrackingOptions(track_skills=False),['isolated fixture'])
 store=__import__(m.__name__+'.gitstore',fromlist=['GitStore']).GitStore(home,home/'plugin-data/memory-rewind')
 rev=rev or store.head()
 (home/'memories/MEMORY.md').write_text('PRIVATE_CHANGED')
 args=argparse.Namespace(mrw_command='restore',rev=rev,target='memory',yes=True,dry_run=True)
 assert cli.run_cli(args,C())==0
 assert (home/'memories/MEMORY.md').read_text()=='PRIVATE_CHANGED'
 args.dry_run=False
 assert cli.run_cli(args,C())!=0
 assert cli.run_cli(args,C(allow_restore=True))==0
 assert (home/'memories/MEMORY.md').read_text()=='PRIVATE_JOINT_SENTINEL'
 print('PASS isolated restore preview, default deny, explicitly authorized restore; production untouched')
finally:
 shutil.rmtree(home,ignore_errors=True)
