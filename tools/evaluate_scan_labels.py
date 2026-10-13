"""Development-set angular evaluation; never calibrates confidence or navigation."""
import json
import math
from pathlib import Path
import cv2
from app import project_paths as paths
from app.navigation.scan_sequence import analyze_sequence


def polygon_heading(points,center=(100,100)):
    apex_index=min(range(len(points)),key=lambda i:math.dist(points[i],center))
    apex=points[apex_index]
    if math.dist(apex,center)>8:raise ValueError('Polygon apex is not near minimap center')
    edges=[points[(apex_index-1)%len(points)],points[(apex_index+1)%len(points)]]
    angles=[math.degrees(math.atan2(y-apex[1],x-apex[0]))%360 for x,y in edges]
    delta=(angles[1]-angles[0]+180)%360-180
    if not 45<=abs(delta)<=90:raise ValueError('Unexpected labeled sector aperture')
    return (angles[0]+delta/2)%360,abs(delta)


def main():
    data=paths.ROOT/'data/navigation/scan_segmentation'
    geometry=json.loads((paths.ROOT/'outputs/navigation/geometry_review/report.json').read_text(encoding='utf-8'))
    by_id={Path(r['source']).stem:r for r in geometry}
    temporal={};rows=[]
    for file in sorted((data/'annotations').glob('*.json')):
        label=json.loads(file.read_text(encoding='utf-8'));group=label['group']
        # Movement labels have a separate replay evaluator and no stationary
        # sequence indexed by their group. Never silently treat them as turns.
        if label['id'] not in by_id:continue
        heading,aperture=polygon_heading(label['polygon_xy'])
        if group not in temporal:
            folder=paths.ROOT/'outputs/navigation/fixed_turn_sequences'/group
            frames=[cv2.imread(str(p)) for p in sorted(folder.glob('frame_*.png'))]
            temporal[group]=analyze_sequence(frames,(100,100),100)
        sequence=temporal[group];index=int(label['id'].rsplit('_',1)[1])
        estimates=sequence.get('estimates',[])
        time_angle=estimates[index]['angle_deg'] if len(estimates)>index else None
        spatial=by_id[label['id']]
        predictions={'geometry':spatial['direction_deg'],'legacy':spatial['legacy']['angle_deg'],
            'consensus':spatial['spatial_consensus']['direction_deg'],'temporal':time_angle}
        rows.append({'id':label['id'],'label_direction_deg':heading,'aperture_deg':aperture,
            'predictions':predictions,'errors_deg':{k:None if a is None else abs((a-heading+180)%360-180) for k,a in predictions.items()}})
    summary={}
    for method in ('geometry','legacy','consensus','temporal'):
        errors=[r['errors_deg'][method] for r in rows if r['errors_deg'][method] is not None]
        summary[method]={'accepted':len(errors),'total':len(rows),
            'mean_error_deg':sum(errors)/len(errors) if errors else None,
            'maximum_error_deg':max(errors,default=None),'errors_over_10_deg':sum(e>10 for e in errors)}
    result={'scope':'Same-location development labels; not independent validation or calibrated confidence',
            'navigation_approved':False,'summary':summary,'samples':rows}
    target=paths.ROOT/'outputs/navigation/geometry_review/human_evaluation.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
