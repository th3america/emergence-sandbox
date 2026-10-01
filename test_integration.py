"""Ember regressions on Greyfoot's review and integration."""
import copy, unittest
from engine import execute, RecipeError
from evaluate_run_pair import evaluate_run_pair
from test_peer import receipt

class IntegrationTests(unittest.TestCase):
    def test_malformed_identifiers_are_recipe_errors(self):
        for op,params,args in [('select',{'key':[]},['$left']),('sort',{'key':[]},['$left']),('use_tool',{'tool_id':[]},['$left','$right'])]:
            with self.subTest(op=op),self.assertRaises(RecipeError):
                execute({'steps':[{'id':'x','op':op,'inputs':args,'params':params}],'output':'x'},{},{})
    def test_tampered_hash_is_not_replay(self):
        a=receipt('a');b=copy.deepcopy(a);b['proposal']['recipe']['output']='tampered'
        r=evaluate_run_pair(a,b)
        self.assertEqual(r['relations']['recipe'],'unknown')
        self.assertEqual(r['recipe_integrity']['current'],'mismatch')
    def test_ablation_target_and_tool_state_are_environment(self):
        a=receipt('a',condition='ablation');b=copy.deepcopy(a)
        a['disabled']='normalize';b['disabled']='compare'
        self.assertEqual(evaluate_run_pair(a,b)['relations']['environment'],'changed')
        a=receipt('a');b=copy.deepcopy(a);b['tool_snapshot']={'new':'tool'}
        self.assertEqual(evaluate_run_pair(a,b)['relations']['environment'],'changed')
    def test_boolean_is_not_number(self):
        recipe={'steps':[{'id':'d','op':'compare','inputs':['$left','$right']}],'output':'d'}
        result,_=execute(recipe,[{'id':'a','value':True}],[{'id':'a','value':1}])
        self.assertEqual(result['changed'],['a'])

