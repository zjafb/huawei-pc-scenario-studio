"""Create private thumbnail sheets for visual inspection; originals are unchanged."""
from pathlib import Path
import json
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
kb = ROOT / '华为PC全板块深度知识库_v7'
files = sorted(p for p in kb.rglob('*') if p.suffix.lower() in ('.png','.jpg','.jpeg','.webp'))
out = ROOT/'data/private/asset-audit'
out.mkdir(parents=True,exist_ok=True)
font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',15)
entries=[]
for start in range(0,len(files),16):
    sheet=Image.new('RGB',(1280,1040),'#e6e8ed')
    draw=ImageDraw.Draw(sheet)
    for slot,path in enumerate(files[start:start+16]):
        n=start+slot+1;x=(slot%4)*320;y=(slot//4)*260
        with Image.open(path) as im:
            original=im.size
            thumb=im.convert('RGBA');thumb.thumbnail((310,205))
            sheet.paste(thumb,(x+(320-thumb.width)//2,y+5),thumb)
        label=f'{n:03d} {path.parent.parent.name[:19]}'
        draw.text((x+5,y+210),label,font=font,fill='black')
        draw.text((x+5,y+234),f'{original[0]}×{original[1]} {path.name[:22]}',font=font,fill='black')
        entries.append({'id':n,'path':path.relative_to(kb).as_posix(),'size':original})
    sheet.save(out/f'sheet-{start//16+1}.png')
(out/'index.json').write_text(json.dumps(entries,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'images':len(files),'sheets':(len(files)+15)//16,'folder':str(out)},ensure_ascii=False))
