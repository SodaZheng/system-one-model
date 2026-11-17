#!/usr/bin/env python3
"""Exercise an unmodified jev-mcp npm package through actual stdio MCP and local HTTP."""
import json
import os
from pathlib import Path
import subprocess
import time
root=Path(__file__).resolve().parents[1]
key=next(x.split('=',1)[1] for x in (root/'.env').read_text().splitlines() if x.startswith('API_KEY='))
env={**os.environ,'TYPESAFE_BASE_URL':'http://127.0.0.1:8080','TYPESAFE_API_KEY':key,
     'JEV_PROVIDER':'typesafe','JEV_MCP_MODEL':'jev-latest','JEV_MCP_REQUEST_TIMEOUT_MS':'3600000'}
entry=root/'artifacts/jev-mcp/node_modules/@jkudish/jev-mcp/dist/index.js'
log=(root/'artifacts/jev-mcp/server.log').open('w')
p=subprocess.Popen(['node',str(entry)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,env=env)
def send(message):
 p.stdin.write(json.dumps(message)+'\n');p.stdin.flush()
def call(id,method,params):
 send({'jsonrpc':'2.0','id':id,'method':method,'params':params})
 while True:
  line=p.stdout.readline()
  if not line: raise RuntimeError('MCP server exited; see artifacts/jev-mcp/server.log')
  message=json.loads(line)
  if message.get('id')==id:
   if 'error' in message: raise RuntimeError(message['error'])
   return message['result']
try:
 init=call(1,'initialize',{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'thisthat-local-validation','version':'1.0'}})
 send({'jsonrpc':'2.0','method':'notifications/initialized'})
 tools=call(2,'tools/list',{})
 assert any(x['name']=='jev_noul' for x in tools['tools'])
 print('MCP initialized; calling jev_noul via local TypeSafe provider.',flush=True)
 start=time.monotonic()
 result=call(3,'tools/call',{'name':'jev_noul','arguments':{'propositions':['The customer wants a refund.','The customer wants the order shipped.'],'context':'The customer said: cancel my order and refund it. Do not ship anything.'}})
 data=json.loads(next(x['text'] for x in result['content'] if x['type']=='text'))
 assert not result.get('isError'),result
 assert data['results'][0]['probability']>.5 and data['results'][1]['probability']<.5,data
 out={'project':'@jkudish/jev-mcp','version':json.loads((entry.parent.parent/'package.json').read_text())['version'],
      'transport':'stdio MCP -> typesafe provider -> local HTTP', 'interface_changes':False,
      'elapsed_seconds':time.monotonic()-start,'registered_tools':len(tools['tools']),'result':data}
 (root/'artifacts/jev-mcp-result.json').write_text(json.dumps(out,indent=2)+'\n')
 print(json.dumps(out),flush=True)
finally:
 p.terminate()
 try:p.wait(timeout=5)
 except subprocess.TimeoutExpired:p.kill();p.wait()
 log.close()
