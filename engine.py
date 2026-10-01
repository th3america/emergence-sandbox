"""Bounded JSON recipe interpreter. No eval, subprocess, imports or filesystem in recipes."""
import copy
import hashlib
import json
import re

OPS = {
    'normalize': 'Map canonical fields to ordered input aliases; omit unrelated fields.',
    'sort': 'Sort record rows by an existing field.',
    'fingerprint': 'SHA256 of canonical JSON.',
    'compare': 'Compare records by id. Return added, removed and changed ids, or additions only.',
    'select': 'Select one field from an object.',
    'use_tool': 'Invoke a previously promoted, immutable recipe with two inputs.'
}

class RecipeError(ValueError):
    pass

def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)

def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()

def rows(value):
    if not isinstance(value, list) or len(value) > 200 or any(not isinstance(x, dict) for x in value):
        raise RecipeError('Expected at most 200 record objects')
    return value

def execute(recipe, left, right, tools=None, disabled=None, depth=0, budget=None):
    tools = tools or {}
    budget = [128] if budget is None else budget
    if depth > 3:
        raise RecipeError('Tool nesting exceeds 3')
    if len(canonical(recipe)) > 32000 or not isinstance(recipe, dict):
        raise RecipeError('Recipe must be an object under 32 KB')
    steps = recipe.get('steps')
    if not isinstance(steps, list) or not 1 <= len(steps) <= 24:
        raise RecipeError('Recipe needs 1–24 steps')
    env = {'$left': copy.deepcopy(left), '$right': copy.deepcopy(right)}
    trace = []
    for step in steps:
        budget[0] -= 1
        if budget[0] < 0:
            raise RecipeError('Shared execution budget of 128 steps exceeded')
        if not isinstance(step, dict):
            raise RecipeError('Each step must be an object')
        sid, op = step.get('id'), step.get('op')
        if not isinstance(sid, str) or not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_]{0,39}', sid) or sid in env:
            raise RecipeError('Step ids must be unique simple identifiers')
        if not isinstance(op, str) or op not in OPS:
            raise RecipeError('Unknown operation: '+str(op))
        if op == disabled:
            raise RecipeError('Countercheck removed required operation: '+op)
        refs = step.get('inputs', [])
        if not isinstance(refs, list) or any(not isinstance(r, str) or r not in env for r in refs):
            raise RecipeError('Inputs must reference existing steps or $left/$right')
        args = [env[r] for r in refs]
        params = step.get('params', {})
        if not isinstance(params, dict):
            raise RecipeError('params must be an object')
        arity = 2 if op in ('compare', 'use_tool') else 1
        if len(args) != arity:
            raise RecipeError(f'{op} requires {arity} input(s)')
        if op == 'normalize':
            fields = params.get('fields')
            if not isinstance(fields, dict) or not 1 <= len(fields) <= 20:
                raise RecipeError('normalize needs 1–20 canonical fields with input aliases')
            out = []
            for row in rows(args[0]):
                item = {}
                for field, aliases in fields.items():
                    if not isinstance(aliases, list) or not aliases or any(not isinstance(a, str) for a in aliases):
                        raise RecipeError('Field aliases must be nonempty string lists')
                    found = [a for a in aliases if a in row]
                    if not found:
                        raise RecipeError('Missing field '+field)
                    if any(canonical(row[a]) != canonical(row[found[0]]) for a in found):
                        raise RecipeError('Contradictory aliases for '+field)
                    item[field] = row[found[0]]
                out.append(item)
        elif op == 'sort':
            key = params.get('key', 'id')
            if not isinstance(key,str): raise RecipeError('sort key must be a string')
            values = rows(args[0])
            if any(key not in row for row in values):
                raise RecipeError('Missing sort field')
            out = sorted(values, key=lambda row: canonical(row[key]))
        elif op == 'fingerprint':
            out = digest(args[0])
        elif op == 'select':
            if not isinstance(params.get('key'),str): raise RecipeError('select key must be a string')
            if not isinstance(args[0], dict) or params.get('key') not in args[0]:
                raise RecipeError('Selected field is absent')
            out = args[0][params['key']]
        elif op == 'compare':
            indexes = []
            for values in args:
                index = {}
                for row in rows(values):
                    identity = row.get('id')
                    if not isinstance(identity, str) or not identity:
                        raise RecipeError('compare needs nonempty string ids')
                    if identity in index:
                        raise RecipeError('Duplicate record id: '+identity)
                    index[identity] = row
                indexes.append(index)
            a, b = indexes
            out = {'added': sorted(b.keys()-a.keys()), 'removed': sorted(a.keys()-b.keys()),
                   'changed': sorted(k for k in a.keys() & b.keys() if canonical(a[k]) != canonical(b[k]))}
            mode = params.get('mode', 'all')
            if mode == 'added':
                out = out['added']
            elif mode != 'all':
                raise RecipeError('compare mode must be all or added')
        else:
            tool_id = params.get('tool_id')
            if not isinstance(tool_id,str): raise RecipeError('tool_id must be a string')
            if tool_id not in tools:
                raise RecipeError('Unknown saved tool')
            tool = tools[tool_id]
            if digest(tool['recipe']) != tool['recipe_sha256']:
                raise RecipeError('Saved tool digest mismatch')
            out, inner = execute(tool['recipe'], *args, tools=tools, disabled=disabled, depth=depth+1, budget=budget)
            trace.append({'step': sid, 'tool_id': tool_id, 'nested_trace': inner})
        if len(canonical(out)) > 100000:
            raise RecipeError('Intermediate result too large')
        env[sid] = out
        trace.append({'step': sid, 'operation': op, 'input_refs': refs, 'output': copy.deepcopy(out), 'output_sha256': digest(out)})
    output = recipe.get('output')
    if not isinstance(output,str) or output not in env or output.startswith('$'):
        raise RecipeError('output must name a completed step')
    return env[output], trace

def fixtures(condition):
    left = [{'id':'a','value':10,'label':'Amber','seen_at':1}, {'id':'b','value':20,'label':'Blue','seen_at':1}]
    right = [{'id':'a','value':10,'label':'Amber','seen_at':2}, {'id':'b','value':25,'label':'Blue','seen_at':2}, {'id':'c','value':30,'label':'Coral','seen_at':2}]
    expected = {'added':['c'], 'removed':[], 'changed':['b']}
    if condition == 'noise':
        right = [dict(x, seen_at=999) for x in reversed(left)]
        expected = {'added':[], 'removed':[], 'changed':[]}
    elif condition == 'schema':
        right = [{'key':x['id'], 'amount':x['value'], 'name':x['label'], 'timestamp':x['seen_at']} for x in right]
    elif condition == 'holdout':
        left = [{'id':'x','value':4,'label':'X','seen_at':1}, {'id':'y','value':9,'label':'Y','seen_at':1}]
        right = [{'id':'y','value':9,'label':'Y changed','seen_at':3}, {'id':'z','value':0,'label':'Z','seen_at':3}]
        expected = {'added':['z'], 'removed':['x'], 'changed':['y']}
    elif condition not in ('baseline', 'ablation'):
        raise RecipeError('Unknown condition')
    return left, right, expected

def goal_text(goal):
    if goal == 'changes':
        return 'Report added, removed and materially changed ids. Material fields are id, value and label. Ignore observation timestamps and input order.'
    if goal == 'additions':
        return 'Return only a sorted list of newly added ids. Do not report updates or removals.'
    raise RecipeError('Unknown goal')

def experiment_inputs(goal, condition, custom=None):
    if goal == 'custom':
        if not isinstance(custom, dict) or not isinstance(custom.get('goal'), str) or not custom['goal'].strip():
            raise RecipeError('Custom experiment requires a goal and left, right, expected fields')
        if any(k not in custom for k in ('left','right','expected')) or len(canonical(custom))>50000:
            raise RecipeError('Custom fixture requires left/right/expected and must fit 50 KB')
        return custom['left'], custom['right'], custom['expected'], custom['goal']
    left, right, expected = fixtures(condition)
    if goal == 'additions':expected=expected['added']
    return left, right, expected, goal_text(goal)

def packet(goal, condition, tools, custom=None):
    left, right, _, instruction = experiment_inputs(goal,condition,custom)
    return {'protocol':'emergence-recipe/1', 'goal':instruction, 'condition':condition,
            'inputs':{'left':left,'right':right}, 'primitives':OPS,
            'contract':{'step':{'id':'unique_name','op':'primitive name','inputs':['$left'], 'params':{}},
                        'recipe':{'steps':'ordered list; input refs can name earlier steps', 'output':'last desired step id'},
                        'normalize':'params.fields maps output keys to ordered input aliases, e.g. id: [id, key]',
                        'compare':'requires id; compares entire normalized record. mode=all or added',
                        'select':'params.key', 'sort':'params.key', 'use_tool':'params.tool_id; two inputs'},
            'tools':[{'id':k,'name':v['name'],'recipe_sha256':v['recipe_sha256'],'recipe':v['recipe']} for k,v in tools.items()],
            'reply_contract':{'participant':'name/model', 'missing_function':'what intermediate demand you identified',
                              'prediction':'expected functional behavior', 'dependency':'one suspected dependency',
                              'recipe':{'steps':[], 'output':''}},
            'instruction':'Propose a method for the goal, including any missing intermediate function. Return JSON only. Test feedback will be provided. No filesystem/network/shell operations exist in this interpreter.'}

DEMO = {'participant':'Authored demonstration (not an AI run)', 'missing_function':'Stable comparison of material record fields',
        'prediction':'Detect changes despite timestamps and row order; schema aliases support changed input format.', 'dependency':'normalize',
        'recipe':{'steps':[
            {'id':'old','op':'normalize','inputs':['$left'],'params':{'fields':{'id':['id','key'],'value':['value','amount'],'label':['label','name']}}},
            {'id':'new','op':'normalize','inputs':['$right'],'params':{'fields':{'id':['id','key'],'value':['value','amount'],'label':['label','name']}}},
            {'id':'delta','op':'compare','inputs':['old','new']}], 'output':'delta'}}
