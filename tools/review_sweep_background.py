"""Label-free background fitting with leave-one-out angular error reporting."""
import json
from pathlib import Path
import cv2
import numpy as np
from app import project_paths as paths
from app.navigation.scan_background import build_sweep_background
from app.navigation.moving_scan import estimate_moving_heading
from tools.scan_labeler import DATA
from tools.evaluate_scan_labels import polygon_heading


def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('session');args=parser.parse_args()
    records=[r for r in json.loads((DATA/'manifest.json').read_text(encoding='utf-8')) if r['group']==args.session]
    frames=[cv2.imread(str(DATA/'images'/(r['id']+'.png'))) for r in records]
    if not frames or any(f is None for f in frames):raise ValueError('Capture images missing')
    circle=records[0]['circle'];center=circle['center_xy'];radius=circle['radius']
    if any(r['circle']!=circle or r['region']!=records[0]['region'] for r in records):raise ValueError('Capture region changed within session')
    background,model=build_sweep_background(frames,center,radius)
    rows=[]
    for i,(record,frame) in enumerate(zip(records,frames)):
        # No image under evaluation is used to construct its background.
        other=[f for j,f in enumerate(frames) if j!=i]
        try:
            leaveout,_=build_sweep_background(other,center,radius)
            reference=frames[1] if i==0 else frames[0]
            result=estimate_moving_heading(reference,leaveout,frame,center,radius)
        except ValueError as error:
            result={'status':'leaveout_reference_unresolved','direction_deg':None,
                    'reason':str(error),'navigation_approved':False}
        result['id']=record['id'];label_path=DATA/'annotations'/(record['id']+'.json')
        if label_path.exists():
            label=json.loads(label_path.read_text(encoding='utf-8'));human,_=polygon_heading(label['polygon_xy'],center)
            result['human_direction_deg']=human
            result['error_deg']=None if result['direction_deg'] is None else abs((result['direction_deg']-human+180)%360-180)
        rows.append(result)
    errors=[r['error_deg'] for r in rows if r.get('error_deg') is not None]
    summary={'accepted':sum(r['direction_deg'] is not None for r in rows),'total':len(rows),
        'mean_error_deg':sum(errors)/len(errors) if errors else None,'maximum_error_deg':max(errors,default=None)}
    output=paths.ROOT/'outputs/navigation/sweep_backgrounds'/args.session
    output.mkdir(parents=True,exist_ok=True);np.save(output/'background.npy',background)
    cv2.imwrite(str(output/'background_preview.png'),np.clip(background,0,255).astype(np.uint8))
    cv2.imwrite(str(output/'reference.png'),frames[0])
    result={'scope':'Same-scene leave-one-out replay, not independent-scene validation',
        'circle':circle,'region':records[0]['region'],'model':model,'summary':summary,
        'samples':rows,'navigation_approved':False,'live_matching_changed':False}
    (output/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary))


if __name__=='__main__':main()
