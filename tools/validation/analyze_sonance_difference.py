import json
from pathlib import Path
import numpy as np
from app.project_paths import ROOT

g=json.loads((ROOT / 'data/map_validation/research/wuthering_gg/marks.json').read_text(encoding='utf-8'))
k=json.loads((ROOT / 'data/map_validation/research/kurobbs/position8.json').read_text(encoding='utf-8'))
a=np.unique(np.asarray(next(x for x in g if x['MarkTitle']=='声匣')['Locations'],float)[:,:2]/100,axis=0)
items=next(x for x in k if x['name']=='声匣')['location']
b=np.unique(np.asarray([[x['x'],x['y']] for x in items],float),axis=0)
d=np.linalg.norm(a[:,None,:]-b[None,:,:],axis=2)
j=d.argmin(axis=1); i=d.argmin(axis=0)
pairs=[(n,int(m)) for n,m in enumerate(j) if i[m]==n]
offsets=np.array([b[m]-a[n] for n,m in pairs])
shift=np.median(offsets,axis=0)
residual=np.linalg.norm(offsets-shift,axis=1)
r={'category':'声匣','coordinate_relation':'gg/100 compared to kuro raw', 'mutual_pairs':len(pairs),'median_offset_kuro_units':shift.tolist(),'offset_residual_median':float(np.median(residual)),'offset_residual_p95':float(np.percentile(residual,95)),'country_ids':sorted({x.get('countryId') for x in items}), 'warning':'Nearest-coordinate candidates only; not visual landmark correspondence. Do not apply this offset globally.', 'examples':[{'gg_div100':a[n].tolist(),'kuro':b[m].tolist(),'difference':(b[m]-a[n]).tolist()} for n,m in pairs[:8]]}
(ROOT / 'data/map_validation/research/sonance_difference.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({key:value for key,value in r.items() if key!='examples'},ensure_ascii=False,indent=2))
