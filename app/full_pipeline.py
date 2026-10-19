"""Full-catalogue, four-channel writing with source-bound evidence and real media."""
from __future__ import annotations
import json,re,copy
from datetime import datetime
from dataclasses import asdict
from . import catalog,compliance
from .channels import CHANNELS,SCENES,GOALS,channel_key,goal_key,writing_brief,scene_brief
from .brief import content_policy,request_issues
from .model_budget import BudgetedModel
from .pipeline import Report,FACT_MARK,_valid_output,_article_text,_check,to_text,STATUS_LABEL
from connectors import ConnectorError,ModelScopeClient,IMAClient,LiveSourceReader

def cache_mode_note():
    return '本地资料模式：使用已导入的 v7 原件并核对文件清单指纹，资料日期 2026-10-17；未验证远端当前最新。'

def _source_reader(product,images,mode):
    if mode!='live':return None
    ima=IMAClient(max_media_info_calls=12)
    base=ima.find_base('任德耀新建华为PC知识库');mapping={}
    wanted=[product['source']]+[i['file'] for i in images]
    from pathlib import PurePosixPath
    for folder in {str(PurePosixPath(f).parent) for f in wanted}:
        entries=ima.list_path(base['kb_id'],[base['kb_name'],*PurePosixPath(folder).parts])
        for entry in entries:
            path=folder+'/'+entry['title']
            if path in wanted:mapping[path]=entry['media_id']
    return LiveSourceReader(ima,mapping)

def _select_images(product,channel,count):
    choices=catalog.assets_for(product)
    # Prefer a complete front/product view, then real scenes, then details.
    choices=sorted(choices,key=lambda i:(0 if i['view_group'].startswith('hero') else 1 if i['view_group'].startswith('scene') else 2,i['id']))
    chosen=[];seen=set();limit=min(CHANNELS[channel]['max_images'],max(1,int(count or CHANNELS[channel]['max_images'])))
    for image in choices:
        if image['view_group'] in seen:continue
        seen.add(image['view_group']);chosen.append(dict(image))
        if len(chosen)>=limit:break
    return chosen

def _normalize(value):return re.sub(r'[\s,*®™]','',value).lower().replace('英寸','寸').replace('克','g')

def writing_facts(facts,channel,request,goal='decision'):
    """Retrieve enough relevant source fields, rather than flooding a short channel with every specification."""
    curated=[]
    for fact in facts:
        if fact['category']=='屏幕':
            for label in ('尺寸','屏幕比例'):
                match=re.search(r'(?:^|\n)'+label+r'\s*\n+\s*([^\n]+)',fact['value'])
                if match:
                    value=match.group(1).strip()
                    curated.append({**fact,'category':'屏幕'+label,'value':value,'quote':value,'quotes':[value],
                                    'caveat':'只陈述这一原文参数，不据此承诺视觉效果。'})
        else:curated.append(dict(fact))
    if channel=='moments':
        desired='屏幕' if '屏幕' in request else '操作系统' if '系统' in request else '重量'
        selected=[f for f in curated if desired in f['category']][:1] or curated[:1]
    elif channel=='poster':
        selected=[]
        for category in ('尺寸与重量','屏幕尺寸','操作系统'):
            selected += [f for f in curated if f['category']==category][:1]
        selected=selected or curated[:3]
    else:
        selected=[f for f in curated if f['category'] in ('尺寸与重量','屏幕尺寸','屏幕屏幕比例','操作系统','存储','内存','电池','处理器')]
        if any(w in request for w in ('AI','小艺','鸿蒙','协同','分享','应用')):
            selected += [f for f in curated if f['category']=='特色应用']
        selected=selected or curated
    if goal=='awareness' and channel in ('wechat','xhs'):
        themes=[f for f in selected if f['category'] in ('尺寸与重量','屏幕尺寸')]
        selected=(themes or selected)[:2]
        if any(w in request for w in ('系统','鸿蒙','HarmonyOS','Windows','软件')):
            selected += [f for f in curated if f['category']=='操作系统'][:1]
    aliases={'屏幕':('屏幕','显示','分辨率','色域','亮度'),'尺寸与重量':('重量','便携','轻薄'),'处理器':('处理器','CPU','性能'),'存储':('存储','硬盘','SSD'),'内存':('内存','RAM'),'电池':('电池','续航'),'接口':('接口','外设','连接口'),'操作系统':('系统','Windows','HarmonyOS','软件'),'特色应用':('AI','小艺','协同','分享'),'键盘和触控板':('键盘','触控板'),'摄像头':('摄像头','视频会议'),'音频':('音频','声音')}
    wanted=[];excluded=set()
    for category,words in aliases.items():
        for word in words:
            for match in re.finditer(re.escape(word),request,re.I):
                prefix=re.split(r'[，,。；;\n]',request[:match.start()])[-1]
                if re.search(r'不要|不提|别写|不写|避免|去掉|删除|不强调',prefix[-12:]):excluded.add(category)
                elif category not in wanted:wanted.append(category)
    if wanted:
        # Explicit user topics take precedence over generic weight/screen defaults.
        requested=[]
        for category in wanted:
            if category in excluded:continue
            pool=curated if category=='屏幕' and not re.search(r'分辨率|色域|亮度|刷新率|护眼|柔光',request) else facts
            matching=[f for f in pool if f['category'].startswith(category)]
            if category=='屏幕' and channel in ('moments','poster'):matching=matching[:1]
            requested+=matching
        if requested:selected=requested[:3 if channel=='poster' else 2 if channel=='moments' else 8]
    selected=[f for f in selected if not any(f['category'].startswith(c) for c in excluded)]
    return [{**f,'id':f'K{index+1:03d}'} for index,f in enumerate(selected)]

def assertion_hits(text):
    hits=[]
    for sentence in re.split(r'[。！？!?；;\n，,]',text):
        for hit in compliance.check_request(sentence):
            if hit.word=='第一' and not re.search(r'全球|世界|全国|国内|行业|全网|首创',sentence):
                non_sequence=re.sub(r'第一(?:时间|印象|反应|感觉|学期|件事|道|层|位要考虑|[天次周月年步章节眼条项点件个台部本款])','',sentence)
                if '第一' not in non_sequence:continue
            if hit.word=='最好' and re.search(r'^(?:建议|选购时|购买前|到店时)?最好(?:选择|去|亲自|根据)',sentence.strip()):continue
            # Literal words inside ordinary selection advice are not ad claims.
            if hit.category=='无依据对比' and hit.word.startswith('比例'):continue
            if hit.word=='仅需' and re.search(r'仅需(?:要)?(?:基础|日常|简单|文档|网页|办公|查看|确认|准备|填写)',sentence):continue
            if hit.word=='价格' and re.search(r'(?:性能|便携|预算|选择).{0,12}价格.{0,8}(?:犹豫|权衡|之间|间)',sentence) and not re.search(r'\d+\s*元|￥|优惠|低价|实惠|便宜|立减|补贴|特价',sentence):continue
            if hit.word in ('更适合','最适合','最合适') and re.search(r'(?:只有|找到|寻找|匹配|挑选|选到|挑出).{0,8}(?:更适合|最适合|最合适)(?:你|自己|自身|个人|的配置)',sentence) and not re.search(r'这台|这款|本产品|本机|该机',sentence):continue
            if hit.word=='真实体验' and re.search(r'(?:接近|到店|现场|亲自|建议|请|可以).{0,16}真实体验',sentence) and not re.search(r'(?:我|我们|客户|用户).{0,10}真实体验|真实体验(?:表明|证明|发现|显示)',sentence):continue
            if hit.word=='最好' and re.search(r'最好(?:还是|先|提前|携带|带上|带着|确认|核对|询问|请|到店|实地|亲手|在现场|把|将|列|准备|留意|了解|核实|检查|联系|结合|考虑|记住|保留|的验证方式|的方式是)',sentence):continue
            if hit.word=='实测' and re.search(r'(?:建议|请|不妨|可以).{0,40}实测|去门店实测|到店.{0,8}实测',sentence) and not re.search(r'我.{0,8}实测',sentence):continue
            if hit.word=='价格' and not re.search(r'\d+\s*元|￥|¥|低|便宜|优惠|立减|补贴|特价',sentence) and re.search(r'配置|预算|核对|确认|咨询|为准|核验',sentence):continue
            if hit.word=='最适合' and re.search(r'(?:选择|找到|做出|找出|挑出).{0,8}最适合(?:自己|自身|个人)',sentence) and not re.search(r'这台|这款|本产品|本机',sentence):continue
            start=sentence.find(hit.word)
            prefix=sentence[max(0,start-16):start] if start>=0 else ''
            if re.search(r'不保证|无法|不能|不作|不做|不要|不应|没有|并非|避免|不是|不代表|别问',prefix):continue
            if hit.category in ('无依据对比','绝对化宣传') and re.search(r'(?:问|想知道|关心|纠结|考虑).{0,12}(?:哪款|哪台|哪一款|是否|能否|哪个|什么)',sentence):continue
            hits.append(hit)
        if re.search(r'比(?:传统|普通|同类|上一?代|其他).{0,35}(?:更多|更少|减少|提升|更快|更强)',sentence):
            hits.append(compliance.Hit('无依据对比','产品效果对比','rewrite','资料没有同条件对比证据，不能推导提升或减少',sentence))
    return compliance._dedupe(hits)

def _evaluate(rep,output,facts,policy,channel):
    # Some valid JSON writers return body strings. Preserve actual prose and
    # visible citations while adapting this harmless schema variation.
    output=copy.deepcopy(output)
    if isinstance(output,dict):
        # Media is exclusively selected and hash-verified by the connector.
        # Unused model filenames must neither be downloaded nor force a rewrite.
        if output.get('images'):rep.run.setdefault('ignored_model_images',[]).append(output['images'])
        output['images']=[]
    if isinstance(output,dict) and isinstance(output.get('article'),dict) and isinstance(output['article'].get('body'),list):
        output['article']['body']=[{'text':b,'fact_ids':sorted(set(FACT_MARK.findall(b)))} if isinstance(b,str) else b for b in output['article']['body']]
    if not _valid_output(output):
        rep.status='failed';rep.message='模型输出结构不完整，未展示为成稿。'
        rep.checks.append(_check('模型结构',False,rep.message));return
    rep.article=output.get('article',{});rep.scene_judgement=output.get('scene_judgement',{})
    def chars(article):return len(re.sub(r'\s','',FACT_MARK.sub('',_article_text(article))))
    request='\n'.join(str(rep.run.get('input',{}).get(k,'')) for k in ('free_text','extra_request'))
    if chars(rep.article)>policy['max_chars'] and rep.article.get('lead') and not re.search(r'导语|副标题',request):
        candidate={**rep.article,'lead':''}
        if policy['min_chars']<=chars(candidate)<=policy['max_chars'] and not request_issues(candidate,policy,_article_text(candidate)):
            rep.run.setdefault('format_edits',[]).append({'removed_optional_lead':rep.article['lead']})
            rep.article['lead']=''
    if chars(rep.article)>policy['max_chars'] and rep.article.get('cta'):
        for block in rep.article.get('body',[]):
            # Remove a duplicated invitation, never a source-backed fact or number.
            pieces=re.findall(r'[^。！？!?；;\n]+[。！？!?；;\n]*',block['text'])
            for piece in pieces:
                # A citation after a full stop belongs to the preceding fact,
                # not to the following invitation. Keep the citation intact.
                prefix=re.match(r'^\s*(?:\[\s*K\d+\s*\]\s*)+',piece)
                anchor=prefix.group() if prefix else '';invitation_text=piece[len(anchor):]
                invitation=bool(re.search(r'(?:欢迎|请|建议|带上|带着|来).{0,20}(?:到店|进店|门店|来店|莅临|店内|评论|留言)',invitation_text))
                if invitation and not FACT_MARK.search(invitation_text) and not compliance.UNIT_PATTERN.search(invitation_text):
                    candidate=copy.deepcopy(rep.article)
                    index=rep.article['body'].index(block);candidate['body'][index]['text']=block['text'].replace(piece,anchor,1)
                    if chars(candidate)>=policy['min_chars']:
                        block['text']=candidate['body'][index]['text']
                        rep.run.setdefault('format_edits',[]).append({'removed_duplicate_cta':invitation_text})
                        if chars(rep.article)<=policy['max_chars']:break
            if chars(rep.article)<=policy['max_chars']:break
    # Blank-line separated prose inside one JSON body item is real paragraphing.
    # Split it before validation rather than rejecting an otherwise valid layout.
    if channel in ('wechat','xhs'):
        paragraphs=[]
        for block in rep.article.get('body',[]):
            pieces=[p.strip() for p in re.split(r'\n\s*\n',block['text']) if p.strip()]
            if len(pieces)>1:
                paragraphs.extend({'text':p,'fact_ids':sorted(set(FACT_MARK.findall(p)))} for p in pieces)
            else:paragraphs.append(block)
        rep.article['body']=paragraphs
    rep.strategy=output.get('strategy',{})
    goal=rep.run.get('marketing_goal')
    if goal in GOALS:
        rep.scene_judgement['goal']=GOALS[goal]['label']
        rep.strategy['marketing_goal']=GOALS[goal]['label']
    known={f['id']:f for f in facts}
    def canonical(fid):
        match=re.fullmatch(r'K0*(\d+)',fid)
        candidate=f'K{int(match.group(1)):03d}' if match else fid
        return candidate if candidate in known else fid
    for key in ('title','lead','cta'):rep.article[key]=FACT_MARK.sub(lambda m:'['+canonical(m.group(1))+']',rep.article.get(key,''))
    repairs=[]
    for body in rep.article.get('body',[]):
        body['text']=FACT_MARK.sub(lambda m:'['+canonical(m.group(1))+']',body['text'])
        declared={canonical(fid) for fid in body.get('fact_ids',[])}
        visible=set(FACT_MARK.findall(body['text']))
        # Render source links from structured IDs; IDs are never evidence by themselves.
        # Numeric support is checked against the linked literal original below.
        for token in compliance.UNIT_PATTERN.finditer(body['text']):
            matches=[f['id'] for f in facts if _normalize(token.group()) in _normalize(f['quote'])]
            if len(matches)==1 and matches[0] not in declared|visible:
                declared.add(matches[0]);repairs.append('按本型号原文唯一数字匹配补充引用：'+token.group())
        for fid in sorted(declared-known.keys()):repairs.append('未知编号未修复：'+fid)
        for fid in sorted((declared & known.keys())-visible):body['text']+=' ['+fid+']'
        body['fact_ids']=sorted(declared|visible)
    rep.run['citation_format_repairs']=repairs
    tags=[]
    for tag in rep.article.get('tags',[]):
        tags.extend(re.sub(r'\s+','',v) for v in re.findall(r'#[^#]+',tag)) if tag.count('#')>1 else tags.append(tag)
    rep.article['tags']=tags
    text=_article_text(rep.article);used=set(FACT_MARK.findall(text))
    citations=bool(used) and used<=known.keys()
    for body in rep.article.get('body',[]):
        visible=set(FACT_MARK.findall(body['text']))
        if visible!=set(body.get('fact_ids',[])):citations=False
    rep.used_facts=[f for f in facts if f['id'] in used]
    rep.checks.append(_check('原文引用',citations,'正文可见编号与本型号资料一致' if citations else '存在缺失、未知或与段落不一致的引用编号'))
    hits=assertion_hits(text)
    # Comparisons often span comma-separated clauses; inspect the whole sentence.
    for sentence in re.split(r'[。！？!?；;\n]',text):
        if re.search(r'(?:相比|比)(?:传统|普通|常见|同类|上一?代|其他).{0,100}(?:更大|更多|更少|减少|提升|更快|更强|更友好)',sentence):
            hits.append(compliance.Hit('无依据对比','跨分句产品对比','rewrite','未提供同条件比较证据，请删除对比结论',sentence))
    for segment in [rep.article.get(k,'') for k in ('title','lead','cta')]+[b['text'] for b in rep.article.get('body',[])]:
        ids=FACT_MARK.findall(segment)
        blob='\n'.join(known[i]['quote'] for i in ids if i in known)
        for instruction in ('完整保留本条原文','不合并不同配置','只陈述这一原文参数','不据此承诺视觉效果'):
            if instruction in segment:
                hits.append(compliance.Hit('提示词泄漏',instruction,'rewrite','这是内部写作约束，不是给读者看的文案，请删掉指令文字但保留真实参数及来源脚注',segment))
        for claim in ('减少滚动次数','提升阅读效率','减轻肩背压力'):
            if claim in segment and claim not in blob:
                hits.append(compliance.Hit('无依据效果',claim,'rewrite','原文参数不能证明该体验效果，请改为到店核对的建议',segment))
        for match in re.finditer(r'减少(?:频繁)?(?:翻页|滚动|滑动)(?:的次数|次数)?|纵向.{0,8}(?:更充裕|更大|更多)|(?:同一页|一屏).{0,8}(?:看到|显示|容纳)更多|装下更多细节|不用频繁缩放|黄金平衡点|卡在.{0,16}平衡点|轻便到.{0,8}忘记|(?:既能|能)看清.{0,30}(?:图纸|图表|公式|表格)|(?:拎|背|拿).{0,8}(?:没那么吃力|毫不费力|很轻松)|(?:少些|减轻|减少).{0,6}(?:负担|压力)',segment):
            clause=re.split(r'[。！？!?；;]',segment[:match.start()])[-1]
            if re.search(r'希望|期待|愿望|是否|能否|不代表|不能证明|不保证',clause) and not re.search(r'它能|它让|这台能|这款能|该机能',clause):continue
            if match.group() not in blob:
                hits.append(compliance.Hit('无依据效果',match.group(),'rewrite','屏幕参数不构成阅读效果的实证，请删除这一推导',segment))
        for number in compliance.UNIT_PATTERN.finditer(segment):
            if _normalize(number.group()) not in _normalize(blob):
                hits.append(compliance.Hit('无依据数字',number.group(),'block','该段数字单位不在所引用的原文中',segment))
        for ratio in re.finditer(r'\d+(?:\.\d+)?\s*[:∶]\s*\d+(?:\.\d+)?',segment):
            if _normalize(ratio.group()).replace('∶',':') not in _normalize(blob).replace('∶',':'):
                hits.append(compliance.Hit('无依据数字',ratio.group(),'block','该比例不在所引用的原文中，不能从其他机型或常识补入',segment))
        for claim in ('累眼','上下黑边','阅读长文档更友好'):
            if claim in segment and claim not in blob:
                hits.append(compliance.Hit('无依据效果',claim,'rewrite','资料没有这一使用效果的依据，请删去体验推导',segment))
        if re.search(r'\d+\s*(kg|克|g)\b',segment,re.I) and '约' in blob and '约' not in segment:
            hits.append(compliance.Hit('限定条件','约','rewrite','重量原文含约，不能省略',segment))
        if ('sRGB' in segment or 'NTSC' in segment or 'nits' in segment) and '典型值' in blob and '典型值' not in segment:
            hits.append(compliance.Hit('限定条件','典型值','rewrite','需保留典型值',segment))
        if re.search(r'Windows',blob,re.I) and '仅限 Windows' in blob and any(w in segment for w in ('华为分享','高能模式','电脑管家','一键还原')) and 'Windows' not in segment:
            hits.append(compliance.Hit('系统范围','Windows','rewrite','应用功能须保留 Windows 适用范围',segment))
    hits=compliance._dedupe(hits)
    rep.rewrite_hits=[vars(h) for h in hits]
    rep.checks.append(_check('事实与营销检查',not hits,'数字逐段对照原文，未命中当前风险规则' if not hits else '；'.join(h.word+'：'+h.reason for h in hits)))
    n=len(re.sub(r'\s','',FACT_MARK.sub('',text)));body=rep.article.get('body',[])
    issues=[]
    if n<policy['min_chars'] or n>policy['max_chars']:issues.append(f"当前{n}字，要求{policy['min_chars']}–{policy['max_chars']}字")
    if len(body)<policy['paragraphs']:issues.append(f"需至少{policy['paragraphs']}段，当前{len(body)}段")
    if not rep.article.get('cta'):issues.append('缺少行动引导')
    if channel in ('xhs','wechat','poster') and not rep.article.get('title'):issues.append('缺少标题')
    if policy.get('tags',channel=='xhs') and not 4<=len(tags)<=6:issues.append('需4–6个话题标签')
    if not policy.get('tags',channel=='xhs') and tags:issues.append('当前设置不使用话题标签')
    if policy.get('max_paragraphs') and len(body)>policy['max_paragraphs']:issues.append(f"用户要求{policy['max_paragraphs']}段，当前{len(body)}段")
    if channel=='moments' and len(rep.strategy.get('selected_points',[]))!=1:issues.append('朋友圈保持一个核心主题')
    if channel=='poster' and len(body)>3:issues.append('海报最多3个短卖点')
    rep.checks.append(_check('渠道结构与篇幅',not issues,'；'.join(issues) if issues else f"{policy['label']} · {n}字 · {len(body)}段"))
    preferences=request_issues(rep.article,policy,text)
    rep.checks.append(_check('用户内容要求',not preferences,'；'.join(preferences) if preferences else '已检查指定标题、关键词、表情和内容格式要求'))
    goal_issues=[]
    if goal in GOALS:
        cta=rep.article.get('cta','')
        actions={'enterprise':r'需求|岗位|软件|采购|咨询','awareness':r'收藏|留言|评论|了解|关注|分享|告诉|聊|说说|互动|探讨|交流','store':r'到店|进店|门店|来店|莅临|店内|店里|线下','decision':r'核对|需求|选择|配置|清单|选购'}
        if not re.search(actions[goal],cta):goal_issues.append('行动引导未体现所选营销目标：'+GOALS[goal]['label'])
        if goal in ('awareness','decision','enterprise') and re.search(r'欢迎.{0,6}(?:到店|进店)|(?:快来|来|请|邀请|建议).{0,4}(?:到店|进店)|到店(?:体验|咨询|看看|了解)',cta):
            goal_issues.append('当前目标不应以邀请到店收尾，请按所选目标设置行动引导')
        if goal=='awareness' and not policy.get('requested_title') and re.search(r'别急着下单|先别急(?:着)?(?:下单|买|选|入手)|先问自己|避坑指南|选购指南|购机指南|几点.{0,4}有数',rep.article.get('title','')):
            goal_issues.append('种草了解需要场景与兴趣标题；当前仍是劝购/避坑清单标题，请围绕一个日常画面重新组织，而不是把选购指南换成口语')
        rep.checks.append(_check('营销目标与行动引导',not goal_issues,'；'.join(goal_issues) if goal_issues else GOALS[goal]['label']+' · 行动引导一致'))
    expected=policy.get('requested_images',policy['min_images'])
    enough=len(rep.images)>=expected
    rep.image_shortage='' if enough else f"本次期望{expected}张，仅有{len(rep.images)}张本型号可用图；未借用其他产品素材。"
    rep.checks.append(_check('型号配图',enough,rep.image_shortage or f'{len(rep.images)}张已核画面且原件指纹一致'))
    if not citations or hits or issues or goal_issues or preferences:
        rep.status='blocked' if any(h.action=='block' for h in hits) else 'failed'
        rep.message='本次草稿未通过核验，未展示为可用稿；具体问题见核验结果。'
    else:
        rep.status='restricted' if not enough or rep.run['source_level']=='discovery' or rep.mode=='test' else 'qualified'
        rep.message='正文已完成。'+(rep.image_shortage or '')
        if rep.run['source_level']=='discovery':rep.message+='该产品目前只有发现卡，定位介绍可用，完整规格仍需核对。'

def remove_risky_body_sentences(output,hits):
    """Delete unsupported body sentences, never invent replacement prose or facts.

    This editorial pass is followed by the same complete validation. If removing
    claims leaves too little text or too few paragraphs, the result still fails.
    """
    cleaned=copy.deepcopy(output);removed=[];body=[]
    for block in cleaned.get('article',{}).get('body',[]):
        if isinstance(block,str):block={'text':block,'fact_ids':sorted(set(FACT_MARK.findall(block)))}
        pieces=re.findall(r'[^。！？!?；;\n]+[。！？!?；;\n]*',block['text'])
        kept=[]
        for piece in pieces:
            reasons=[]
            for hit in hits:
                word=hit.get('word','');sentence=hit.get('sentence','')
                if (word and word in piece) or (sentence and sentence.strip() in piece):
                    reasons.append(hit['category']+'：'+word)
            if reasons:removed.append({'text':piece,'reasons':reasons})
            else:kept.append(piece)
        text=''.join(kept).strip()
        if re.sub(r'[\s。！？!?；;]','',FACT_MARK.sub('',text)):
            # Rebuild declarations from the surviving visible source links.
            body.append({**block,'text':text,'fact_ids':sorted(set(FACT_MARK.findall(text)))})
    cleaned.setdefault('article',{})['body']=body
    return cleaned,removed

def review_expression(client,rep,facts,channel,goal,*,revise=True):
    """A real model review supplements source/number rules; never overrides failure."""
    text=_article_text(rep.article)
    claims=[]
    attribution=r'HUAWEI|MateBook|本机|该机|这台|这款|这块|这种(?:屏幕|比例|尺寸|重量|设计|配置)|它(?:能|让|会|的|可以|采用|搭载|支持|提供|带来)'
    for sentence in re.split(r'(?<=[。！？!?；;])|\n',text):
        attributed=bool(re.search(attribution,sentence,re.I) or compliance.UNIT_PATTERN.search(sentence))
        advice=bool(re.search(r'建议|不妨|请|欢迎|携带.{0,12}(?:清单|课表)|不同.{0,12}软件.{0,12}(?:要求|环境)|(?:屏幕大小|屏幕尺寸|重量).{0,8}(?:影响|关注|考虑)|希望|期待|愿望',sentence))
        if sentence.strip() and (attributed or not advice):claims.append(sentence)
    instruction='''[EDITOR_REVIEW] 只检查本稿的实质性问题：本型号不获原文支持的具体功能、效果/对比承诺、兼容性结论、虚构体验或违背用户明确要求。数字与格式由程序另查，不因审美偏好要求重写。
区分产品已实现的效果与读者的生活背景、期待和选购建议。允许“屏幕大小影响查看体验”“把重量作为参考并结合自身接受程度判断”“可以到店体验手感”等背景常识与建议；不能仅因原文没有证明这些常识而报错。不推测隐藏暗示，不把整个包含审慎建议的段落当成承诺。
应报告的例子：“这台电脑让人背着不累”“此屏幕让你更专注”“该机适配所有专业软件”，须有本次产品原文支持。生活画面可以自然、有趣，不能伪造个人实测。
quote只逐字摘录最小的具体错误断言，reason说明哪个本型号结论无依据或哪条用户要求未执行。没有实质性问题则issues为空。
只输出严格JSON：{"issues":[{"quote":"原稿中的具体错误断言","reason":"具体理由"}]}。不编造引用句，不补写产品事实。'''
    policy=rep.run.get('content_policy') or content_policy(channel,rep.run.get('input',{}).get('detail_level','标准'))
    instruction+='\n用户明确的标题、内容重点、语气、表情/标签设置和修订要求优先于渠道的默认写法。审稿和实际编辑必须保留这些要求，不擅自改回通用模板。只审查当前稿件，用户需求中的禁用示例不是稿件事实。'
    instruction+='\n本次只审 product_claims 列出的产品断言。copy仅用于理解上下文，不能把其余生活背景或普通咨询建议扩张成新问题。“不同软件的环境要求不同”“携带清单到店核对”属于正常选购建议；不要求知识库为日常建议提供实测证明。用户具体格式要求另由程序严格校验。'
    instruction+='\nsource_facts已由程序按当前product_name绑定产品原件并核对文件指纹；product_name、source_title、section及source_sha256提供归属信息，quote保留原文。结合这些来源字段判断参数归属，不要求每条参数原文再次重复型号名称。若来源存在实际冲突或不能支持稿件结论，仍应报告。'
    instruction+='\n产品事实以本次source_facts为依据，禁止用模型记忆、旧版本印象或“通常搭载”否定当前原件；若认定资料之间冲突，必须指出本次所给来源中的具体冲突，不得凭空猜测。编辑不得把原文的系统、型号、版本或参数换成你记忆中的值。无法确认的事实只能提示待确认，不能自行修正为可用事实。'
    if revise:
        instruction+='\n若issues非空，必须同时返回revised_article完整对象（不能为null）：按原article的title/lead/body（text与fact_ids对象数组）/cta/tags结构实际编辑，不是仅列建议。删除无依据效果或改成条件化的核对建议，不用同义词继续暗示效果。保留用户指定标题、重点、格式和引用，总字数必须落在本次范围内。不要添加新事实或免费服务。issues为空时revised_article可为null。'
    source_facts=[{k:f[k] for k in ('id','category','quote','product_name','source_title','source_file','source_url','source_sha256','section') if k in f} for f in facts]
    result=client.chat_json([{'role':'system','content':instruction},{'role':'user','content':json.dumps({'product_name':rep.product_name,'channel':CHANNELS[channel]['label'],'goal':GOALS[goal]['label'],'channel_rules':writing_brief(channel,goal),'user_brief':rep.run.get('input',{}),'resolved_settings':policy,'length_min':policy['min_chars'],'length_max':policy['max_chars'],'body_min':policy['paragraphs'],'source_facts':source_facts,'product_claims':claims,'article':rep.article,'copy':text},ensure_ascii=False)}],max_tokens=6500 if revise and channel=='wechat' else 4000 if revise else 1800,temperature=0.1)
    rep.run.setdefault('expression_review_responses',[]).append(copy.deepcopy(result))
    if not isinstance(result,dict) or not isinstance(result.get('issues'),list):
        raise ConnectorError('表达复核未返回有效问题清单，未放行稿件。',kind='invalid_model_json')
    issues=result['issues']
    if any(not isinstance(i,dict) or not isinstance(i.get('quote'),str) or not i['quote'].strip() or i['quote'] not in text or not isinstance(i.get('reason'),str) or not i['reason'].strip() for i in issues):
        raise ConnectorError('表达复核未能定位原稿句子，未放行稿件。',kind='invalid_model_json')
    outside=[i for i in issues if not any(i['quote'] in claim for claim in claims)]
    if outside:rep.run.setdefault('out_of_scope_review_notes',[]).extend(outside)
    issues=[i for i in issues if i not in outside]
    completion=getattr(client,'last_completion',None)
    rep.run.setdefault('expression_reviews',[]).append({'issues':issues,'request_id':getattr(completion,'request_id',None),'raw_output':getattr(completion,'text',None)})
    rep.run['model_stats']=dict(getattr(client,'stats',{}))
    rep.checks.append(_check('表达与证据复核',not issues,'模型逐句复核未发现具体无依据效果或目标偏离，发布前仍需人工复核' if not issues else '；'.join(i['quote']+'：'+i['reason'] for i in issues)))
    if issues:
        rep.status='failed';rep.message='表达复核发现缺乏依据的表述，未展示为可用稿。'
        rep.rewrite_hits.extend({'category':'表达与证据','word':i['quote'],'sentence':i['quote'],'action':'rewrite','reason':i['reason']} for i in issues)
    return result.get('revised_article') if issues and revise else None


def compose(rep,system,prompt,facts,policy,channel,goal,model_client,on_progress):
    """Write once, repair rules once, then review once and audit edits once."""
    try:client=BudgetedModel(model_client or ModelScopeClient(),rep.run,
                            on_wait=lambda message:on_progress(2,message) if on_progress else None)
    except ConnectorError as error:
        rep.status='failed';rep.message=str(error);rep.run['failure_kind']=error.kind
        rep.checks=[_check('模型配置',False,rep.message)];return
    def event(message):
        if on_progress:on_progress(3,message)
    def validate(output):
        rep.checks=[];rep.rewrite_hits=[]
        _evaluate(rep,output,facts,policy,channel)
        if channel in ('wechat','xhs') and rep.rewrite_hits:
            cleaned,removed=remove_risky_body_sentences(output,rep.rewrite_hits)
            if removed:
                rep.run.setdefault('editorial_removals',[]).append({'removed':removed})
                rep.checks=[];rep.rewrite_hits=[];_evaluate(rep,cleaned,facts,policy,channel)
        return rep.status in ('qualified','restricted')
    def write(messages,purpose):
        client.purpose=purpose
        if on_progress:on_progress(2,f'{purpose} · 本次最多4次模型调用')
        rep.run['prompt_messages']=messages
        output=client.chat_json(messages,max_tokens=6000 if channel=='wechat' else 4000 if channel=='xhs' else 1800,temperature=.55 if channel=='xhs' else .35)
        completion=getattr(client,'last_completion',None)
        if completion:rep.run.update(model_raw_output=completion.text,usage=completion.usage,model_request_id=completion.request_id)
        return output
    try:
        try:
            output=write([{'role':'system','content':system},{'role':'user','content':prompt}],'生成初稿')
            event('初稿已返回，正在检查引用、数字、用户要求和渠道格式')
            good=validate(output)
        except ConnectorError as error:
            if error.kind!='invalid_model_json':raise
            output=None;good=False
            rep.checks=[_check('模型结构',False,'输出不是合法JSON，允许一次定向修复')]
        if not good:
            rep.run['first_attempt']={'article':copy.deepcopy(rep.article),'checks':copy.deepcopy(rep.checks),'status':rep.status}
            repair=prompt+'\n上一轮待修订输出（真实原稿，只修正下列问题；所有数字按本次FACT_POOL重新绑定引用编号）：'+json.dumps(output,ensure_ascii=False)
            repair+='\n本次唯一一次定向修订，请逐条执行用户修改与设置，并同时解决：'+json.dumps([c for c in rep.checks if not c.get('ok')],ensure_ascii=False)
            repair+='\n具体问题：'+json.dumps(rep.rewrite_hits,ensure_ascii=False)
            current_chars=len(re.sub(r'\s','',FACT_MARK.sub('',_article_text(rep.article))))
            if current_chars>policy['max_chars']:
                repair+=f"\n字数由程序实际计数为{current_chars}，超出上限{policy['max_chars']}。请至少删去{current_chars-policy['max_chars']+max(15,round(policy['max_chars']*.15))}字，合并场景铺垫与重复邀请，保留参数、限定和引用，不要只改一两个词。"
            repair+='\n无依据效果整句删除，不用同义词继续暗示。保留其他有依据内容，补充篇幅只写读者情境与审慎建议。body保持text和fact_ids对象数组。只输出完整JSON。'
            output=write([{'role':'system','content':system},{'role':'user','content':repair}],'定向修订（仅一次）')
            good=validate(output)
            rep.run['repair_attempts']=[{'status':rep.status,'checks':copy.deepcopy(rep.checks)}]
        if good:
            event('规则检查通过，正在复核表达和用户要求')
            client.purpose='表达与需求复核'
            revised=review_expression(client,rep,facts,channel,goal)
            if isinstance(revised,dict):
                rep.run.setdefault('expression_edits',[]).append(copy.deepcopy(revised))
                # A critic may edit copy but cannot bypass numeric or request checks.
                if validate({**output,'article':revised}):
                    event('表达已编辑，正在进行最后一次复核')
                    client.purpose='编辑后最终复核'
                    review_expression(client,rep,facts,channel,goal,revise=False)
    except ConnectorError as error:
        rep.status='failed';rep.run['failure_kind']=error.kind
        rep.run['model_error']={'message':str(error),'http_status':error.code,'provider_code':error.provider_code,'stage':client.purpose}
        guidance={
            'token_rate_limit':'模型服务的 Token 吞吐额度暂时受限，本次已停止。请稍后重试；若持续出现，请检查当前模型的限流和可用额度。',
            'rate_limit':'模型服务请求过于频繁，本次已停止。请稍后重试，避免连续提交。',
            'quota':'模型服务的可用额度或账户预算已耗尽，本次已停止。请检查服务平台的额度、预算或账户状态，恢复后再生成。',
        }
        rep.message=guidance.get(error.kind,'本次已停止：'+str(error))
        if error.kind in guidance:
            rep.message+=' 本地 v7 资料缓存只提供原文和图片，写作与复核仍需调用在线模型。'
            rep.message+=' 停止阶段：'+client.purpose+'。'
        rep.checks.append(_check('模型调用',False,rep.message))
    finally:
        rep.run['model']=client.model;rep.run['model_stats']=dict(getattr(client,'stats',{}))
    if rep.status not in ('qualified','restricted') and not rep.run.get('failure_kind'):
        reasons=[c['detail'] for c in rep.checks if not c.get('ok')]
        rep.message='自动修订已停止，本次未作为可用稿展示。'+('主要问题：'+reasons[0] if reasons else '请查看核验结果。')


def run_task(*,on_progress=None,**kwargs):
    """Emit milestones only when execution actually reaches them; no timed progress."""
    stages=[]
    def emit(stage,detail,state='active'):
        event={'stage':stage,'detail':detail,'state':state,'at':datetime.now().astimezone().isoformat()}
        stages.append(event)
        if on_progress:on_progress(event)
    emit(0,'正在检查型号、渠道和场景')
    rep=_run_task(on_progress=emit,**kwargs)
    emit(3 if rep.status in ('qualified','restricted') else -1,rep.message,rep.status)
    rep.run['stages']=stages
    return rep

def _run_task(*,product='',audience='',scene='',platform='',free_text='',variant='',os_name='',extra_request='',mode='cache',
             previous_article=None,image_count=None,detail_level='详细',marketing_goal='awareness',model_client=None,on_progress=None):
    rep=Report(mode=mode,mode_note=cache_mode_note() if mode!='live' else '实时模式：本次从 ima 读取所选产品原件，失败即停止，不自动切换。')
    rep.run={'started_at':datetime.now().astimezone().isoformat(),'input':dict(product=product,audience=audience,scene=scene,
             platform=platform,marketing_goal=marketing_goal,free_text=free_text,variant=variant,os_name=os_name,extra_request=extra_request,image_count=image_count,detail_level=detail_level),
             'revision_context_used':bool(previous_article),'stages':[]}
    if mode not in ('cache','live','test'):
        rep.message='未知运行模式';return rep
    item=catalog.find_product(product);channel=channel_key(platform);goal=goal_key(marketing_goal)
    scene_name=SCENES.get(scene,scene)
    if not item:rep.questions.append('请从产品目录选择具体型号，不会自动猜型号。')
    if not channel:rep.questions.append('请选择公众号、小红书、门店朋友圈或门店海报。')
    if not goal:rep.questions.append('请选择营销目标：企业咨询、种草了解、到店咨询或选购决策。')
    if not scene_name:rep.questions.append('请说明使用场景。')
    if rep.questions:
        rep.status='need_info';rep.message='先补齐任务信息再生成。';return rep
    if on_progress:on_progress(1,'任务范围已确认，正在读取并核对原文与图片')
    rep.product_name=item['name'];rep.run['source_level']=item['level']
    try:policy=content_policy(channel,detail_level,free_text,extra_request)
    except ValueError as error:
        rep.status='need_info';rep.message=str(error);rep.questions.append(str(error));return rep
    if image_count is not None:policy['requested_images']=min(policy['max_images'],max(1,int(image_count)))
    rep.run['content_policy']=policy
    rep.run['marketing_goal']=goal
    rep.blocked_requests=[vars(h) for h in assertion_hits('\n'.join((free_text,extra_request))) if free_text or extra_request]
    try:
        facts=writing_facts(catalog.facts_for(item,variant,os_name),channel,'\n'.join((free_text,extra_request)),goal)
        rep.images=_select_images(item,channel,image_count)
        reader=_source_reader(item,rep.images,mode)
        if reader:
            reader.read(item['source'],item['sha256'])
        for image in rep.images:
            if reader:raw=reader.read(image['file'],image['sha256']).data
            else:
                raw,digest=catalog.read_verified(image['file'])
                if digest!=image['sha256']:raise ConnectorError('图片与核画面时的指纹不一致',kind='source_changed')
            rep.image_payloads[image['id']]=raw
        rep.run['source_stats']=dict(reader.stats) if reader else {'api_requests':0,'media_info_requests':0,'cache_hits':1+len(rep.images)}
    except ConnectorError as error:
        rep.message='资料读取失败：'+str(error);rep.run['failure_kind']=error.kind;return rep
    if not facts:
        rep.status='need_info';rep.message='你限定的主题暂无可引用原文，尚未调用写作模型。请调整重点或补充资料。';rep.questions.append(rep.message);return rep
    system=(catalog.ROOT/'prompts/system_prompt_v2.md').read_text(encoding='utf-8')
    system+='\n本次写作任务：'+writing_brief(channel,goal)
    system+=f'\nJSON 的 body 数组必须至少有 {policy["paragraphs"]} 个独立元素，每个元素对应一段；不要把整篇文章塞进一个 text。'
    system+=f"\n本次篇幅硬约束：{policy['min_chars']}–{policy['max_chars']}字（不含图片图注和来源），不要只写参数。"
    target=f"{policy['min_chars']}–{policy['max_chars']}"
    system+=f'\n建议写到{target}字，标题、导语、正文、CTA和标签都计入总字数；避免逼近上限。FACT_POOL 的 caveat 是写作规则，不能原样抄进正文；只保留真实的参数条件和产品原文脚注。屏幕比例不得推导减少滚动、效率提升，不写任何无依据体验效果。'
    system+='\n标题、导语、CTA 不写具体数字参数，数字只放在有 fact_ids 的正文。不要讨论“保证、完美、最适合”等词，直接删掉这些措辞。不要把场景建议写成产品实测结论。'
    if channel=='moments':system+='本次只有一个核心主题、一个已检索事实，selected_points 必须恰好1项，不要输出多个主题。'
    if channel=='xhs':system+='小红书采用4–5段，每段约70–110字；导语不超过60字，CTA不超过45字。只展开1–3个主题，不把所有检索参数都写进正文，不重复正文已有的限定条件。'
    if channel=='poster':system+='海报不是文章：body最多3个短行，每行只写一个事实；不要展开故事，不列长解释。'
    system+='\n以下本次设置和用户明确要求优先于上文渠道默认篇幅、段数、选题与语气；事实来源、所选产品和营销目标仍须遵守。逐项执行用户要求，不要用通用模板覆盖。\n本次有效设置：'+json.dumps(policy,ensure_ascii=False)
    system+='\n如用户要求不使用表情/话题标签，标题、导语、正文、CTA和tags都须同步遵守。用户指定标题须逐字采用。针对上一稿的修改必须实际编辑原稿；保留未要求修改且有依据的部分，不重新套另一篇模板。'
    system+=f"\n本次每段建议字数约{max(20,int((policy['min_chars']+policy['max_chars'])/2/max(policy['paragraphs'],1))-35)}；正文数组最少{policy['paragraphs']}段。最终总字数必须在{target}之间。"
    target_chars=round((policy['min_chars']+policy['max_chars'])/2)
    title_budget=len(policy.get('requested_title','')) or 16
    lead_budget=12 if target_chars<200 else 35
    cta_budget=22 if target_chars<200 else 40
    body_budget=max(20,target_chars-title_budget-lead_budget-cta_budget-(35 if policy.get('tags') else 0))
    system+=f'\n控制篇幅的字段预算：标题约{title_budget}字；lead可留空，最多{lead_budget}字；body所有段落合计约{body_budget}字；cta最多{cta_budget}字。不要在正文末尾重复CTA。以上总数包含标题、导语、正文、CTA及标签，引用编号不计数。'
    # All real product conditions already live in value. Keep editorial
    # instructions in the system message, away from the quotable fact data.
    pool=[{k:f[k] for k in ('id','category','value')} for f in facts]
    prompt=f'''产品：{item['name']}\n资料级别：{item['level']}\n版本：{variant or '按原文区分，不混合配置'}\n系统：{os_name or '按原文区分'}
受众：{audience or '根据场景推断，并列为假设'}\n场景：{scene_name}\n平台：{policy['label']}\n营销目标（用户已选，不可变更）：{GOALS[goal]['label']}\n详略：{detail_level}
用户说明：{free_text}\n修改要求：{extra_request}
场景策略：{scene_brief(scene_name,goal)}
FACT_POOL（所有事实只从这里来，条件脚注必须保留）：\n{json.dumps(pool,ensure_ascii=False)}
图片由程序按本型号实际原图插入，不需要你编造或输出图片。当前原图{len(rep.images)}张。
叙事要求：{GOALS[goal]['instruction']}
先理解场景，按所选目标组织开头、展开和收束。不要照抄现成软文，不要为了篇幅补编事实。
必须达到本次渠道篇幅要求：{policy['min_chars']}–{policy['max_chars']}字。只遵守本次渠道，不套用其他渠道篇幅。
每个带产品事实的 body 段落，在 text 中使用 [K001] 这样的可见引用，fact_ids 列出相同编号。选购提醒若含数字也必须引用。
只输出严格JSON。'''
    if previous_article:
        prompt+='\n上一稿（仅供编辑；旧标题、旧字数和旧引用编号都不能覆盖本轮要求）：'+json.dumps(previous_article,ensure_ascii=False)
        prompt+='\n本轮最终修订指令（覆盖之前说明中的同类要求）：'+extra_request
        prompt+=f"\n再次确认：最终总字数是{target}字；这是对原稿的实际编辑，不保留旧稿字数或旧选题。"
    compose(rep,system,prompt,facts,policy,channel,goal,model_client,on_progress)
    for index,image in enumerate(rep.images):
        image['position']='导语后' if index==0 else f"第{min(len(rep.article.get('body',[])),index)}段后" if rep.article.get('body') else '标题后'
        image['caption']=image['actual_view']
    rep.run['finished_at']=datetime.now().astimezone().isoformat()
    rep.notes_for_review.append('已取消签字门槛；程序核对来源、指纹、数字和渠道规则，生成后仍可人工编辑与复核。')
    return rep
