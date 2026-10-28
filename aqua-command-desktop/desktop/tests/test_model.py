import unittest,tempfile,pathlib,os,json,importlib.util
ROOT=pathlib.Path(__file__).resolve().parents[1]
class ModelTests(unittest.TestCase):
 def setUp(self):
  spec=importlib.util.spec_from_file_location('aqua_model',ROOT/'model.py');self.model=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.model)
 def test_tag_import_reads_configuration_without_selecting_command_tags(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'Export.txt';p.write_text('DmTag\tTags\tTag\n[NAME][100][1]\t[COMMENT][211][1]\t[TYPE][101][1]\nName\tComment\tData type\nLAB_A.RUN_S\t\tBinary Tag\nLAB_A.START_C\t\tBinary Tag\nLAB_B.RUN_S\t\tBinary Tag\n',encoding='utf-16');raw=p.read_bytes();stamp=p.stat().st_mtime_ns
   self.assertEqual(self.model.read_tag_names(p),['LAB_A.RUN_S','LAB_B.RUN_S']);self.assertEqual(p.read_bytes(),raw);self.assertEqual(p.stat().st_mtime_ns,stamp)
 def test_status_never_turns_missing_bad_or_stale_values_into_off(self):
  s={'agents':[{'online':True,'recording':True,'simulated':False,'observedAt':'2000-01-01T00:00:00Z','pumps':{'LAB_A.RUN_S':False},'observations':{'LAB_A.RUN_S':{'raw_value':0,'quality':'BAD','quality_code':0}}}],'gatewayConnected':True,'internetStatus':'UNREACHABLE','readOnly':True}
  view=self.model.present_status(s);self.assertFalse(view['gateway_ready']);self.assertEqual(view['rows'][0]['state'],'ไม่ทราบ');self.assertEqual(view['mode'],'ไฟล์ต้นทาง · WinCC ยังไม่ผ่านการตรวจรับ')
 def test_idle_agent_without_first_observation_stays_unknown(self):
  view=self.model.present_status({'agents':[{'online':True,'recording':False,'observedAt':None}]})
  self.assertEqual(view['observed'],'—');self.assertEqual(view['rows'],[])
 def test_settings_fail_closed_before_writing_through_source_alias(self):
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d);source=root/'source';source.mkdir();alias=root/'alias';alias.symlink_to(source,target_is_directory=True)
   with self.assertRaises(ValueError):self.model.prepare_profile(alias,{'sourceDirectory':str(source),'tags':['LAB_A.RUN_S']})
   self.assertEqual(list(source.iterdir()),[])
 def test_profiles_preserve_private_configuration_and_reject_invalid_names(self):
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d);source=root/'source';source.mkdir();state=root/'state';settings={'sourceDirectory':str(source),'tags':['LAB_A.RUN_S'],'timezoneOffset':'+07:00','mappingConfirmed':False}
   a=self.model.prepare_profile(state,settings);b=self.model.prepare_profile(state,settings);self.assertEqual(a,b);self.assertEqual(json.loads(a['config'].read_text())['tags'],['LAB_A.RUN_S']);self.assertEqual(a['config'].stat().st_mode&0o777,0o600)
   with self.assertRaises(ValueError):self.model.prepare_profile(state,{**settings,'tags':['bad;command']})
if __name__=='__main__':unittest.main()
