"""Evaluate angular error, segmentation overlap, and rejection on held-out data."""
import argparse
import json
import time
from pathlib import Path
import cv2
import numpy as np
from app import project_paths as paths
from app.navigation.ai_scan import predict_heading
from tools.evaluate_scan_labels import polygon_heading


def main():
    parser=argparse.ArgumentParser();parser.add_argument('run',type=Path);parser.add_argument('--weights',choices=['best','last'],default='best');parser.add_argument('--split',choices=['val','test','all'],default='all');args=parser.parse_args()
    import torch
    from ultralytics import YOLO
    torch.set_num_threads(4)
    device='cpu'
    model=YOLO(str(args.run/f'fit/weights/{args.weights}.pt'))
    audit=json.loads((args.run/'dataset/split.json').read_text(encoding='utf-8'))
    folder=args.run/f'evaluation_{args.weights}_{args.split}';folder.mkdir(exist_ok=True);rows=[];summary={}
    for split in (('val','test') if args.split=='all' else (args.split,)):
        for record in audit['splits'][split]:
            identity=record['id'];file=args.run/'dataset/images'/split/f'{identity}.png'
            frame=cv2.imread(str(file));label=json.loads((paths.ROOT/'data/navigation/scan_segmentation/annotations'/f'{identity}.json').read_text(encoding='utf-8'))
            circle=record.get('circle',dict(center_xy=[100,100],radius=100))
            angle,aperture=polygon_heading(label['polygon_xy'],circle['center_xy'])
            started=time.perf_counter();result,mask=predict_heading(model,frame,circle,device)
            result.update(id=identity,split=split,label_direction_deg=angle,elapsed_ms=(time.perf_counter()-started)*1000,
                          error_deg=None if result['direction_deg'] is None else abs((result['direction_deg']-angle+180)%360-180))
            if mask is not None:
                truth=np.zeros(frame.shape[:2],np.uint8)
                cv2.fillPoly(truth,[np.round(label['polygon_xy']).astype(np.int32)],1)
                predicted=mask>.5
                result['mask_iou']=float(np.count_nonzero(predicted&(truth>0))/max(np.count_nonzero(predicted|(truth>0)),1))
                preview=frame.copy();preview[predicted]=(.5*preview[predicted]+.5*np.array([0,255,0])).astype(np.uint8)
                cv2.imwrite(str(folder/f'{identity}.png'),preview)
            rows.append(result)
        subset=[r for r in rows if r['split']==split];errors=[r['error_deg'] for r in subset if r['error_deg'] is not None]
        summary[split]=dict(total=len(subset),accepted=len(errors),mean_error_deg=sum(errors)/len(errors) if errors else None,
            maximum_error_deg=max(errors,default=None),errors_over_10_deg=sum(e>10 for e in errors),
            mean_mask_iou=float(np.mean([r.get('mask_iou',0) for r in subset])))
    negatives=[]
    manifest=json.loads((paths.ROOT/'data/navigation/scan_segmentation/manifest.json').read_text(encoding='utf-8'))
    for record in manifest:
        if record['status']!='invalid_capture':continue
        file=paths.ROOT/'data/navigation/scan_segmentation/images'/f'{record["id"]}.png'
        frame=cv2.imread(str(file))
        if frame is None:continue
        circle=record.get('circle',dict(center_xy=[100,100],radius=100))
        rejection,_=predict_heading(model,frame,circle,device)
        negatives.append(dict(id=record['id'],status=rejection['status'],direction_deg=rejection['direction_deg']))
    result=dict(weights=args.weights,scope=audit['scope'],navigation_approved=False,confidence_calibrated=False,summary=summary,samples=rows,
                non_game_checks=negatives,non_game_false_accepts=sum(r['direction_deg'] is not None for r in negatives))
    (folder/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
