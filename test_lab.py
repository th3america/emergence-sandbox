import copy
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from engine import DEMO, RecipeError, digest, execute, fixtures, packet
from app import Lab, handler

class EngineTests(unittest.TestCase):
    def test_semantic_cases(self):
        for condition in ('baseline','noise','schema','holdout'):
            with self.subTest(condition=condition):
                a,b,want=fixtures(condition)
                got,trace=execute(DEMO['recipe'],a,b)
                self.assertEqual(want,got);self.assertEqual(len(trace),3)

    def test_changed_goal_requires_adaptation(self):
        a,b,want=fixtures('baseline')
        original,_=execute(DEMO['recipe'],a,b)
        self.assertNotEqual(original,want['added'])
        recipe=copy.deepcopy(DEMO['recipe'])
        recipe['steps'][-1]['params']={'mode':'added'}
        self.assertEqual(execute(recipe,a,b)[0],['c'])

    def test_naive_raw_comparison_fails_noise(self):
        a,b,want=fixtures('noise')
        raw={'steps':[{'id':'delta','op':'compare','inputs':['$left','$right']}],'output':'delta'}
        self.assertNotEqual(execute(raw,a,b)[0],want)

    def test_unknown_operation(self):
        with self.assertRaises(RecipeError):execute({'steps':[{'id':'x','op':'shell','inputs':[]}],'output':'x'},[],[])

    def test_forward_reference(self):
        with self.assertRaises(RecipeError):execute({'steps':[{'id':'x','op':'fingerprint','inputs':['future']}],'output':'x'},[],[])

    def test_countercheck_removes_dependency(self):
        a,b,_=fixtures('baseline')
        with self.assertRaisesRegex(RecipeError,'Countercheck'):execute(DEMO['recipe'],a,b,disabled='normalize')

    def test_alias_contradiction(self):
        a,b,_=fixtures('baseline');b[0]['key']='not-a'
        with self.assertRaisesRegex(RecipeError,'Contradictory'):execute(DEMO['recipe'],a,b)

    def test_duplicate_identity(self):
        a,b,_=fixtures('baseline');b.append(b[0])
        with self.assertRaisesRegex(RecipeError,'Duplicate'):execute(DEMO['recipe'],a,b)

    def test_packet_has_no_evaluator_answer(self):
        p=packet('changes','schema',{})
        self.assertNotIn('expected',p);self.assertNotIn('DEMO',p)

    def test_pinned_tool_reuse_and_tamper(self):
        t={'recipe':DEMO['recipe'],'recipe_sha256':digest(DEMO['recipe'])}
        recipe={'steps':[{'id':'x','op':'use_tool','inputs':['$left','$right'],'params':{'tool_id':'t'}}],'output':'x'}
        a,b,want=fixtures('holdout')
        self.assertEqual(execute(recipe,a,b,{'t':t})[0],want)
        t['recipe_sha256']='bad'
        with self.assertRaisesRegex(RecipeError,'digest'):execute(recipe,a,b,{'t':t})

    def test_recursion_stops(self):
        recipe={'steps':[{'id':'x','op':'use_tool','inputs':['$left','$right'],'params':{'tool_id':'t'}}],'output':'x'}
        with self.assertRaisesRegex(RecipeError,'nesting'):execute(recipe,[],[],{'t':{'recipe':recipe,'recipe_sha256':digest(recipe)}})

class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'lab.sqlite';self.lab=Lab(self.path)
    def tearDown(self):self.temp.cleanup()
    def test_run_receipt_and_promotion(self):
        r=self.lab.run({'proposal':DEMO,'source':'authored_demo','condition':'holdout'})
        self.assertTrue(r['passed']);saved=Lab(self.path).items('run')[0]
        sha=saved.pop('receipt_sha256');self.assertEqual(digest(saved),sha)
        t=self.lab.promote({'run_id':r['id'],'name':'test tool'})
        self.assertEqual(Lab(self.path).tools()[t['id']]['origin_source'],'authored_demo')
    def test_failed_run_not_promotable(self):
        r=self.lab.run({'proposal':DEMO,'goal':'additions'})
        with self.assertRaises(RecipeError):self.lab.promote({'run_id':r['id'],'name':'no'})
    def test_stop_persists_and_rejects(self):
        self.lab.save('control',{'id':'control-1','stopped':True})
        reloaded=Lab(self.path)
        with self.assertRaisesRegex(RecipeError,'stopped'):reloaded.run({'proposal':DEMO})

    def test_custom_goal_and_packet_separation(self):
        proposal=copy.deepcopy(DEMO)
        proposal['recipe']={'steps':[{'id':'result','op':'select','inputs':['$left'],'params':{'key':'answer'}}],'output':'result'}
        fixture={'goal':'Extract the answer field','left':{'answer':42},'right':{},'expected':42}
        result=self.lab.run({'proposal':proposal,'goal':'custom','custom_fixture':fixture})
        self.assertTrue(result['passed'])
        exported=packet('custom','baseline',{},fixture)
        self.assertEqual(exported['goal'],'Extract the answer field');self.assertNotIn('expected',exported)
        fixture['expected']=True
        fixture['left']['answer']=1
        self.assertFalse(self.lab.run({'proposal':proposal,'goal':'custom','custom_fixture':fixture})['passed'])

class HttpTests(unittest.TestCase):
    def test_origin_token_and_real_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            lab=Lab(Path(temp)/'db.sqlite')
            server=ThreadingHTTPServer(('127.0.0.1',0),handler(lab,'secret',0))
            port=server.server_address[1];server.RequestHandlerClass=handler(lab,'secret',port)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            def post(headers):
                c=http.client.HTTPConnection('127.0.0.1',port)
                c.request('POST','/api/run',json.dumps({'proposal':DEMO,'source':'authored_demo'}),headers)
                r=c.getresponse();status=r.status;body=json.loads(r.read());c.close();return status,body
            try:
                self.assertEqual(post({})[0],403)
                self.assertEqual(post({'X-Lab-Token':'secret','Origin':'https://unrelated.invalid'})[0],403)
                status,result=post({'X-Lab-Token':'secret'})
                self.assertEqual(status,200);self.assertTrue(result['passed'])
            finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main(verbosity=2)
