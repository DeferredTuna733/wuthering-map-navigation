"""Export actual AI masks as editable suggestions, never as training labels."""
import json
from pathlib import Path
import shutil
import cv2
import numpy as np
import torch
from ultralytics import YOLO
from app import project_paths as paths
from app.navigation.ai_scan import mask_heading


def main():
    ids=json.loads((paths.ROOT/'outputs/navigation/ai_hard_example_label_queue.json').read_text())
    data=paths.ROOT/'data/navigation/scan_segmentation'
    records={r['id']:r for r in json.loads((data/'manifest.json').read_text(encoding='utf-8'))}
    folder=paths.ROOT/'outputs/navigation/ai_corrections/hard_examples_6'
    folder.mkdir(parents=True,exist_ok=True)
    torch.set_num_threads(4)
    weights=paths.ROOT/'models/navigation/camera_sector/experimental.pt'
    model=YOLO(str(weights));images={}
    colors=[(0,220,0),(255,120,0),(200,0,200),(0,180,255)]
    for identity in ids:
        source=data/'images'/f'{identity}.png'
        frame=cv2.imread(str(source));record=records[identity]
        prediction=model.predict(frame,imgsz=320,conf=.25,iou=.5,device='cpu',verbose=False,retina_masks=True)[0]
        candidates=[];combined=frame.copy()
        shutil.copy2(source,folder/f'{identity}_original.png')
        if prediction.masks is not None:
            for i,tensor in enumerate(prediction.masks.data):
                mask=tensor.cpu().numpy()
                if mask.shape!=frame.shape[:2]:mask=cv2.resize(mask,(frame.shape[1],frame.shape[0]),interpolation=cv2.INTER_NEAREST)
                binary=(mask>.5).astype(np.uint8)
                contours,_=cv2.findContours(binary,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
                if not contours:continue
                contour=max(contours,key=cv2.contourArea)
                polygon=cv2.approxPolyDP(contour,1.0,True).reshape(-1,2).tolist()
                score=float(prediction.boxes.conf[i].cpu())
                circle=record['circle']
                geometry=mask_heading(mask,circle.get('player_center_xy',circle['center_xy']),circle['radius'])
                color=np.array(colors[i%len(colors)])
                preview=frame.copy();selected=binary>0
                preview[selected]=(.55*preview[selected]+.45*color).astype(np.uint8)
                cv2.polylines(preview,[np.array(polygon,np.int32)],True,tuple(int(v) for v in color),1)
                cv2.imwrite(str(folder/f'{identity}_candidate_{i+1}.png'),preview)
                combined[selected]=(.65*combined[selected]+.35*color).astype(np.uint8)
                candidates.append(dict(number=i+1,score=score,polygon_xy=polygon,
                    geometry=geometry,preview=str(folder/f'{identity}_candidate_{i+1}.png')))
        combined=cv2.resize(combined,(600,600),interpolation=cv2.INTER_NEAREST)
        cv2.imwrite(str(folder/f'{identity}_detected.png'),combined)
        images[identity]=dict(candidates=candidates,original=str(source),detected=str(folder/f'{identity}_detected.png'))
    (folder/'suggestions.json').write_text(json.dumps(dict(model=str(weights),label_source='unconfirmed_ai_suggestion',images=images),ensure_ascii=False,indent=2),encoding='utf-8')
    print('Detection previews and editable suggestions:',folder,flush=True)


if __name__=='__main__':main()
