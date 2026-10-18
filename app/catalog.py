"""Full supplied v7 catalogue. Source cards and complete specifications remain distinct."""
from __future__ import annotations
import csv
import hashlib
import json
import os
import re
from functools import lru_cache
from pathlib import Path
from connectors import ConnectorError

ROOT = Path(__file__).resolve().parents[1]
KB_ROOT = Path(os.environ.get('APP_KB_DIR', ROOT/'华为PC全板块深度知识库_v7'))
REVIEW_FILE = Path(os.environ.get('APP_ASSET_REVIEW',ROOT/'data/private/asset-review-v2.json'))

def read_verified(relative: str) -> tuple[bytes,str]:
    path=(KB_ROOT/relative).resolve()
    if not path.is_relative_to(KB_ROOT.resolve()):
        raise ConnectorError('资料路径越界。',kind='source_changed')
    try:
        raw=path.read_bytes()
    except OSError:
        raise ConnectorError('本地资料缺失：'+relative,kind='cache_missing') from None
    digest=hashlib.sha256(raw).hexdigest()
    expected=manifest().get(relative)
    if not expected or digest!=expected:
        raise ConnectorError('资料与 v7 文件清单指纹不一致：'+relative,kind='source_changed')
    return raw,digest

@lru_cache(maxsize=1)
def manifest() -> dict:
    file=KB_ROOT/'全库文件清单_SHA256.csv'
    if not file.exists(): return {}
    with file.open(encoding='utf-8-sig',newline='') as f:
        return {r['相对路径']:r['SHA256'] for r in csv.DictReader(f)}

def urls(text):
    return list(dict.fromkeys(re.findall(r'https://[^\s<>）)]+',text)))

@lru_cache(maxsize=1)
def inventory() -> list[dict]:
    p1=KB_ROOT/'P1-产品参数库'
    rows=[];by_url={}
    for path in sorted(p1.rglob('产品事实.md')):
        relative=path.relative_to(KB_ROOT).as_posix()
        raw,sha=read_verified(relative);text=raw.decode('utf-8-sig')
        name=text.splitlines()[0].lstrip('# ').replace(' - 产品事实','').strip()
        links=urls(text)
        row={'id':'P'+hashlib.sha256(relative.encode()).hexdigest()[:10], 'name':name,
             'category':'鸿蒙电脑' if '鸿蒙电脑' in relative else 'Windows 笔记本',
             'source':relative,'sha256':sha,'url':links[0] if links else '',
             'level':'specification','folder':path.parent.relative_to(KB_ROOT).as_posix(),
             'aliases':[path.parent.name,name]}
        rows.append(row)
        if links: by_url[links[0].rstrip('/')]=row
    index=p1/'07-扩展产品目录/扩展产品索引.csv'
    if index.exists():
        for r in csv.DictReader(index.read_text(encoding='utf-8-sig').splitlines()):
            key=r['官方URL'].rstrip('/')
            if key in by_url and by_url[key]['level']=='specification':
                by_url[key]['aliases'].append(r['产品名称']);continue
            relative=r['本地条目'];raw,sha=read_verified(relative)
            row={'id':'P'+hashlib.sha256(relative.encode()).hexdigest()[:10],'name':r['产品名称'],
                 'category':r['目录'],'source':relative,'sha256':sha,'url':r['官方URL'],
                 'level':'discovery','folder':str(Path(relative).parent).replace('\\','/'),
                 'aliases':[r['产品名称']], 'summary':r['官网摘要']}
            rows.append(row)
    return rows

@lru_cache(maxsize=1)
def products() -> list[dict]:
    """Selectable PCs require a complete specification and same-model imagery."""
    return [p for p in inventory() if p['level']=='specification' and assets_for(p)]


def image_count(product: dict) -> int:
    return len({i['view_group'] for i in assets_for(product)})


def find_product(value: str) -> dict | None:
    value=(value or '').strip()
    exact=[p for p in products() if value==p['id'] or value==p['name'] or value in p['aliases']]
    if len(exact)==1:return exact[0]
    norm=lambda s:re.sub(r'[\s（()）_-]','',s).lower()
    matches=[p for p in products() if norm(value) in {norm(a) for a in p['aliases']}]
    return matches[0] if len(matches)==1 else None

def product_choices():
    def label(p):
        short=re.search(r'D\s+(14|16)',p['name'])
        alias=f" / D{short.group(1)}" if short else ''
        return f"{p['name']}{alias} · {image_count(p)} 张原图"
    return [(label(p),p['id']) for p in products()]

def _variant_block(content: str, variant: str) -> str:
    """D14's two screen/keyboard blocks are explicit; never blend them."""
    if 'HUAWEI MateBook D 14 2024 SE 版' not in content:return content
    chunks=re.split(r'(?=HUAWEI MateBook D 14 2024)',content)
    generic=[c for c in chunks if not c.startswith('HUAWEI MateBook D 14 2024')]
    selected=[c for c in chunks if c.startswith('HUAWEI MateBook D 14 2024') and
              (('SE 版' in c.splitlines()[0]) == (variant=='SE 版'))]
    footnotes=re.findall(r'(?m)^\*.*$',content)
    return '\n'.join(generic+selected+footnotes)

def facts_for(product: dict, variant='', system='') -> list[dict]:
    raw,sha=read_verified(product['source']);text=raw.decode('utf-8-sig')
    facts=[]
    if product['level']=='discovery':
        # The source itself calls these discovery summaries, not full SKU specifications.
        match=re.search(r'## 官网公开定位摘要\s*\n(.*?)(?=\n## |\Z)',text,re.S)
        block=match.group(1).strip() if match else product.get('summary','')
        facts.append({'id':'K001','category':'官方定位摘要','value':block,'quote':block,'quotes':[block],
                      'section':'官网公开定位摘要','must_keep':[], 'caveat':'定位摘要不替代完整规格，不作兼容、性能或服务保证。'})
    else:
        sections=re.split(r'^## ',text,flags=re.M)[1:]
        for section in sections:
            title,_,body=section.partition('\n');body=body.strip()
            if title.strip() in ('来源','官方规格摘录','包装清单') or not body:continue
            if title=='尺寸与重量':
                weight=re.search(r'重量\s*\n(.*)',body,re.S)
                if not weight:continue
                body=weight.group(1).strip() # Excludes known mislabeled dimension fields.
            if 'MateBook D 14' in product['name'] and variant in ('标准版','SE 版'):
                body=_variant_block(body,variant)
            if system=='Linux' and title in ('特色应用','处理器'):continue
            # Preserve whole source paragraphs with their original conditions.
            chunks=[body[i:i+2200] for i in range(0,len(body),2200)] if len(body)>2200 else [body]
            for block in chunks:
                if block not in text: # Filtering remains a set of literal source quotations.
                    quotes=[q.strip() for q in block.split('\n\n') if q.strip() and q.strip() in text]
                else:quotes=[block]
                if not quotes:continue
                facts.append({'id':f'K{len(facts)+1:03d}','category':title.strip(),'value':block,
                    'quote':'\n'.join(quotes),'quotes':quotes,'section':title.strip(),'must_keep':[],
                    'caveat':'完整保留本条原文中的版本、典型值、条件和脚注，不合并不同配置。'})
    for fact in facts:
        fact.update(source_title=product['name']+' / '+fact['section'],source_file=product['source'],
                    source_sha256=sha,source_url=product['url'],usage='body',product_name=product['name'],
                    verification='source_hash_and_literal_quote; no human signature required')
    return facts

def assets_for(product: dict) -> list[dict]:
    if not REVIEW_FILE.exists():return []
    reviewed=json.loads(REVIEW_FILE.read_text(encoding='utf-8')).get('images',[])
    return [i for i in reviewed if i['product_folder']==product['folder'] and i.get('usable')]

def describe(value: str) -> str:
    product=find_product(value)
    if not product:return '请选择知识库中的具体产品。'
    try:
        count=len(facts_for(product));images=image_count(product)
        level='完整规格档案' if product['level']=='specification' else '产品发现卡：可写定位介绍，精确 SKU 参数待复核'
        return f"**{product['name']}** · {level}\n\n可溯源事实章节 **{count}** · 本型号可用原图 **{images} 张**（同画面尺寸版本已合并） · 资料日期 **2026-10-17**\n\n图片按渠道上限插入，不足时用实际数量并提示，不借用其他型号。\n\n来源：{product['url']}"
    except ConnectorError as error:return str(error)
