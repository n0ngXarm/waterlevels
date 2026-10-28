import pathlib,tempfile,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from consent import ConsentBook,scope_key

class ConsentTests(unittest.TestCase):
 def test_permissions_are_separate_and_bound_to_exact_source_and_destination(self):
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d)/'state';book=ConsentBook(root)
   source={'mode':'csv','directory':'approved-input','tags':['LAB_A.RUN_S'],'interval':5}
   a=scope_key(source);b=scope_key({**source,'tags':['LAB_B.RUN_S']})
   self.assertFalse(root.exists());self.assertFalse(book.approved('capture',a))
   book.remember('capture',a);self.assertTrue(book.approved('capture',a))
   self.assertFalse(book.approved('capture',b));self.assertFalse(book.approved('transfer',a))
   self.assertTrue(ConsentBook(root).approved('capture',a));self.assertEqual((root/'permissions.json').stat().st_mode&0o777,0o600)
   dest=scope_key({'source':a,'gateway':'http://127.0.0.1:4444','mode':'dry-run'})
   book.remember('transfer',dest);self.assertFalse(book.approved('transfer',scope_key({'source':a,'gateway':'http://127.0.0.1:5555','mode':'dry-run'})))
   book.clear();self.assertFalse(ConsentBook(root).approved('capture',a));self.assertFalse(ConsentBook(root).approved('transfer',dest))
 def test_invalid_or_old_permissions_fail_closed(self):
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d);(root/'permissions.json').write_text('{"capture":true}')
   self.assertFalse(ConsentBook(root).approved('capture','anything'))
   (root/'permissions.json').write_text('invalid')
   self.assertFalse(ConsentBook(root).approved('capture','anything'))

if __name__=='__main__':unittest.main()
