"""Record the agent's actual contact-sheet visual inspection, not human signatures."""
from pathlib import Path
import csv,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.catalog import KB_ROOT,read_verified

VIEWS={1:('绿色机身斜侧面与键盘','angle-green'),2:('粉金色机身斜侧面与键盘','angle-pink'),
3:('电脑正面，屏幕展示演示文稿界面','screen-document'),4:('灰色机身斜侧面与键盘','angle-grey'),
5:('闭合电脑的侧边与接口','closed-side'),6:('绿色电脑正面完整外观','front-green'),7:('绿色电脑闭合上盖，HUAWEI 标识','lid-green'),
8:('绿色电脑正面完整外观','front-green'),9:('绿色电脑键盘俯视图','keyboard-green'),11:('展开电脑的侧边形态与接口','open-side'),
13:('绿色电脑正面完整外观','front-green'),14:('浅金色电脑正面完整外观','front-gold'),16:('粉金色电脑正面完整外观','front-pink'),
17:('粉金色电脑正面完整外观','front-pink'),18:('绿色电脑闭合侧边与接口','closed-side'),
20:('官方人物手持金色闭合电脑的场景图','person-gold'),21:('官方人物手持白色闭合电脑的场景图','person-white'),
22:('官方人物手持黑色闭合电脑的场景图','person-black'),23:('官方场景：展开电脑与手机同时出镜','scene-devices'),24:('折叠电脑展开并配键盘的完整主视觉','hero-fold'),
25:('官方户外场景：人物在浅金色电脑前','scene-outdoor'),26:('官方户外场景：人物在灰色电脑前','scene-outdoor-grey'),
27:('官方场景：人物在浅色电脑前','scene-indoor'),28:('官方办公场景：黑色电脑与手写笔','scene-writing'),
29:('官方办公场景：黑色电脑与手写笔','scene-writing'),30:('官方场景：电脑、手机与平板同时出镜','scene-devices'),
31:('官方街景：人物手持闭合电脑出行','scene-travel'),32:('深色电脑正面，屏幕为蓝色弧形壁纸','hero-dark'),
33:('紫色电脑展开侧面形态','open-side'),34:('紫色电脑正面完整外观','hero-purple'),35:('官方多人桌面协作场景，数台电脑同时出镜','scene-meeting'),
36:('紫色电脑闭合上盖特写','lid-purple'),37:('官方户外场景：人物坐在台阶上使用电脑','scene-outdoor'),38:('金色电脑闭合侧边','closed-gold'),
39:('绿色电脑与屏幕手写笔示意','hero-pen'),40:('绿色电脑与屏幕手写笔示意','hero-pen'),43:('电脑完整正面与彩色壁纸','hero-front'),
45:('绿色电脑斜侧面，背景有宣传标语','angle-styled'),46:('绿色电脑斜侧面，背景有宣传标语','angle-styled'),
47:('电脑、手机、平板等设备的互联关系示意，不是整机外观','diagram-devices'),49:('电脑完整正面与彩色壁纸','hero-front'),
55:('电脑与多种设备的互联图标示意，不是整机外观','diagram-devices'),56:('电脑、手机、平板等设备的互联关系示意','diagram-devices'),
58:('银色电脑斜侧面，屏幕展示页面界面','hero-silver'),62:('电脑机身侧边与接口的局部特写','detail-ports'),
63:('多台电脑的不同角度与颜色组合主视觉','hero-colors'),64:('电脑斜侧面，屏幕展示文档界面','scene-document'),
66:('电脑后侧机身、散热开口与转轴特写','detail-vent'),67:('官方人物侧坐并使用电脑的场景','scene-white'),68:('官方人物手持电脑的场景','scene-pink')}

def main():
 expected_manifest='5f2bb15bff7c8f28410391d2ffee2349d887fc59657753d6e924780a0135afe6'
 if hashlib.sha256((KB_ROOT/'全库文件清单_SHA256.csv').read_bytes()).hexdigest()!=expected_manifest:
  raise ValueError('This visual review is only valid for the inspected v7 manifest; inspect new materials again.')
 index=json.loads((ROOT/'data/private/asset-audit/index.json').read_text(encoding='utf-8'))
 rows=[]
 for entry in index:
  path=Path(entry['path'])
  parent=path.parent if (KB_ROOT/path.parent/'图片索引.csv').exists() else path.parent.parent
  csv_path=KB_ROOT/parent/'图片索引.csv'
  sources={}
  if csv_path.exists():
   sources={r['文件名']:r for r in csv.DictReader(csv_path.read_text(encoding='utf-8-sig').splitlines())}
  source=sources.get(path.name,{})
  accepted=entry['id'] in VIEWS and bool(source)
  view,group=VIEWS.get(entry['id'],('未选入生成：网页条幅、功能广告卡、空白屏幕组件、品牌标识或无对应型号的装饰画面','excluded'))
  _,sha=read_verified(entry['path'])
  owner=parent.parent if parent.name=='商城款式图片' else parent
  rows.append({'id':f"I{entry['id']:03d}",'file':entry['path'],'sha256':sha,'product_folder':owner.as_posix(),
    'name':view,'actual_view':view,'view_group':group,'source_title':source.get('产品型号','')+' / 原图素材索引',
    'source_url':source.get('来源页面',''),'original_url':source.get('原始图片URL',''),
    'usable':accepted,'usage_limit':'仅说明实际画面，不证明具体 SKU、性能、护眼效果或无条件兼容；官方人物场景不代表用户实测。',
    'review_method':'Codex inspected original-image thumbnail contact sheets 1–7; no human signature claimed',
    'policy':'User explicitly removed signature requirement and authorized all supplied materials on 2026-10-18'})
 output=ROOT/'data/private/asset-review-v2.json'
 output.write_text(json.dumps({'images':rows},ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'reviewed':len(rows),'usable':sum(r['usable'] for r in rows)},ensure_ascii=False))

if __name__=='__main__':main()
