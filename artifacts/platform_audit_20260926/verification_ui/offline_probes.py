"""Extract exact bounded methods; no application imports/network/runtime access."""
import ast,asyncio,hashlib,json,logging
from pathlib import Path
from datetime import datetime,timezone
from decimal import Decimal
ROOT=Path('/Users/marselkei/.codex/worktrees/platform-audit-20260926/intra')
OUT=Path.home()/'Library/Application Support/Intra/audits/2026-09-26/verification-ui'
def extract(path,names):
 t=ast.parse((ROOT/path).read_text()); nodes=[]
 for n in ast.walk(t):
  if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in names:
   n.decorator_list=[];nodes.append(n)
 return compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),str(ROOT/path),'exec')
class Session:
 async def __aenter__(self):return {'authenticated':True,'user_id':'synthetic-alice','roles':['viewer']}
 async def __aexit__(self,*_):pass
class SIO:
 def __init__(self):self.rooms=[];self.emits=[]
 def session(self,sid):return Session()
 async def enter_room(self,sid,topic):self.rooms.append([sid,topic])
 async def emit(self,event,data,**kw):self.emits.append([event,data,kw])
class Cache:
 async def get(self,key):return None
class FailedBroker:
 async def get_account(self):raise RuntimeError('synthetic broker unavailable')
class Service:
 _get_broker_client=lambda self:FailedBroker()
async def main():
 sio=SIO();g={'sio':sio,'logging':logging,'logger':logging.getLogger('audit'),'client_subscriptions':{'synthetic-session':set()},'topic_subscribers':{},'Any':object}
 exec(extract('backend/api/socketio_server.py',{'subscribe','broadcast_portfolio_update'}),g)
 await g['subscribe']('synthetic-session',{'topic':'user_synthetic-bob'})
 await g['broadcast_portfolio_update']('synthetic-bob',{'marker':'SYNTHETIC_OTHER_USER_PORTFOLIO'})
 socket={'authenticated_principal':'synthetic-alice','requested_private_topic':'user_synthetic-bob','entered_rooms':sio.rooms,'other_user_portfolio_delivered':any(e[0]=='portfolio_update'and e[2].get('to')=='synthetic-session'for e in sio.emits)}
 g={'get_hot_data_cache':lambda:Cache(),'portfolio_cache_key':lambda u:u,'logger':logging.getLogger('audit'),'Decimal':Decimal,'datetime':datetime,'UTC':timezone.utc,'Any':object}
 exec(extract('backend/services/portfolio_service.py',{'get_user_portfolio'}),g)
 portfolio=await g['get_user_portfolio'](Service(),'synthetic-alice')
 r={'mode':'pure stdlib extracted actual function bodies; no application imports/network','socket_private_room_bypass':socket,'dependency_failure_portfolio':portfolio,'source_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()for p in ['backend/api/socketio_server.py','backend/services/portfolio_service.py']}}
 (OUT/'offline_probes.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'private_room_data_delivered':socket['other_user_portfolio_delivered'],'fake_portfolio_equity':portfolio['totalEquity'],'fake_portfolio_positions':len(portfolio['positions']),'fresh_timestamp_emitted':bool(portfolio['lastUpdate'])}))
asyncio.run(main())
