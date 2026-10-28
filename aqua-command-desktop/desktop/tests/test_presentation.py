import unittest,pathlib,sys,datetime,copy,json
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from presentation import console_state
NOW=datetime.datetime(2026,10,28,8,30,5,tzinfo=datetime.timezone.utc)
STAMP='2026-10-28T08:30:05Z'
def fixture():
 return {'captureAllowed':True,'transferAllowed':True,'agents':[{'id':'PC-01','role':'agent','online':True,'lastSeen':STAMP,'sourceAdapter':'wincc-csv','simulated':False,'recording':True,'captureAllowed':True,'transferAllowed':True,'observedAt':STAMP,'lastExport':STAMP,'snapshots':12,'pending':2,'acked':10,'lastAckAt':STAMP,'pumps':{'LAB_A.RUN_S':False},'observations':{'LAB_A.RUN_S':{'raw_value':0,'quality_code':128,'read_error':0,'quality':'GOOD'}},'gatewayAuthenticated':True,'lanState':'LAN_CONNECTED'}],'gateway':{'id':'PC-04','online':True,'lastSeen':STAMP,'pending':1,'upstreamDelivered':9,'notificationMode':'dry-run','notificationSent':2,'notificationPending':1,'lastDelivery':STAMP,'egress':{'status':'SIMULATED_AVAILABLE','mode':'simulated','checkedAt':STAMP},'messages':[]},'central':{'id':'CENTRAL-LAB','online':True,'lastSeen':STAMP},'events':[]}
class PresentationTests(unittest.TestCase):
 def state(self,s=None,mode='csv',**kw):return console_state(s or {},mode,{'sourceDirectory':'approved-csv','tags':['LAB_A.RUN_S'],'mappingConfirmed':True},4173,session_active=bool(s),now=NOW,**kw)
 def test_idle_never_invents_live_hostnames_or_nic_addresses(self):
  v=self.state();self.assertEqual(v['source_mode'],'FILE');self.assertEqual(len(v['devices']),3);self.assertTrue(all(d['hostname'] is None and d['observed_ips']==[] for d in v['devices']));self.assertTrue(all(d['reachability']=='NOT_CHECKED' for d in v['devices']));self.assertEqual(v['devices'][0]['endpoint'],'127.0.0.1:4181');self.assertTrue(all(m['value'] is None for m in v['metrics'].values()))
 def test_runtime_unavailable_cannot_display_file_or_simulated_readings(self):
  v=self.state(fixture(),mode='runtime');self.assertFalse(v['source_available']);self.assertEqual(v['signals'],[]);self.assertEqual(v['source_mode'],'UNAVAILABLE')
 def test_real_file_is_not_labelled_live_wincc_and_zero_is_preserved(self):
  v=self.state(fixture());self.assertEqual(v['source_mode'],'FILE');r=v['signals'][0];self.assertEqual(r['raw'],0);self.assertEqual(r['state'],'OFF');self.assertEqual(r['freshness'],'CURRENT');self.assertIn('+07:00',r['observed'])
 def test_bad_and_unconfirmed_values_do_not_become_off(self):
  for q in ('BAD','UNVERIFIED_MAPPING','UNSUPPORTED_VALUE'):
   s=fixture();s['agents'][0]['observations']['LAB_A.RUN_S']['quality']=q;v=self.state(s);self.assertEqual(v['signals'][0]['state'],'UNKNOWN');self.assertEqual(v['signals'][0]['quality'],q)
 def test_old_sample_and_future_clock_are_unknown_without_mutating_raw_quality(self):
  for stamp,want in [('2026-10-28T08:29:00Z','STALE'),('2026-10-28T08:31:00Z','CLOCK_SKEW')]:
   s=fixture();s['agents'][0]['observedAt']=stamp;v=self.state(s);r=v['signals'][0];self.assertEqual(r['state'],'UNKNOWN');self.assertEqual(r['quality'],'GOOD');self.assertEqual(r['freshness'],want)
 def test_fresh_status_timestamp_cannot_refresh_an_old_sample(self):
  s=fixture();s['time']=STAMP;s['agents'][0]['observedAt']='2026-10-28T08:20:00Z';self.assertEqual(self.state(s)['signals'][0]['freshness'],'STALE')
 def test_stale_gateway_cannot_advertise_verified_internet(self):
  s=fixture();s['gateway'].update(online=False,lastSeen='2026-10-28T08:20:00Z');s['gateway']['egress']={'status':'VERIFIED','mode':'real','checkedAt':'2026-10-28T08:20:00Z'};v=self.state(s);self.assertFalse(v['egress']['available']);self.assertEqual(v['egress']['freshness'],'CACHED');self.assertIsNone(v['devices'][0]['internet'])
 def test_missing_gateway_placeholder_zero_is_not_an_observed_zero(self):
  s=fixture();s['gateway']={'online':False,'upstreamDelivered':0,'pending':None};v=self.state(s);self.assertIsNone(v['metrics']['central']['value']);self.assertIsNone(v['metrics']['gateway']['value']);s=fixture();s['gateway']['upstreamDelivered']=0;self.assertEqual(self.state(s)['metrics']['central']['value'],0)
 def test_partial_local_total_reports_coverage_and_not_a_complete_zero(self):
  s=fixture();s['agents'].append({'id':'PC-02','online':False});m=self.state(s)['metrics']['local'];self.assertEqual(m['value'],2);self.assertTrue(m['partial']);self.assertEqual(m['coverage'],'1/2')
 def test_central_accepted_and_gateway_ack_are_distinct_receipts(self):
  v=self.state(fixture());self.assertEqual(v['metrics']['central']['value'],9);self.assertEqual(v['gateway_acked'],10);self.assertEqual(v['notification']['count'],2);self.assertEqual(v['notification']['mode'],'dry-run')
 def test_no_per_item_receipt_last_good_or_os_login_is_fabricated(self):
  v=self.state(fixture());r=v['signals'][0];self.assertIsNone(r['last_good']);self.assertIsNone(r['sample_received']);self.assertIsNone(r['receipt']);self.assertEqual(v['scada_auth'],'NOT_AVAILABLE');self.assertFalse(v['capabilities']['browse']);self.assertFalse(v['capabilities']['item_rules'])
 def test_safe_view_excludes_secrets_and_does_not_mutate_backend_state(self):
  s=fixture();s['secret']='sensitive';s['gateway']['token']='private';s['events']=[{'id':'PC-01:1','time':STAMP,'kind':'RETRY','message':'secret=private token=hidden'}];before=copy.deepcopy(s);v=self.state(s);body=json.dumps(v);self.assertNotIn('sensitive',body);self.assertNotIn('private',body);self.assertNotIn('hidden',body);self.assertEqual(s,before)
 def test_null_optional_containers_and_extreme_timestamp_fail_to_unknown(self):
  for field in ('agents','events'):
   s=fixture();s[field]=None;self.state(s)
  s=fixture();s['gateway']['messages']=None;s['agents'][0]['disk']=True;s['agents'][0]['lastSeen']='9999-12-31T23:59:59Z';v=self.state(s);self.assertEqual(v['devices'][0]['last_seen'],'Not reported')
 def test_ack_notification_and_source_counters_keep_cached_provenance(self):
  s=fixture();s['agents'][0].update(online=False,lastSeen='2026-10-28T08:20:00Z');s['gateway'].update(online=False,lastSeen='2026-10-28T08:20:00Z');v=self.state(s);self.assertTrue(v['ack_metric']['cached']);self.assertTrue(v['notification']['count_metric']['cached']);self.assertTrue(v['sources'][0]['cached']);self.assertIn('+07:00',v['ack_metric']['as_of'])
 def test_bearer_and_quoted_json_secret_values_are_redacted_completely(self):
  for message in ('Authorization: Bearer opaque-secret','{"token":"opaque-secret"}','password="two word secret"'):
   s=fixture();s['events']=[{'id':'PC-01:1','time':STAMP,'kind':'ERROR','message':message}];body=json.dumps(self.state(s));self.assertNotIn('opaque-secret',body);self.assertNotIn('word secret',body)

class ReportedModeTests(unittest.TestCase):
 def test_reported_simulation_is_visible_even_when_selected_source_is_file(self):
  s=fixture();s['agents'][0]['simulated']=True
  v=console_state(s,'csv',{'tags':['LAB_A.RUN_S']},4173,session_active=True,now=NOW)
  self.assertEqual(v['signals'][0]['mode'],'SIMULATED');self.assertEqual(v['reading_modes'],['SIMULATED']);self.assertEqual(v['source_mode'],'FILE')

if __name__=='__main__':unittest.main()
