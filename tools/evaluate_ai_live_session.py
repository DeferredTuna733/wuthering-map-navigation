"""Replay a live diagnostic session. Training examples are not independent tests."""
import argparse
import json
import math
from pathlib import Path
import cv2
import numpy as np
import torch
from ultralytics import YOLO
from app import project_paths as paths
from app.navigation.ai_scan import predict_heading
from tools.evaluate_scan_labels import polygon_heading


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--weights',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--session',default='20261011_210442_349840')
    args=p.parse_args()
    torch.set_num_threads(4)
    folder=paths.ROOT/'outputs/navigation/ai_live_checks'/args.session
    original=json.loads((folder/'report.json').read_text(encoding='utf-8'))
    circle=original['circle']
    calibration=json.loads((paths.ROOT/'config/navigation/ai_sector_geometry.json').read_text())
    if calibration['region']==original['region']:
        circle=dict(circle,player_center_xy=calibration['player_center_xy'])
    data=paths.ROOT/'data/navigation/scan_segmentation'
    labels={}
    for f in (data/'annotations').glob(f'ai_live_{args.session}_*.json'):
        r=json.loads(f.read_text(encoding='utf-8'))
        labels[int(r['id'].rsplit('_',1)[1])]=polygon_heading(r['polygon_xy'],circle['center_xy'])[0]
    model=YOLO(str(args.weights));rows=[]
    args.output.mkdir(parents=True,exist_ok=True)
    for old in original['observations']:
        i=old['index'];frame=cv2.imread(str(folder/f'frame_{i:03d}.png'))
        row,mask=predict_heading(model,frame,circle)
        row.update(index=i,label_direction_deg=labels.get(i))
        row['error_deg']=None if i not in labels or row['direction_deg'] is None else abs((row['direction_deg']-labels[i]+180)%360-180)
        rows.append(row)
        if i in labels:
            overlay=frame.copy()
            if mask is not None:
                selected=mask>.5
                overlay[selected]=(.5*overlay[selected]+.5*np.array([0,255,0])).astype('uint8')
            c=tuple(round(v) for v in circle['player_center_xy'])
            for angle,color in ((labels[i],(255,0,0)),(row['direction_deg'],(0,0,255))):
                if angle is not None:
                    end=(round(c[0]+80*math.cos(math.radians(angle))),round(c[1]+80*math.sin(math.radians(angle))))
                    cv2.arrowedLine(overlay,c,end,color,1)
            cv2.imwrite(str(args.output/f'overlay_{i:03d}.png'),overlay)
    annotated=[r for r in rows if r['label_direction_deg'] is not None]
    errors=[r['error_deg'] for r in annotated if r['error_deg'] is not None]
    result=dict(scope='Diagnostic replay; annotated frames may be used for refinement training. Adjacent frames are correlated. Not independent accuracy.',
                navigation_approved=False,weights=str(args.weights),samples=len(rows),
                output_count=sum(r['direction_deg'] is not None for r in rows),
                labeled_count=len(annotated),labeled_accepted=len(errors),
                mean_error_deg=sum(errors)/len(errors) if errors else None,
                maximum_error_deg=max(errors,default=None),errors_over_10_deg=sum(e>10 for e in errors),
                labels=annotated,samples_detail=rows)
    (args.output/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('labels','samples_detail')},ensure_ascii=False))


if __name__=='__main__':main()
