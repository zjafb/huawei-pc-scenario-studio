"""Presentation-only assets and truthful workflow rendering for the Gradio studio."""
import base64
import html
from pathlib import Path

ASSETS=Path(__file__).parent/'assets'

def studio_css():
    fonts=''
    for name,file in [('Studio Sans','studio-sans.woff2'),('Studio Serif','studio-serif.woff2')]:
        encoded=base64.b64encode((ASSETS/'fonts'/file).read_bytes()).decode()
        fonts+=f'@font-face{{font-family:"{name}";src:url(data:font/woff2;base64,{encoded}) format("woff2");font-weight:400 700;font-display:swap;}}'
    return fonts+(ASSETS/'studio.css').read_text(encoding='utf-8')+'\n'+(ASSETS/'studio-polish.css').read_text(encoding='utf-8')

def studio_js():
    base=(ASSETS/'studio.js').read_text(encoding='utf-8')
    effects=(ASSETS/'studio-effects.js').read_text(encoding='utf-8')
    return '() => { ('+base+')(); ('+effects+')(); }'

def workflow(event=None):
    event=event or {};stage=event.get('stage',-1);state=event.get('state','idle')
    success=state in ('qualified','restricted');terminal=state not in ('idle','active')
    active=event.get('last_stage',stage) if stage<0 and terminal else stage
    label={'idle':'等待开始','active':'正在执行','qualified':'核验通过','restricted':'受限完成',
           'need_info':'需要补充','blocked':'已拦截','failed':'执行未通过'}.get(state,'执行未通过')
    titles=[('确认任务','产品、配置与发布渠道'),('核对依据','读取原文并校验素材'),('场景创作','模型按场景组织图文'),('规则核验','引用、数字与内容检查')]
    nodes=[]
    for i,(title,detail) in enumerate(titles):
        status='done' if success or i<active else 'error' if terminal and i==active else 'active' if state=='active' and i==active else 'waiting'
        word={'done':'已完成','error':'请查看结果','active':'执行中','waiting':'待执行'}[status]
        note=event.get('detail',detail) if i==active else detail
        nodes.append(f'<details class="flow-node {status}"><summary><span class="node-badge">{"✓" if status=="done" else str(i+1).zfill(2)}</span><span><strong>{title}</strong><small>{word}</small></span></summary><p>{html.escape(str(note))}</p></details>')
    progress=100 if success else max(0,active)*100/4
    return '<section class="execution" aria-label="实际执行进度"><div class="execution-heading"><strong>创作路径</strong><span role="status">'+label+'</span></div><div class="pipeline" style="--progress:'+str(progress)+'%">'+''.join(nodes)+'</div><p class="execution-note">'+html.escape(event.get('detail') or '从一个真实场景开始。展开节点可查看执行说明，进度随实际任务更新。')+'</p></section>'

EMPTY_ARTICLE='''<div class="article-empty"><div class="empty-mark" aria-hidden="true">✳</div><p class="eyebrow">A NEW STORY BEGINS HERE</p><h3>好内容，从一个真实场景开始。</h3><p>在左侧选好产品、读者与渠道，<br>让事实成为表达的起点。</p><div class="empty-lines" aria-hidden="true"><i></i><i></i><i></i></div><span>生成后，这里将呈现经过核验的图文与来源。</span></div>'''
