"""V2 source-bound catalogue, four-channel and media integration checks."""
import copy,hashlib,io,json,unittest
from unittest.mock import patch
from PIL import Image
from app import catalog,full_pipeline as flow
from app.channels import CHANNELS,GOALS,writing_brief
from app.ui import rich_article

class FullCatalogueChecks(unittest.TestCase):
 @unittest.skipUnless((catalog.KB_ROOT/'全库文件清单_SHA256.csv').exists(),'Private supplied v7 materials are not in the public source package.')
 def test_inventory_is_retained_but_only_image_backed_pc_profiles_are_selectable(self):
  rows=catalog.inventory()
  self.assertEqual(55,len(rows));self.assertEqual(55,len({r['id'] for r in rows}))
  self.assertTrue(any('MateDock 2' in p['name'] for p in rows));self.assertTrue(any('MateDock 3' in p['name'] for p in rows))
  self.assertEqual(10,sum(p['level']=='specification' for p in rows))
  ready=catalog.products()
  self.assertEqual(10,len(ready))
  self.assertTrue(all(p['level']=='specification' and catalog.image_count(p)>0 for p in ready))
  excluded=next(p for p in rows if 'MateDock 2' in p['name'])
  self.assertIsNone(catalog.find_product(excluded['id']))
  self.assertIsNone(catalog.find_product(excluded['name']))
  self.assertEqual({p['id'] for p in ready},{v for label,v in catalog.product_choices()})

 @unittest.skipUnless((catalog.KB_ROOT/'全库文件清单_SHA256.csv').exists(),'Private v7 evidence absent.')
 def test_every_catalogue_fact_has_literal_quote_and_fingerprint(self):
  for item in catalog.products():
   text=catalog.read_verified(item['source'])[0].decode('utf-8-sig');facts=catalog.facts_for(item)
   self.assertTrue(facts,item['name'])
   for fact in facts:
    self.assertTrue(all(q in text for q in fact['quotes']),fact['id'])
    self.assertEqual(item['sha256'],fact['source_sha256'])

 @unittest.skipUnless(catalog.REVIEW_FILE.exists(),'Private visual-review metadata absent.')
 def test_reviewed_originals_match_exact_hash_and_no_duplicate_views(self):
  for item in catalog.products():
   for asset in catalog.assets_for(item):
    self.assertTrue(asset['actual_view']);self.assertEqual(asset['sha256'],catalog.read_verified(asset['file'])[1])
   for key,policy in CHANNELS.items():
    picked=flow._select_images(item,key,6)
    self.assertLessEqual(len(picked),policy['max_images'])
    self.assertEqual(len(picked),len({i['view_group'] for i in picked}))

 def test_four_channels_have_shared_explicit_limits(self):
  self.assertEqual({'wechat','xhs','moments','poster'},set(CHANNELS))
  self.assertEqual((2,4),(CHANNELS['wechat']['min_images'],CHANNELS['wechat']['max_images']))
  self.assertEqual((3,6),(CHANNELS['xhs']['min_images'],CHANNELS['xhs']['max_images']))

 def test_advice_and_explicit_refusals_are_not_product_promises(self):
  self.assertFalse(flow.assertion_hits('最好先带上常用外设到店核对，不能保证所有设备兼容。'))
  self.assertTrue(flow.assertion_hits('这是最好的电脑，保证所有设备兼容。'))
  self.assertFalse(flow.assertion_hits('先别问“最轻”，很多新生一上来就问哪款更轻便。'))
  self.assertFalse(flow.assertion_hits('选购前最好列一份课程清单，最好带着自己的外设到店检查。'))
  self.assertTrue(flow.assertion_hits('先别问最轻，这台电脑全网最轻。'))
  self.assertFalse(flow.assertion_hits('带着需求到店，做出最适合自己的选择。'))
  self.assertTrue(flow.assertion_hits('这台是最适合大学生的电脑。'))
  self.assertFalse(flow.assertion_hits('新生往往在性能、便携与价格间犹豫。其尺寸与比例对长时间阅读很重要。若仅需基础办公与网页浏览，只有“更适合你当下阶段”的选择。'))
  self.assertFalse(flow.assertion_hits('这样得出的结论更接近真实体验。让店员帮你匹配最合适的配置组合。'))
  self.assertTrue(flow.assertion_hits('这款仅需2999元，价格实惠。这台更适合你。我们真实体验发现性能提升。'))
  self.assertFalse(flow.assertion_hits('第一时间核对课程要求，最好选择符合自己任务的配置，找店员匹配最合适的配置组合。'))
  self.assertTrue(flow.assertion_hits('这款电脑行业第一，在第一时间实现行业第一。'))

class FullFlowChecks(unittest.TestCase):
 def setUp(self):
  self.item={'id':'SYNTHETIC','name':'SYNTHETIC Product','source':'fixture.md','sha256':'synthetic','level':'specification','folder':'fixture','url':'https://example.invalid'}
  self.facts=[{'id':'K001','category':'显示','value':'14 英寸','quote':'14 英寸','quotes':['14 英寸'],'section':'显示','caveat':'','source_title':'SYNTHETIC source','source_sha256':'synthetic','product_name':'SYNTHETIC Product'}]
  stream=io.BytesIO();Image.new('RGB',(12,8),'blue').save(stream,format='PNG');self.raw=stream.getvalue()
  self.image={'id':'I001','file':'synthetic.png','sha256':hashlib.sha256(self.raw).hexdigest(),'view_group':'hero-fixture','name':'synthetic','actual_view':'合成测试蓝色块','source_title':'SYNTHETIC image','usage_limit':'合成测试'}
  self.output={'scene_judgement':{'audience':'测试受众','scene':'测试场景','problems':[],'assumptions':[]},'strategy':{'selected_points':[{'category':'显示','fact_ids':['K001'],'why':'测试'}],'dropped_points':[]},
   'article':{'title':'','lead':'选购前不妨先列出自己的使用需求，确认每天处理哪些文档，以及常用的软件和外设。',
   'body':[{'text':'这款产品的屏幕为 14 英寸 [K001]。到店之前可以整理日常任务清单，体验时按自己的阅读习惯查看界面，再确认具体销售配置。','fact_ids':['K001']}],
   'cta':'欢迎到店查看实物，或留言说说你的具体使用需求。','tags':[]},'images':[],'notes_for_review':[]}

 def execute(self,output,channel='moments',**kwargs):
  class Model:
   model='SYNTHETIC';stats={'model_requests':0}
   def chat_json(self,*args,**kwargs):
    self.stats['model_requests']+=1
    self.prompts=getattr(self,'prompts',[])+[copy.deepcopy(args[0])]
    return copy.deepcopy(output)
  client=Model()
  kwargs.setdefault('marketing_goal','store')
  with patch.object(catalog,'find_product',return_value=self.item),patch.object(catalog,'facts_for',return_value=self.facts),patch.object(catalog,'assets_for',return_value=[self.image]),patch.object(catalog,'read_verified',return_value=(self.raw,self.image['sha256'])):
   report=flow.run_task(product='SYNTHETIC',scene='门店到访',platform=channel,detail_level='标准',model_client=client,**kwargs)
  return report,client

 def test_new_flow_writes_from_source_without_human_signatures(self):
  report,_=self.execute(self.output)
  self.assertEqual('qualified',report.status,report.checks)
  self.assertEqual('SYNTHETIC Product',report.product_name)
  self.assertEqual(0,report.run['source_stats']['api_requests'])
  self.assertIn('data:image/png;base64',rich_article(report))

 def test_awareness_cannot_silently_turn_into_store_conversion(self):
  report,client=self.execute(self.output,marketing_goal='awareness')
  self.assertEqual('failed',report.status)
  self.assertFalse(next(c for c in report.checks if c['name']=='营销目标与行动引导')['ok'])
  self.assertIn('营销目标（用户已选，不可变更）：种草了解',client.prompts[0][1]['content'])

 def test_selected_goal_is_preserved_in_strategy_and_export_even_if_model_changes_it(self):
  output=copy.deepcopy(self.output);output['scene_judgement']['goal']='到店咨询'
  output['article']['cta']='留言说说你的日常场景，收藏这份关注点，继续了解具体配置。'
  report,_=self.execute(output,marketing_goal='awareness')
  self.assertEqual('qualified',report.status,report.checks)
  self.assertEqual('种草了解',report.scene_judgement['goal'])
  self.assertIn('种草了解',flow.to_text(report))

 def test_unknown_goal_stops_before_model(self):
  report,client=self.execute(self.output,marketing_goal='unknown')
  self.assertEqual('need_info',report.status)
  self.assertEqual(0,client.stats['model_requests'])

 def test_awareness_rejects_renamed_purchase_checklist(self):
  output=copy.deepcopy(self.output)
  output['article']['title']='先别急，选购指南来了'
  output['article']['cta']='收藏这篇，评论说说你的日常场景。'
  report,_=self.execute(output,marketing_goal='awareness')
  self.assertEqual('failed',report.status)
  self.assertFalse(next(c for c in report.checks if c['name']=='营销目标与行动引导')['ok'])

 def test_each_goal_requires_its_own_next_action(self):
  for goal,cta in [('enterprise','留言整理岗位和软件需求，作为进一步企业咨询的起点。'),('decision','核对自己的用途与配置清单，再做选购选择。'),('store','欢迎到店带上使用需求，亲手看一看实物。')]:
   with self.subTest(goal=goal):
    output=copy.deepcopy(self.output);output['article']['cta']=cta
    report,_=self.execute(output,marketing_goal=goal)
    self.assertEqual('qualified',report.status,report.checks)

 def test_unknown_numeric_claim_stays_blocked_after_two_repairs(self):
  bad=copy.deepcopy(self.output);bad['article']['body'][0]['text']+=' 续航 99 小时。'
  report,client=self.execute(bad)
  self.assertEqual('blocked',report.status);self.assertEqual(3,client.stats['model_requests'])
  self.assertNotIn('data:image',rich_article(report))

 def test_repair_receives_actual_previous_draft_not_only_error_labels(self):
  bad=copy.deepcopy(self.output);bad['article']['body'][0]['text']+=' 续航 99 小时。'
  report,client=self.execute(bad)
  repair=client.prompts[1][1]['content']
  self.assertIn('上一轮待修订输出',repair)
  self.assertIn('续航 99 小时',repair)
  self.assertEqual('blocked',report.status)

 def test_unknown_visible_citation_cannot_pass(self):
  bad=copy.deepcopy(self.output);bad['article']['body'][0]['text']=bad['article']['body'][0]['text'].replace('[K001]','[K999]')
  report,_=self.execute(bad)
  self.assertIn(report.status,('failed','blocked'))

 def test_changed_image_review_pin_stops_before_model(self):
  with patch.object(catalog,'find_product',return_value=self.item),patch.object(catalog,'facts_for',return_value=self.facts),patch.object(catalog,'assets_for',return_value=[self.image]),patch.object(catalog,'read_verified',return_value=(b'changed','different')):
   report=flow.run_task(product='SYNTHETIC',scene='门店到访',platform='moments',mode='cache')
  self.assertEqual('failed',report.status);self.assertEqual('source_changed',report.run['failure_kind'])

 def test_missing_product_asks_before_model(self):
  with patch.object(catalog,'find_product',return_value=None):report=flow.run_task(product='',platform='wechat',scene='职场差旅')
  self.assertEqual('need_info',report.status);self.assertTrue(report.questions)

 def test_discovery_card_does_not_become_complete_specification(self):
  self.item['level']='discovery';report,_=self.execute(self.output)
  self.assertEqual('restricted',report.status);self.assertIn('发现卡',report.message)

 def test_internal_writing_instructions_are_never_publishable_copy(self):
  bad=copy.deepcopy(self.output);bad['article']['body'][0]['text']+='完整保留本条原文中的版本，不合并不同配置。'
  report,_=self.execute(bad)
  self.assertIn(report.status,('failed','blocked'))
  self.assertTrue(any(h['category']=='提示词泄漏' for h in report.rewrite_hits))

 def test_comparison_across_comma_is_not_missed(self):
  bad=copy.deepcopy(self.output);bad['article']['body'][0]['text']+='相比传统屏幕，纵向空间更大，可以减少滚动次数。'
  report,_=self.execute(bad)
  self.assertIn(report.status,('failed','blocked'))
  self.assertTrue(any(h['category']=='无依据对比' for h in report.rewrite_hits))

 def test_editorial_deletion_preserves_supported_sentence_and_qualifiers(self):
  out=copy.deepcopy(self.output)
  original='这款产品的屏幕为 14 英寸 [K001]。'
  out['article']['body']=[{'text':original+'实际容量为 930 GB。','fact_ids':['K001']}]
  cleaned,removed=flow.remove_risky_body_sentences(out,[{'word':'930 GB','category':'无依据数字','sentence':out['article']['body'][0]['text']}])
  self.assertEqual(original,cleaned['article']['body'][0]['text'])
  self.assertEqual(['K001'],cleaned['article']['body'][0]['fact_ids'])
  self.assertEqual(1,len(removed));self.assertIn('930 GB',out['article']['body'][0]['text'])

 def test_deletion_cannot_turn_an_empty_body_into_a_qualified_draft(self):
  out=copy.deepcopy(self.output);out['article']['body']=[{'text':'续航 99 小时。[K001]','fact_ids':['K001']}]
  cleaned,_=flow.remove_risky_body_sentences(out,[{'word':'99 小时','category':'无依据数字','sentence':''}])
  self.assertEqual([],cleaned['article']['body'])
  report,_=self.execute(cleaned)
  self.assertNotEqual('qualified',report.status)

 def test_xhs_real_blank_line_paragraphs_inside_one_item_are_counted(self):
  out=copy.deepcopy(self.output)
  out['article']['title']='测试选购提醒'
  text=out['article']['body'][0]['text']+'可以提前准备自己的文件与常用外设，到店核对具体配置与实际需求。'
  out['article']['body']=[{'text':'\n\n'.join([text]*4),'fact_ids':['K001']}]
  out['article']['tags']=['#选购','#到店','#需求','#型号']
  report,_=self.execute(out,channel='xhs')
  self.assertEqual(4,len(report.article['body']))
  self.assertTrue(next(c for c in report.checks if c['name']=='渠道结构与篇幅')['ok'],report.checks)
  self.assertEqual('restricted',report.status)
  self.assertEqual(1,len(report.images))
  self.assertIn('仅有1张',report.image_shortage)
  self.assertEqual(1,rich_article(report).count('<img'))

 def test_screen_effect_synonym_cannot_evade_evidence_check(self):
  bad=copy.deepcopy(self.output);bad['article']['body'][0]['text']+='纵向空间更充裕，能减少翻页次数。'
  report,_=self.execute(bad)
  self.assertEqual('failed',report.status)
  self.assertTrue(any(h['category']=='无依据效果' for h in report.rewrite_hits))

 def test_unsupported_display_ratio_is_a_numeric_claim(self):
  bad=copy.deepcopy(self.output);bad['article']['body'][0]['text']+='屏幕为 16:9 [K001]。'
  report,_=self.execute(bad)
  self.assertEqual('blocked',report.status)
  self.assertTrue(any(h['word']=='16:9' for h in report.rewrite_hits))

 def test_inaccurate_screen_size_in_title_cannot_hide_behind_colloquial_unit(self):
  bad=copy.deepcopy(self.output);bad['article']['title']='15寸屏幕如何选择'
  report,_=self.execute(bad)
  self.assertEqual('blocked',report.status)
  self.assertTrue(any(h['word']=='15寸' for h in report.rewrite_hits))

 def test_scene_tone_cannot_turn_specs_into_unsupported_reading_benefits(self):
  bad=copy.deepcopy(self.output);bad['article']['body'][0]['text']+='同一页看到更多内容，减少频繁滚动的次数。'
  report,_=self.execute(bad)
  self.assertEqual('failed',report.status)
  self.assertTrue(any(h['category']=='无依据效果' for h in report.rewrite_hits))

if __name__=='__main__':unittest.main()
