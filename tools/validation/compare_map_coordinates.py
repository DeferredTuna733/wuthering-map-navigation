"""Cross-source evidence audit; no game-coordinate approval or export."""
import json
from pathlib import Path
import numpy as np

from app.project_paths import ROOT

def audit():
    gg=json.loads((ROOT/'data/map_validation/research/wuthering_gg/marks.json').read_text(encoding='utf-8'))
    kuro={g['name']:g for g in json.loads((ROOT/'data/map_validation/research/kurobbs/position8.json').read_text(encoding='utf-8'))}
    records=[]
    # Discover relation on 云芝 only. Other named categories are held out.
    for name in ('云芝','鸢尾花','声匣','定风铎','傲寒钟','银雪莲'):
        group=next(g for g in gg if g['MarkTitle']==name)
        a=np.unique(np.asarray(group['Locations'],dtype=float)[:,:2],axis=0)
        locations=kuro[name]['location']
        b=np.unique(np.asarray([[p['x'],p['y']] for p in locations],dtype=float),axis=0)
        dist=np.linalg.norm(a[:,None,:]/100-b[None,:,:],axis=2)
        nearest_b=np.argmin(dist,axis=1)
        nearest_a=np.argmin(dist,axis=0)
        pairs=[(i,int(j),float(dist[i,j])) for i,j in enumerate(nearest_b) if nearest_a[j]==i]
        tight=[p for p in pairs if p[2] <= 1]
        records.append({'category':name,'role':'discovery' if name=='云芝' else 'holdout',
                        'gg_unique_count':len(a),'kuro_unique_count':len(b),
                        'mutual_pairs':len(pairs),'pairs_within_one_kuro_unit':len(tight),
                        'max_pair_error_kuro_units':max(p[2] for p in pairs),
                        'examples':[{'gg_xy':a[i].tolist(),'kuro_xy':b[j].tolist(),'error':d} for i,j,d in tight[:3]]})
    result={'status':'cross_source_data_relation_only_not_game_validated',
            'candidate_relation':'kuro_position_xy = gg_site_xy / 100',
            'axis_swap':False,'axis_signs':[1,1],
            'warning':'Mutual nearest matches are coordinate-selected, not independent visual landmark identification. Sources may share upstream data. No in-game or URL-unit validation.',
            'categories':records}
    (ROOT/'data/map_validation/research/cross_map_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

if __name__=='__main__':
    result=audit()
    for row in result['categories']:
        print(row['category'],row['role'],row['pairs_within_one_kuro_unit'], '/', row['mutual_pairs'], 'max error',row['max_pair_error_kuro_units'])
