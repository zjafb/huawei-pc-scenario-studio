"""Gradio 页面。明确选择缓存/实时；测试模式仅在环境变量 APP_TEST_MODE=1 时出现，
且页面顶部持续标红“测试”。页面不展示任何凭证。"""
from __future__ import annotations

import html
import os
import base64
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from queue import Queue
from threading import Thread

import gradio as gr
from PIL import Image

from . import full_pipeline as pl
from . import catalog
from .channels import CHANNELS,SCENES as ALL_SCENES
from run_records import save_run
from .studio import workflow, EMPTY_ARTICLE, studio_css, studio_js

TEST_MODE = os.environ.get("APP_TEST_MODE") == "1"

STATUS_STYLE = {
    "qualified": ("核验通过", "#477568"),
    "restricted": ("受限完成", "#86522D"),
    "need_info": ("需补充", "#477568"),
    "blocked": ("已拦截", "#99543E"),
    "failed": ("未通过", "#99543E"),
}

SCENES = list(ALL_SCENES.values())
PLATFORMS = [c['label'] for c in CHANNELS.values()]
VARIANTS = ["", "标准版", "SE 版"]
OSES = ["", "Windows", "Linux"]


def _banner(rep: pl.Report) -> str:
    label, color = STATUS_STYLE.get(rep.status, (rep.status, "#444"))
    mode = {"test": "测试（非真实运行结果）", "cache": "缓存", "live": "实时"}.get(rep.mode, "未知")
    parts = [f'<div class="result-banner" style="--status-color:{color}">'
             f'<strong>{label}</strong> · 模式：{mode}']
    if rep.mode_note:
        parts.append(f'<p>{html.escape(rep.mode_note)}</p>')
    if rep.image_shortage:
        parts.append(f'<p>⚠ {html.escape(rep.image_shortage)}</p>')
    if rep.message:
        parts.append(f'<div style="margin-top:6px">{html.escape(rep.message)}</div>')
    if rep.questions:
        qs = "".join(f"<li>{html.escape(q)}</li>" for q in rep.questions)
        parts.append(f"<ol>{qs}</ol>")
    if rep.status in ('failed','blocked'):
        failed=[c for c in rep.checks if not c.get('ok')]
        if failed:
            parts.append('<ul>'+''.join('<li>'+html.escape(c['name']+'：'+c['detail'])+'</li>' for c in failed[:4])+'</ul>')
    return "".join(parts)+'</div>'


def _section(rep: pl.Report, n: int) -> str:
    sj, a = rep.scene_judgement or {}, rep.article or {}
    if n == 1:
        if not sj:
            return "（本次未生成）"
        lines = [f"- 目标人群 / 使用场景：{sj.get('audience', '')} / {sj.get('scene', '')}",
                 f"- 用户问题：{'；'.join(sj.get('problems', []) or [])}",
                 f"- 内容目标 / 购买阶段：{sj.get('goal', '')} / {sj.get('purchase_stage', '')}"]
        st = rep.strategy or {}
        if st.get("angle"):
            lines.append(f"- 切入点：{st['angle']}")
        for p in st.get("selected_points", []) or []:
            lines.append(f"- 选用卖点：{p.get('category', '')}（依据 {', '.join(p.get('fact_ids', []))}）：{p.get('why', '')}")
        for p in st.get("dropped_points", []) or []:
            lines.append(f"- 舍弃：{p.get('category', '')}：{p.get('reason', '')}")
        for x in sj.get("assumptions", []) or []:
            lines.append(f"- 系统假设：{x}")
        return "\n".join(lines)
    if n == 2:
        if not rep.used_facts:
            return "（本次未使用可引用的原文事实）"
        rows = []
        for f in rep.used_facts:
            rows.append(f"- **[{f['id']}]** {f.get('product_name') or rep.product_name} ｜ {f.get('section', '')}")
            rows.append(f"  - 来源：{f.get('source_title', '')}；原文：" + "；".join(f.get('quotes') or [f.get('quote', '')]))
            rows.append(f"  - 原文 SHA-256：`{f.get('source_sha256', '')}`")
        return "\n".join(rows)
    if n == 3:
        if rep.status in ("failed", "blocked", "need_info"):
            return "（核验未通过或信息不全，本次不展示可发布正文；详见核验结果。）"
        if not a:
            return "（本次未生成）"
        out = []
        if a.get("title"):
            out.append(f"**标题**：{a['title']}")
        if a.get("lead"):
            out.append(f"**导语**：{a['lead']}")
        for b in a.get("body", []) or []:
            out.append(b.get("text", "") if isinstance(b, dict) else str(b))
        if a.get("cta"):
            out.append(f"**行动引导**：{a['cta']}")
        if a.get("tags"):
            out.append("**标签**：" + " ".join(a["tags"]))
        for i in rep.images:
            out.append(f"🖼 **{i['id']} · {i['name']}** ｜ 建议位置：{i.get('position', '')} ｜ 来源：{i.get('source_title', '')}"
                       f"\n\n画面：{i.get('caption', i.get('actual_view', ''))}；限制：{i.get('usage_limit', '')}")
        return "\n\n".join(out)
    lines = [f"- {'✅ 通过' if c['ok'] else '❌ 未通过'}｜**{c['name']}**：{c['detail']}" for c in rep.checks]
    for b in rep.blocked_requests:
        lines.append(f"- 🚫 已拦截用户要求（{b['category']}「{b['word']}」）：{b['reason']}")
    if rep.rewrite_hits:
        for h in rep.rewrite_hits:
            lines.append(f"- ✏️ 命中「{h['category']}」：{h['word']} —— {h['reason']}")
    if rep.pending:
        lines.append("- **待确认信息（未进入正文）**：")
        lines += [f"  - {p}" for p in rep.pending]
    for n_ in rep.notes_for_review:
        lines.append(f"- 提示：{n_}")
    return "\n".join(lines) or "（无）"


def rich_article(rep):
    if rep.status not in ('qualified','restricted'):
        return '<div class="article-empty">本次尚无通过核验的正文。请查看核验结果或补充需求。</div>'
    def esc(value):return html.escape(str(value or '')).replace('\n','<br>')
    def figure(info):
        raw=rep.image_payloads.get(info['id'])
        if not raw:return ''
        encoded=base64.b64encode(raw).decode('ascii')
        mime='image/png' if raw.startswith(b'\x89PNG') else 'image/webp' if raw[8:12]==b'WEBP' else 'image/jpeg'
        return f'<figure><img src="data:{mime};base64,{encoded}" alt="{esc(info.get("actual_view"))}"><figcaption>{esc(info.get("actual_view"))}<br>来源：{esc(info.get("source_title"))} · {esc(info.get("usage_limit"))}</figcaption></figure>'
    article=rep.article
    chunks=['<article class="story-card">',f'<p class="story-eyebrow">{esc(rep.product_name)}</p>',
            f'<h1>{esc(article.get("title"))}</h1>',f'<p class="story-lead">{esc(article.get("lead"))}</p>']
    if rep.images:chunks.append(figure(rep.images[0]))
    remaining=iter(rep.images[1:])
    for block in article.get('body',[]):
        chunks.append('<p class="story-paragraph">'+esc(block['text'])+'</p>')
        image=next(remaining,None)
        if image:chunks.append(figure(image))
    chunks += [figure(i) for i in remaining]
    chunks.append('<p class="story-cta">'+esc(article.get('cta'))+'</p>')
    chunks.append('<p class="story-tags">'+esc(' '.join(article.get('tags',[])))+'</p></article>')
    return ''.join(chunks)


def run_ui(product, audience, scene, platform, free_text, variant, os_name, extra, mode_choice="cache", previous=None,
           image_count=6,detail_level='详细',on_progress=None):
    mode = "test" if TEST_MODE else ({"缓存": "cache", "实时": "live"}.get(mode_choice, mode_choice))
    context_key = [product or "", variant or "", os_name or "", mode]
    old_article = previous.get("article") if extra and isinstance(previous, dict) and previous.get("key") == context_key else None
    try:
        rep = pl.run_task(product=product or "", audience=audience or "", scene=scene or "",
                          platform=platform or "", free_text=free_text or "", variant=variant or "",
                          os_name=os_name or "", extra_request=extra or "", mode=mode, previous_article=old_article,
                          image_count=image_count,detail_level=detail_level,**({'on_progress':on_progress} if on_progress else {}))
    except Exception as e:  # 页面不崩溃；错误如实显示，不产生假结果
        rep = pl.Report(status="failed", mode=mode, message=f"运行出错：{type(e).__name__}：{e}")
    gallery = []
    if rep.status in ("qualified", "restricted"):
        try:
            for info in rep.images:
                with Image.open(BytesIO(rep.image_payloads[info["id"]])) as original:
                    original.load()
                    gallery.append((original.copy(), f"{info['id']} · {info.get('caption', info['name'])}"))
        except (OSError, ValueError, KeyError):
            rep.status, rep.message = "failed", "原图无法解码展示，本次不能作为完整图文稿使用。"
            rep.checks.append({"name": "原图展示", "ok": False, "detail": rep.message})
            gallery = []
    try:
        path = save_run(rep)
        rep.run["record_id"] = path.stem
        rep.notes_for_review.append(f"运行记录：{path.stem}")
    except (OSError, ValueError, TypeError):
        rep.notes_for_review.append("运行记录保存失败，请保留本次导出文本。")
    export_text = pl.to_text(rep)
    export_file = None
    html_file = None
    try:
        export_dir = Path(__file__).resolve().parent.parent / "data" / "private" / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        destination = export_dir / f"result-{uuid4().hex}.txt"
        destination.write_text(export_text, encoding="utf-8-sig")
        export_file = str(destination)
        html_destination=export_dir/f'result-{uuid4().hex}.html'
        html_destination.write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>'+STORY_CSS+'</style><body>'
            +f'<p>{html.escape(rep.mode_note)} · 状态：{html.escape(rep.status)}</p>'+rich_article(rep)+'</body></html>',encoding='utf-8')
        html_file=str(html_destination)
    except OSError:
        rep.notes_for_review.append("下载文件写入失败，可以复制文本。")
    next_state = {"key": context_key, "article": rep.article} if rep.status in ("qualified", "restricted") else None
    if on_progress:on_progress({'stage':3 if rep.status in ('qualified','restricted') else -1,'state':rep.status,'detail':rep.message})
    return (_banner(rep), _section(rep, 1), _section(rep, 2), rich_article(rep), _section(rep, 4),
            export_text, gallery, export_file, next_state,html_file)


def reset_ui():
    """Changing task context invalidates displayed evidence, without an API call."""
    return ("<div style='padding:12px'>需求已变化，请重新生成并核验。</div>", "", "", "", "", "", [], None, None,None)


STORY_CSS='''
.story-card{max-width:850px;margin:0 auto;padding:12px 3px;background:#FFFEFB;color:#283D36;font-family:'Studio Sans','Noto Sans SC','Microsoft YaHei',sans-serif;line-height:2;overflow-wrap:anywhere}
.story-card h1{font-family:'Studio Serif','Noto Serif SC','Songti SC','SimSun',serif;font-weight:600;font-size:34px;line-height:1.65;margin:14px 0 24px;letter-spacing:.4px}.story-eyebrow{color:#99543E;font-size:13px;font-weight:600;letter-spacing:1px;padding-bottom:17px;border-bottom:1px solid #DEDFD3}
.story-lead{font-size:17px;color:#52644F;border-left:2px solid #a6b18c;padding-left:17px;margin:22px 0}.story-paragraph{font-size:16px;margin:28px 0;white-space:normal}
.story-card figure{margin:30px 0}.story-card img{display:block;width:100%;height:auto;max-height:560px;object-fit:contain;background:#F3F3ED;border-radius:8px;border:1px solid #e6e7dc}
.story-card figcaption{font-size:13px;color:#626D63;line-height:1.9;margin-top:11px}.story-cta{padding:18px 20px;background:#f0f2e7;border-left:2px solid #a6b18c;font-weight:500}.story-tags{color:#99543E;font-size:14px;line-height:2}
@media(max-width:760px){.story-card h1{font-size:28px}.story-paragraph{font-size:15px}.story-lead{font-size:15px}.story-card{padding:6px 0}.story-card figcaption{font-size:13px}}
'''


def run_ui_stream(*args):
    """Stream actual pipeline milestones while the synchronous model request runs."""
    updates=Queue()
    def work():
        try:updates.put(('result',run_ui(*args,on_progress=lambda event:updates.put(('progress',event)))))
        except Exception:
            updates.put(('error',None))
    Thread(target=work,daemon=True).start()
    last_stage=0;last_event={}
    while True:
        kind,payload=updates.get()
        if kind=='progress':
            if payload['stage']>=0:last_stage=payload['stage']
            last_event={**payload,'last_stage':last_stage}
            # Only delivery of the actual result can announce final completion.
            if payload['state']=='active':yield (*[gr.skip() for _ in range(10)],workflow(last_event))
        elif kind=='result':
            yield (*payload,workflow(last_event));break
        else:
            failure=pl.Report(status='failed',message='页面处理失败，请重试；未展示为可用稿。')
            yield (_banner(failure),'','',rich_article(failure),'','',[],None,None,None,
                   workflow({'stage':-1,'last_stage':last_stage,'state':'failed','detail':failure.message}));break


class StudioBlocks(gr.Blocks):
    """Keep the studio assets when a host calls demo.launch() itself."""
    def launch(self,*args,**kwargs):
        kwargs.setdefault('css',studio_css());kwargs.setdefault('js',studio_js())
        kwargs.setdefault('footer_links',[]);kwargs.setdefault('run_history',False)
        return super().launch(*args,**kwargs)


def build() -> gr.Blocks:
    entries=catalog.products();choices=catalog.product_choices()
    default=next((p['id'] for p in entries if p['name']=='HUAWEI MateBook Pro'),entries[0]['id'] if entries else None)
    with StudioBlocks(title="华为 PC · 场景创作室",analytics_enabled=False) as demo:
        gr.HTML('<style>'+STORY_CSS+'</style>')
        previous = gr.State(None)
        gr.HTML('''<header class="studio-header"><div class="studio-brand"><span class="brand-mark" aria-hidden="true">✳</span><div>华为 PC · 场景创作室<small>SCENARIO MARKETING STUDIO</small></div></div><div class="header-tools"><span><i class="local-dot"></i>本地创作工作台</span><button id="motion-toggle" type="button" aria-pressed="true">动效已开启</button></div></header>''',elem_id='studio-header')
        gr.HTML(f'''<section class="studio-intro"><div><p class="eyebrow">FROM SCENARIO TO STORY</p><h1>让每一句表达，<em>都有据可循。</em></h1><p>从一个真实场景开始，把产品信息变成有依据、有人情味的图文。</p></div><aside class="intro-aside"><strong>先有证据，再有表达。</strong><br>{len(entries)} 个产品 · 4 种发布渠道<br>原文可追溯 · 原图可核对</aside></section>''',elem_id='studio-intro')
        progress=gr.HTML(workflow(),elem_id='workflow')
        if TEST_MODE:
            gr.HTML('<div style="background:#b91c1c;color:#fff;padding:8px">测试模式：结果不是真实运行结果，'
                    "不得放进说明书的运行结果。</div>")
        with gr.Row(elem_id='studio-workspace'):
            with gr.Column(scale=4,min_width=310,elem_id='brief-column'):
                gr.HTML('<div class="section-heading"><p class="eyebrow">01 / THE BRIEF</p><h2>这次，写给谁？</h2><p>清晰的任务，是好内容的第一步。</p></div>')
                product = gr.Dropdown(choices,label="选择产品（可输入型号关键词搜索）",value=default,filterable=True)
                with gr.Accordion('查看产品资料范围',open=False):
                    product_info=gr.Markdown(catalog.describe(default or ''),elem_id='product-info')
                with gr.Row(elem_classes='pair-row'):
                    variant = gr.Dropdown(['按资料区分','标准版','SE 版','柔光版','非柔光版'],label="产品版本 / 配置",value='按资料区分',allow_custom_value=True,min_width=120)
                    os_name = gr.Dropdown(['按资料区分','HarmonyOS','Windows','Linux'],label="操作系统",value='按资料区分',min_width=120)
                with gr.Row(elem_classes='pair-row'):
                    audience = gr.Textbox(label="目标人群", placeholder="例如：大学新生",value='大学新生',min_width=120)
                    scene = gr.Dropdown(SCENES, label="使用场景", value="开学季",min_width=120)
                platform = gr.Radio(PLATFORMS, label="发布渠道", value="小红书",elem_id='channel-choice')
                free_text = gr.Textbox(label="补充说明（可选，也可只写一句话需求）", lines=2)
                with gr.Accordion('内容设置、修订与资料模式',open=False):
                    detail_level=gr.Radio(['标准','详细'],label='内容详略',value='详细')
                    image_count=gr.Slider(1,6,value=6,step=1,label='期望图片数（受渠道上限和实际素材限制）')
                    extra = gr.Textbox(label="修订要求（可选，例如删段、换卖点）", lines=2)
                    mode_choice = gr.Dropdown([("本地 v7 资料（不请求 ima，未核远端最新）", "cache"),
                                               ("实时（本次读取 ima，失败即停止）", "live")],
                                              label="运行模式（显式选择，不会自动切换）", value="cache")
                btn = gr.Button("✧  生成并核验  ↗", variant="primary",elem_id='generate')
                gr.HTML('<p class="source-footnote">默认读取本地 v7 原件，核对文件指纹；未验证远端最新。生成将调用模型，失败与缺图会如实提示。</p>')
            with gr.Column(scale=7,min_width=420,elem_id='result-column'):
                gr.HTML('<div class="result-heading"><div><p class="eyebrow">02 / THE STORY</p><h2>把产品，写进生活。</h2></div><span>图文与依据，同步呈现</span></div>')
                banner = gr.HTML(elem_id='run-banner')
                with gr.Tabs(elem_id='story-tabs'):
                    with gr.Tab('图文初稿'):
                        s3=gr.HTML(EMPTY_ARTICLE,elem_id='article-preview')
                    with gr.Tab('场景策略'):s1=gr.Markdown('生成后可查看人群判断、内容切入点与卖点取舍。')
                    with gr.Tab('原文依据'):s2=gr.Markdown('生成后可查看本次引用的原文与来源指纹。')
                    with gr.Tab('核验素材'):
                        s4=gr.Markdown('生成后可查看规则核验、受限项与本型号原图。')
                        gallery=gr.Gallery(label='本次原图（可放大查看）',columns=3,height=380,object_fit='contain',format='png',buttons=['fullscreen','download'])
                with gr.Accordion('复制文本与下载图文  ↗',open=False,elem_id='export-panel'):
                    export=gr.Textbox(label='完整文本（含来源）',lines=12,buttons=['copy'])
                    download=gr.File(label='下载文本',interactive=False)
                    html_download=gr.File(label='下载完整图文 HTML（含实际图片，可离线打开）',interactive=False)
        gr.HTML('<footer class="studio-footer"><span>SCENARIO STUDIO · 让创作有温度，让事实有来处。</span><span>来源、核验和素材限制，请在交付前一并查看。</span></footer>')
        controls = [product, audience, scene, platform, free_text, variant, os_name, extra, mode_choice, btn,image_count,detail_level]
        outputs = [banner, s1, s2, s3, s4, export, gallery, download, previous,html_download]
        def begin():
            cleared=list(reset_ui());cleared[0]='';cleared[3]='<div class="article-empty"><h3>正在组织这一次表达。</h3><p>执行节点会随实际进度更新；核验通过后呈现图文。</p></div>';cleared[8]=gr.skip()
            return (*[gr.update(interactive=False) for _ in controls],*cleared,workflow({'stage':0,'state':'active','detail':'任务已提交，正在检查输入。'}))
        event = btn.click(begin, outputs=[*controls,*outputs,progress], queue=False)
        event = event.then(run_ui_stream,
                           [product, audience, scene, platform, free_text, variant, os_name, extra, mode_choice, previous,image_count,detail_level],
                           [*outputs,progress], concurrency_limit=1,show_progress='hidden')
        event.then(lambda: [gr.update(interactive=True) for _ in controls], outputs=controls, queue=False)
        for control in (product, audience, scene, platform, free_text, variant, os_name, mode_choice,image_count,detail_level):
            def reset_studio():
                cleared=list(reset_ui());cleared[3]=EMPTY_ARTICLE
                return (*cleared,workflow())
            control.input(reset_studio, outputs=[*outputs,progress], queue=False)
        product.change(catalog.describe,inputs=product,outputs=product_info,queue=False)
    return demo
