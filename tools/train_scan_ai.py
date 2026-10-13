"""Train a small camera-sector segmenter with grouped, scene-aware holdout."""
import argparse
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
import cv2
import numpy as np
from app import project_paths as paths


def prepare(folder):
    source=paths.ROOT/'data/navigation/scan_segmentation'
    records=json.loads((source/'manifest.json').read_text(encoding='utf-8'))
    splits={name:[] for name in ('train','val','test')};seen={}
    for record in records:
        if record['status']!='labeled':continue
        group=record['group']
        early=(group.startswith('20261011_') or group.startswith('capture_20261011_182749')
               or group.startswith('backgroundcheck_20261011_184642') or group.startswith('backgroundcheck_20261011_185140'))
        validation=group in {'backgroundcheck_20261011_194540_036015','backgroundcheck_20261011_195041_507190','backgroundcheck_20261011_195421_717215'}
        split='test' if early else ('val' if validation else 'train')
        image=source/'images'/f'{record["id"]}.png';label=source/'labels'/f'{record["id"]}.txt'
        decoded=cv2.imread(str(image))
        if decoded is None or not label.exists():raise ValueError(f'Incomplete sample {record["id"]}')
        fields=label.read_text().split();values=np.asarray([float(x) for x in fields[1:]])
        if fields[0]!='0' or len(values)<6 or len(values)%2 or not np.isfinite(values).all() or np.any((values<0)|(values>1)):
            raise ValueError(f'Invalid polygon {record["id"]}')
        digest=hashlib.sha256(decoded.tobytes()).hexdigest()
        if digest in seen:
            if seen[digest]!=split:raise ValueError('Identical image crosses dataset split')
            continue
        seen[digest]=split
        for kind,file in (('images',image),('labels',label)):
            target=folder/kind/split;target.mkdir(parents=True,exist_ok=True)
            shutil.copy2(file,target/file.name)
        splits[split].append(record)
    (folder/'dataset.yaml').write_text(f'path: {folder.as_posix()}\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n  0: camera_sector\n',encoding='utf-8')
    audit=dict(scope='Earlier location held out as test; validation groups are nearby views, not independent global scenes',
               navigation_approved=False,splits=splits,counts={k:len(v) for k,v in splits.items()})
    (folder/'split.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    return audit


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--train',action='store_true');parser.add_argument('--epochs',type=int,default=100)
    parser.add_argument('--init-weights',type=Path);parser.add_argument('--device',default=None)
    args=parser.parse_args()
    run=paths.ROOT/'outputs/training/camera_sector'/datetime.now().strftime('%Y%m%d_%H%M%S')
    data=run/'dataset';data.mkdir(parents=True,exist_ok=False)
    audit=prepare(data);print('DATA',audit['counts'],flush=True)
    if not args.train:return
    import torch
    from ultralytics import YOLO
    torch.set_num_threads(4)
    device=args.device or ('xpu:0' if torch.xpu.is_available() else 'cpu')
    # Existing detection pretraining supplies shared features, avoiding an
    # untracked external download; segmentation layers initialize separately.
    model=(YOLO(str(args.init_weights)) if args.init_weights else
           YOLO('yolov8n-seg.yaml').load(str(paths.ROOT/'models/treasure/base_yolov8n.pt')))
    model.train(data=str(data/'dataset.yaml'),epochs=args.epochs,imgsz=320,batch=8,
        device=device,workers=0,amp=False,project=str(run),name='fit',
        pretrained=True,optimizer='AdamW',lr0=.0003 if args.init_weights else .001,patience=25,seed=42,
        mosaic=0,mixup=0,copy_paste=0,degrees=180,translate=.03,scale=.15,
        fliplr=.5,flipud=.5,hsv_h=.01,hsv_s=.2,hsv_v=.2,plots=False,
        save=True,verbose=False)
    (run/'training_complete.json').write_text(json.dumps(dict(weights=str(run/'fit/weights/best.pt'),
        dataset=str(data/'dataset.yaml'),device=device,init_weights=str(args.init_weights) if args.init_weights else None,
        navigation_approved=False),indent=2),encoding='utf-8')
    print('TRAINED',run,flush=True)


if __name__=='__main__':main()
