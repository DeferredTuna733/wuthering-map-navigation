"""Full decoded-tile offline acceptance check, independent of download status."""
import hashlib
import json
from pathlib import Path
from PIL import Image
from app.project_paths import OFFLINE_TILES


def verify(root):
    root=Path(root);missing=[];invalid=[];records=[]
    for z in (5,6):
        for y in range(2**z):
            for x in range(2**z):
                p=root/str(z)/f'{x}_{y}.png'
                if not p.is_file():missing.append([z,x,y]);continue
                try:
                    with Image.open(p) as im:
                        im.load()
                        if im.size!=(256,256) or im.format!='PNG':raise ValueError('Wrong format/size')
                    records.append({'z':z,'x':x,'y':y,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
                except (OSError,ValueError) as exc:invalid.append({'key':[z,x,y],'error':str(exc)})
    result={'expected':5120,'valid':len(records),'complete':len(records)==5120 and not missing and not invalid,
            'missing':missing,'invalid':invalid,'bytes':sum(r['bytes'] for r in records),'tiles':records}
    (root/'offline_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('complete',result['complete'],'valid',result['valid'],'missing',len(missing),'invalid',len(invalid),'MB',round(result['bytes']/1024**2,1))
    return result

if __name__=='__main__':
    report=verify(OFFLINE_TILES)
    raise SystemExit(0 if report['complete'] else 1)
