"""Behavioral regressions for user choices, revisions and bounded work."""
import copy,unittest
from unittest.mock import patch
import gradio as gr
import test_full_catalog as fixtures
from app import ui,full_pipeline as flow
from app.brief import content_policy
from app.model_budget import BudgetedModel
from connectors import ConnectorError


class UserControls(unittest.TestCase):
 def setUp(self):
  self.fixture=fixtures.FullFlowChecks();self.fixture.setUp()

 def test_product_is_choice_only(self):
  component=next(c for c in ui.build().config['components'] if c['props'].get('elem_id')=='product-choice')
  self.assertFalse(component['props']['filterable']);self.assertFalse(component['props']['allow_custom_value'])

 def test_soft_settings_clear_display_but_preserve_revision_context(self):
  state=ui.reset_studio(keep_revision=True)
  self.assertEqual(gr.skip(),state[8]);self.assertEqual([],state[6]);self.assertIsNone(state[7])
  self.assertIsNone(ui.reset_studio()[8])

 def test_standard_and_detailed_are_disjoint_targets(self):
  for channel in ('wechat','xhs','moments','poster'):
   with self.subTest(channel=channel):
    standard=content_policy(channel,'标准');detailed=content_policy(channel,'详细')
    self.assertLess(standard['min_chars'],detailed['min_chars'])
    self.assertLess(standard['max_chars'],detailed['max_chars'])

 def test_latest_revision_length_overrides_initial_brief_and_level(self):
  p=content_policy('moments','详细','写150字左右','缩短到100字以内，不要表情，不加话题标签')
  self.assertEqual(100,p['max_chars']);self.assertTrue(p['no_emoji']);self.assertFalse(p['tags'])

 def test_approximate_length_has_tolerance_but_upper_bound_is_strict(self):
  p=content_policy('moments','标准','150字左右')
  self.assertEqual((120,180),(p['min_chars'],p['max_chars']))
  self.assertEqual(100,content_policy('moments','标准','100字以内')['max_chars'])

 def test_revision_can_reverse_earlier_phrase_and_emoji_preferences(self):
  p=content_policy('xhs','标准','必须包含“移动办公”，不要表情，不加话题标签','不要出现“移动办公”，允许表情，加入话题标签')
  self.assertFalse(p['no_emoji']);self.assertTrue(p['tags'])
  self.assertEqual([],p['required_phrases']);self.assertEqual(['移动办公'],p['forbidden_phrases'])

 def test_failed_draft_is_kept_privately_for_requested_revision_but_not_displayed(self):
  report=flow.Report(status='failed',article={'lead':'SYNTHETIC-UNAPPROVED'})
  with patch.object(ui.pl,'run_task',return_value=report),patch.object(ui,'save_run') as save:
   save.return_value=__import__('pathlib').Path('synthetic.json')
   result=ui.run_ui('D14','新生','school','moments','','标准版','Windows','')
  self.assertNotIn('SYNTHETIC-UNAPPROVED',result[3])
  self.assertEqual(report.article,result[8]['article']);self.assertFalse(result[8]['approved'])

 def test_conflicting_long_copy_stops_before_network(self):
  report,client=self.fixture.execute(self.fixture.output,extra_request='改写成3000字')
  self.assertEqual('need_info',report.status);self.assertEqual(0,client.stats['model_requests'])

 def test_user_title_cannot_silently_be_ignored(self):
  report,client=self.fixture.execute(self.fixture.output,extra_request='标题改为“来聊聊你的新学期”')
  self.assertEqual('failed',report.status)
  self.assertFalse(next(c for c in report.checks if c['name']=='用户内容要求')['ok'])
  self.assertEqual(2,client.stats['model_requests'])

 def test_review_and_edit_receive_user_requirements_and_previous_article(self):
  report,client=self.fixture.execute(self.fixture.output,extra_request='用正式语气，不要表情',previous_article={'title':'真实上一稿'})
  self.assertEqual('qualified',report.status,report.checks)
  writer=client.prompts[0][1]['content'];reviewer=client.prompts[1][1]['content']
  self.assertIn('真实上一稿',writer);self.assertIn('正式语气',reviewer);self.assertIn('不要表情',reviewer)
  self.assertTrue(report.run['revision_context_used'])

 def test_user_can_request_one_image_without_false_material_shortage(self):
  report,_=self.fixture.execute(self.fixture.output,image_count=1)
  self.assertEqual('qualified',report.status);self.assertEqual('',report.image_shortage)

 def test_reviewer_receives_product_and_original_source_provenance(self):
  import json
  report,client=self.fixture.execute(self.fixture.output)
  review=json.loads(client.prompts[1][1]['content'])
  self.assertEqual(report.product_name,review['product_name'])
  source=review['source_facts'][0]
  for key in ('product_name','source_title','source_sha256','section','quote'):
   self.assertEqual(self.fixture.facts[0][key],source[key])

 def test_natural_store_invitation_is_not_rejected_for_missing_exact_keyword(self):
  output=copy.deepcopy(self.fixture.output);output['article']['cta']='带上您的需求，来店亲手体验。'
  report,_=self.fixture.execute(output)
  self.assertEqual('qualified',report.status,report.checks)

 def test_requested_facts_replace_weight_screen_template(self):
  facts=[{'category':c,'value':c} for c in ('尺寸与重量','操作系统','内存','接口')]
  picked=flow.writing_facts(facts,'xhs','不要重量，重点介绍接口','awareness')
  self.assertEqual(['接口'],[f['category'] for f in picked])

 def test_unused_model_image_filenames_do_not_trigger_regeneration(self):
  output=copy.deepcopy(self.fixture.output);output['images']=['made-up.jpg','https://example.invalid/not-a-source.png']
  report,client=self.fixture.execute(output)
  self.assertEqual('qualified',report.status,report.checks)
  self.assertEqual([self.fixture.image['id']],[i['id'] for i in report.images])
  self.assertEqual(2,client.stats['model_requests'])

 def test_redundant_body_invitation_can_be_removed_to_meet_explicit_length(self):
  output=copy.deepcopy(self.fixture.output)
  output['article']['lead']=''
  output['article']['body'][0]['text']='这款产品的屏幕为14英寸[K001]。请带上课表与需求清单，到店由专人协助核对配置是否满足课程安排。'
  report,_=self.fixture.execute(output,extra_request='缩短到60字以内')
  self.assertEqual('qualified',report.status,report.checks)
  self.assertIn('14英寸',report.article['body'][0]['text'])
  self.assertTrue(report.run.get('format_edits'))

 def test_citation_after_full_stop_survives_duplicate_cta_cleanup(self):
  output=copy.deepcopy(self.fixture.output);output['article']['lead']=''
  output['article']['body'][0]['text']='这款产品的屏幕为14英寸。[K001] 请带上课表与需求清单到店，我们协助核对具体适配情况。'
  report,_=self.fixture.execute(output,extra_request='缩短到60字以内')
  self.assertEqual('qualified',report.status,report.checks)
  self.assertIn('[K001]',report.article['body'][0]['text'])

 def test_call_budget_is_shared_and_enforced_before_network(self):
  class Client:
   def __init__(self):self.count=0
   def chat_json(self,*args,**kwargs):self.count+=1;return {'actual':'response'}
  client=Client();run={};budget=BudgetedModel(client,run)
  for _ in range(4):budget.chat_json([{'role':'user','content':'synthetic'}])
  with self.assertRaises(ConnectorError):budget.chat_json([])
  self.assertEqual(4,client.count);self.assertEqual(4,len(run['model_calls']))

 def test_failed_editor_audit_stops_without_outer_regeneration_loop(self):
  output=copy.deepcopy(self.fixture.output);claim='它让专注变得更容易。'
  output['article']['body'][0]['text']+=claim
  responses=[{'issues':[{'quote':claim,'reason':'无依据'}],'revised_article':self.fixture.output['article']},
             {'issues':[{'quote':'这款产品的屏幕为 14 英寸 [K001]。','reason':'合成测试：产品断言审稿失败'}]}]
  report,client=self.fixture.execute(output,review_responses=responses)
  self.assertEqual('failed',report.status);self.assertEqual(3,client.stats['model_requests'])
  self.assertEqual(3,len(report.run['model_calls']))

 def test_generic_consultation_advice_cannot_become_a_product_effect_failure(self):
  output=copy.deepcopy(self.fixture.output);advice='不同专业软件的环境要求不同，建议带上清单到店核对。'
  output['article']['body'][0]['text']+=advice
  report,_=self.fixture.execute(output,editor_issues=[{'quote':advice,'reason':'合成误报：资料未证明这一常识'}])
  self.assertEqual('qualified',report.status,report.checks)
  self.assertTrue(report.run.get('out_of_scope_review_notes'))


if __name__=='__main__':unittest.main()
