"""Resolve user settings once for writing, editing and deterministic checks."""
import re
from .channels import CHANNELS

RANGES={
 'wechat':{'标准':(700,1050,5),'详细':(1050,1700,5)},
 'xhs':{'标准':(350,550,4),'详细':(550,850,4)},
 'moments':{'标准':(90,160,1),'详细':(160,260,1)},
 'poster':{'标准':(35,110,1),'详细':(70,200,1)},
}
EMOJI=re.compile('[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]')


def content_policy(channel,level,description='',revision=''):
    policy=dict(CHANNELS[channel]);low,high,paragraphs=RANGES[channel].get(level,RANGES[channel]['标准'])
    policy.update(min_chars=low,max_chars=high,paragraphs=paragraphs,tags=channel=='xhs')
    # Later revision requests supersede the earlier brief's length/format.
    text=description+'\n'+revision
    spans=list(re.finditer(r'(\d{2,4})\s*[—–~～至到-]\s*(\d{2,4})\s*字',text))
    singles=list(re.finditer(r'(?:控制在|写成|缩短到|扩写到|约|大约|写|到|在)?\s*(\d{2,4})\s*字(?:左右|以内|上下)?',text))
    spans=[m for m in spans if int(m[1])<=int(m[2])]
    singles=[m for m in singles if not any(s.start()<=m.start()<s.end() for s in spans)]
    def tolerance(m):return max(10,round(int(m[1])*(.2 if re.search(r'左右|上下|约',m[0]) else .12)))
    matches=sorted([(m.start(),int(m[1]),int(m[2])) for m in spans]+[(m.start(),20 if '以内' in m[0] else max(20,int(m[1])-tolerance(m)),int(m[1]) if '以内' in m[0] else int(m[1])+tolerance(m)) for m in singles])
    if matches:
        _,low,high=matches[-1]
        if high>CHANNELS[channel]['max_chars']:raise ValueError(f"所选渠道最多{CHANNELS[channel]['max_chars']}字，请缩短字数要求或更换渠道。")
        policy.update(min_chars=low,max_chars=high,explicit_length=True)
        if high<350:policy['paragraphs']=min(policy['paragraphs'],2)
    counts=list(re.finditer(r'(?:只保留|分成|写成|保留|分为|写|用)\s*([一二两三四五六七八九十\d]+)\s*段',text))
    if counts:
        value=counts[-1][1];number=int(value) if value.isdigit() else {'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}.get(value,0)
        if not 1<=number<=10 or (channel=='poster' and number>3):raise ValueError('段落要求超出当前渠道可用范围。')
        policy.update(paragraphs=number,max_paragraphs=number)
    def latest_flag(default,no,yes):
        events=[(m.end(),0,True) for m in re.finditer(yes,text,re.I)]+[(m.end(),1,False) for m in re.finditer(no,text,re.I)]
        return sorted(events)[-1][2] if events else default
    policy['no_emoji']=not latest_flag(True,r'(?:不要|不加|不用|去掉|删除|不使用).{0,5}(?:emoji|表情|颜文字)',r'(?:加上|添加|加入|允许|使用|保留).{0,4}(?:emoji|表情|颜文字)')
    policy['tags']=latest_flag(policy['tags'],r'(?:不要|不加|不用|去掉|删除).{0,4}(?:话题标签|标签|话题)',r'(?:加上|添加|加入|使用|保留).{0,4}(?:话题标签|标签|话题)')
    title=list(re.finditer(r'标题(?:请)?(?:改成|改为|设为|用|是)\s*[“「\"]([^”」\"\n]+)[”」\"]',text))
    if title:policy['requested_title']=title[-1][1]
    phrases={};events=[]
    for kind,pattern in [('required',r'(?:必须包含|必须出现|一定要有|加入这句话)\s*[“「\"]([^”」\"\n]+)[”」\"]'),('forbidden',r'(?:不要出现|不提|删除|不要写)\s*[“「\"]([^”」\"\n]+)[”」\"]')]:
        events.extend((m.start(),kind,m[1]) for m in re.finditer(pattern,text))
    for _,kind,phrase in sorted(events):phrases[phrase]=kind
    policy['required_phrases']=[s for s,k in phrases.items() if k=='required']
    policy['forbidden_phrases']=[s for s,k in phrases.items() if k=='forbidden']
    return policy


def request_issues(article,policy,text):
    issues=[]
    if policy.get('no_emoji') and EMOJI.search(text):issues.append('用户要求不使用表情符号')
    if policy.get('requested_title') and article.get('title')!=policy['requested_title']:issues.append('未采用用户指定的标题')
    issues.extend('缺少用户要求的文字：'+s for s in policy.get('required_phrases',[]) if s not in text)
    issues.extend('仍含用户要求删除的文字：'+s for s in policy.get('forbidden_phrases',[]) if s in text)
    return issues
