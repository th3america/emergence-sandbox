import tempfile,unittest
from pathlib import Path
from app import Lab
from assembly import act,library
from engine import RecipeError
class AssemblyTests(unittest.TestCase):
 def test_creation_lineage_and_reload(self):
  with tempfile.TemporaryDirectory() as tmp:
   lab=Lab(Path(tmp)/'db');a=act(lab,'assemble',dict(goal='Create a method',pieces=['functional-lens','creation-method'],relationships=[dict(**{'from':'functional-lens','to':'creation-method'},relation='frames')]))
   c=act(lab,'creation',dict(assembly_id=a['assembly']['id'],participant='test author',title='Design',function='Inspect function',artifact='Apply lens, then assemble',scope='Fixture',contributions={'functional-lens':'Frames goal','creation-method':'Assembles'},conflicts=[],generated_demands=['Identify missing input'],governance=['Stay in scope'],claims=['Useful method']))
   self.assertEqual(c['claim_status'],'unverified')
   self.assertEqual(library(Lab(Path(tmp)/'db'))[-1]['origin_creation'],c['id'])
 def test_invalid_edges_and_missing_contributions(self):
  with tempfile.TemporaryDirectory() as tmp:
   lab=Lab(Path(tmp)/'db')
   with self.assertRaises(RecipeError):act(lab,'assemble',dict(goal='x',pieces=['functional-lens'],relationships=[{'from':'functional-lens','to':'absent','relation':'frames'}]))
   a=act(lab,'assemble',dict(goal='x',pieces=['functional-lens']))
   with self.assertRaises(RecipeError):act(lab,'creation',dict(assembly_id=a['assembly']['id'],participant='x',title='x',function='x',artifact='x',scope='x',contributions={}))
 def test_stop_and_piece(self):
  with tempfile.TemporaryDirectory() as tmp:
   lab=Lab(Path(tmp)/'db')
   p=act(lab,'piece',dict(type='context',name='x',function='bounds',content='actual',scope='test',provenance='test'))
   self.assertIn(p,library(lab))
   lab.stopped=True
   with self.assertRaises(RecipeError):act(lab,'assemble',dict(goal='x',pieces=[p['id']]))

