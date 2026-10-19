"""Real request/revision acceptance; no canned copy, source data stays private."""
from pathlib import Path
from datetime import datetime
import json,sys,time,re
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app import catalog,full_pipeline as flow
from run_records import save_run


def main():
    product=next(p for p in catalog.products() if p['name']=='HUAWEI MateBook Pro')
    folder=ROOT/'data/private/brief-acceptance'/datetime.now().strftime('%Y%m%d-%H%M%S');folder.mkdir(parents=True)
    base=dict(product=product['id'],audience='准备考研的大学生',scene='开学季',platform='moments',mode='cache',marketing_goal='store',image_count=1)
    description='围绕考研自习，正式语气，不要表情。标题改为“自习搭档，到店聊聊”。只讲屏幕，不要重量。写150字左右。'
    rows=[];previous=None
    for name,level,extra in [('initial','标准',''),('revision','详细','标题改为“带上课表，来聊选购”。缩短到100字以内，不要表情，必须包含“带上课表”，不要出现“自习搭档”。只讲系统，不写屏幕和重量。')]:
        start=time.monotonic()
        report=flow.run_task(**base,free_text=description,detail_level=level,extra_request=extra,previous_article=previous)
        record=save_run(report);(folder/(name+'.txt')).write_text(flow.to_text(report),encoding='utf-8-sig')
        row={'case':name,'status':report.status,'title':report.article.get('title'),'chars':len(re.sub(r'\s','',flow.FACT_MARK.sub('',flow._article_text(report.article)))),'revision_context_used':report.run['revision_context_used'],'requests':len(report.run.get('model_calls',[])),'seconds':round(time.monotonic()-start,2),'images':len(report.images),'checks':report.checks,'run_id':record.stem}
        rows.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
        (folder/'summary.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
        if report.status not in ('qualified','restricted'):return 1
        previous=report.article
    assert rows[0]['title']=='自习搭档，到店聊聊' and rows[1]['title']=='带上课表，来聊选购'
    assert rows[1]['revision_context_used'] and rows[1]['chars']<rows[0]['chars']
    assert rows[1]['chars']<=100
    assert all(r['requests']<=4 for r in rows)
    print('Private acceptance folder:',folder);return 0


if __name__=='__main__':raise SystemExit(main())
