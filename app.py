"""Loopback-only emergence recipe workbench; standard library, no model credentials."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse
import datetime
import json
import secrets
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from engine import OPS, DEMO, RecipeError, canonical, digest, execute, fixtures, goal_text, packet, experiment_inputs

ROOT = Path(__file__).resolve().parent

class Lab:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.stopped = False
        with self.db() as c:
            c.execute('create table if not exists events (id text primary key, kind text, payload text)')
        controls = self.items('control')
        self.stopped = controls[-1]['stopped'] if controls else False

    @contextmanager
    def db(self):
        connection=sqlite3.connect(self.path)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def save(self, kind, value):
        with self.db() as c:
            c.execute('insert into events values (?,?,?)', (value['id'],kind,canonical(value)))

    def items(self, kind):
        with self.db() as c:
            return [json.loads(x[0]) for x in c.execute('select payload from events where kind=? order by rowid', (kind,))]

    def tools(self):
        return {x['id']:x for x in self.items('tool')}

    def run(self, request):
        with self.lock:
            if self.stopped:
                raise RecipeError('Experiment execution is stopped. Resume explicitly to run again.')
            proposal = request.get('proposal')
            if not isinstance(proposal,dict) or not isinstance(proposal.get('recipe'),dict):
                raise RecipeError('A proposal with a recipe object is required')
            for key in ('participant','missing_function','prediction','dependency'):
                if not isinstance(proposal.get(key),str) or not proposal[key].strip() or len(proposal[key])>2000:
                    raise RecipeError('Provide a short nonempty '+key)
            source=request.get('source','external_ai')
            if source not in ('external_ai','human','authored_demo'):
                raise RecipeError('Unknown attribution source')
            goal=request.get('goal','changes')
            condition=request.get('condition','baseline')
            left,right,expected,goal_description=experiment_inputs(goal,condition,request.get('custom_fixture'))
            disabled=request.get('disabled','normalize') if condition=='ablation' else None
            if disabled is not None and disabled not in OPS:raise RecipeError('Unknown countercheck primitive')
            tools=self.tools(); output=None; trace=[]; error=None
            try:
                output,trace=execute(proposal['recipe'],left,right,tools,disabled)
            except (RecipeError,TypeError,KeyError,ValueError) as exc:
                error=str(exc)
            result={'id':str(uuid.uuid4()),'kind':'run','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    'source':source,'attribution_note':'Participant identity and intent are supplied claims; execution trace is controller-observed.',
                    'goal':goal,'goal_description':goal_description,'condition':condition,'disabled':disabled,'proposal':proposal,'recipe_sha256':digest(proposal['recipe']),
                    'inputs':{'left':left,'right':right},'output':output,'expected':expected,'error':error,
                    'passed':error is None and canonical(output)==canonical(expected),'trace':trace,
                    'tool_snapshot':tools,'parent_run':request.get('parent_run'),
                    'evaluation':'Fixture outcome only. Self-prompting, independence and transfer require review of the attributed proposal and paired runs.'}
            result['receipt_sha256']=digest(result)
            self.save('run',result)
            return result

    def promote(self, request):
        with self.lock:
            runs={x['id']:x for x in self.items('run')}
            run=runs.get(request.get('run_id'))
            if not run or not run['passed']:raise RecipeError('Only a passing saved run can supply a reusable tool')
            name=request.get('name','')
            if not isinstance(name,str) or not 1<=len(name.strip())<=80:raise RecipeError('Tool name must be 1–80 characters')
            tool={'id':str(uuid.uuid4()),'name':name.strip(),'recipe':run['proposal']['recipe'],
                  'recipe_sha256':run['recipe_sha256'],'origin_run':run['id'],'origin_source':run['source'],
                  'verified_scope':{'goal':run['goal'],'condition':run['condition']},
                  'utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
            self.save('tool',tool);return tool

from evaluate_run_pair import evaluate_run_pair
from assembly import library, act

def handler(lab, token, port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):pass
        def respond(self, status, value, mime='application/json'):
            raw=(canonical(value) if mime=='application/json' else value).encode('utf-8')
            self.send_response(status);self.send_header('Content-Type',mime+'; charset=utf-8')
            self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'")
            self.end_headers();self.wfile.write(raw)
        def valid_host(self):
            return self.headers.get('Host') in (f'127.0.0.1:{port}',f'localhost:{port}')
        def do_GET(self):
            if not self.valid_host():return self.respond(403,{'error':'Unexpected host'})
            if self.path in ('/','/app.js','/style.css'):
                filename={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}[self.path]
                mime={'/':'text/html','/app.js':'text/javascript','/style.css':'text/css'}[self.path]
                return self.respond(200,(ROOT/'web'/filename).read_text(encoding='utf-8'),mime)
            if self.path=='/api/state':
                return self.respond(200,{'app':'emergence-sandbox','version':2,'token':token,'stopped':lab.stopped,'primitives':OPS,'demo':DEMO,
                                          'pieces':library(lab),'assemblies':lab.items('assembly'),'creations':lab.items('creation'),'tools':list(lab.tools().values()),'runs':lab.items('run')[-40:]})
            return self.respond(404,{'error':'Not found'})
        def do_POST(self):
            if not self.valid_host():return self.respond(403,{'error':'Unexpected host'})
            origin=self.headers.get('Origin')
            if origin and origin not in (f'http://127.0.0.1:{port}',f'http://localhost:{port}'):
                return self.respond(403,{'error':'Cross-origin writes rejected'})
            if self.headers.get('X-Lab-Token')!=token:return self.respond(403,{'error':'Missing session token'})
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=100000:raise RecipeError('Request must be 1–100000 bytes')
                data=json.loads(self.rfile.read(size),parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
                if not isinstance(data,dict):raise RecipeError('Request must be an object')
                if self.path.startswith('/api/assembly/'):
                    result=act(lab,self.path.rsplit('/',1)[1],data)
                elif self.path=='/api/run':result=lab.run(data)
                elif self.path=='/api/packet':result=packet(data.get('goal','changes'),data.get('condition','baseline'),lab.tools(),data.get('custom_fixture'))
                elif self.path=='/api/compare':
                    runs={r['id']:r for r in lab.items('run')}
                    result=evaluate_run_pair(runs[data['previous']],runs[data['current']])
                elif self.path=='/api/promote':result=lab.promote(data)
                elif self.path=='/api/stop':
                    with lab.lock:
                        lab.stopped=True
                        lab.save('control',{'id':str(uuid.uuid4()),'stopped':True})
                    result={'stopped':True}
                elif self.path=='/api/resume':
                    with lab.lock:
                        lab.stopped=False
                        lab.save('control',{'id':str(uuid.uuid4()),'stopped':False})
                    result={'stopped':False}
                else:return self.respond(404,{'error':'Not found'})
                self.respond(200,result)
            except (RecipeError,ValueError,TypeError,KeyError,RecursionError) as exc:
                self.respond(400,{'error':str(exc)[:500]})
    return Handler

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8774);parser.add_argument('--data',default=str(ROOT/'data'/'lab.sqlite'))
    args=parser.parse_args();lab=Lab(args.data);token=secrets.token_urlsafe(32)
    server=ThreadingHTTPServer(('127.0.0.1',args.port),handler(lab,token,args.port))
    print(f'Emergence Sandbox: http://127.0.0.1:{args.port}',flush=True)
    server.serve_forever()

if __name__=='__main__':main()
