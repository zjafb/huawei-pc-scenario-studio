"""Real v2 acceptance: full catalogue and four channels, no canned marketing output."""
import argparse,json,sys
from pathlib import Path
from datetime import datetime
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.catalog import products
from app.full_pipeline import run_task,to_text
from run_records import save_run

def main():
 p=argparse.ArgumentParser();p.add_argument('--run',action='store_true');p.add_argument('--channel',default='all');args=p.parse_args()
 if not args.run:print('Use --run to call the configured model. Uses supplied local materials; no ima request.');return 0
 product=next(p for p in products() if p['name']=='HUAWEI MateBook Pro')
 folder=ROOT/'data/private/full-acceptance'/datetime.now().strftime('%Y%m%d-%H%M%S');folder.mkdir(parents=True)
 cases=['wechat','xhs','moments','poster'] if args.channel=='all' else [args.channel]
 rows=[]
 for channel in cases:
  report=run_task(product=product['id'],audience='大学新生' if channel=='xhs' else '经常移动办公的职场人士',scene='开学季' if channel=='xhs' else '职场差旅',platform=channel,mode='cache',detail_level='详细',image_count=6)
  record=save_run(report)
  (folder/(channel+'.txt')).write_text(to_text(report),encoding='utf-8-sig')
  row={'channel':channel,'product':report.product_name,'status':report.status,'images':len(report.images),'run_id':record.stem,'checks':report.checks,'source_stats':report.run.get('source_stats'),'model_stats':report.run.get('model_stats')}
  rows.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
 (folder/'summary.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
 print(str(folder/'summary.json'));return 0 if all(r['status']=='qualified' for r in rows) else 1
if __name__=='__main__':raise SystemExit(main())
