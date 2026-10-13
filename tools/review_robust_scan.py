"""Replay a recorded step without modifying its original measurements."""
import json
from pathlib import Path
import cv2
import numpy as np
from app.navigation.robust_scan import estimate_robust_heading


def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path);args=parser.parse_args()
    original=json.loads((args.folder/'report.json').read_text(encoding='utf-8'))
    model_folder=Path(original['reference_report']).parent
    background=np.load(model_folder/'background.npy',allow_pickle=False)
    reference=cv2.imread(str(model_folder/'reference.png'));circle=original['circle'];rows=[]
    for file in sorted(args.folder.glob('after_[0-9][0-9].png')):
        r=estimate_robust_heading(reference,background,cv2.imread(str(file)),circle['center_xy'],circle['radius'])
        r['image']=str(file);rows.append(r)
        print(file.name,r['status'],r['direction_deg'],[(b['direction_deg'],round(b['explained_fraction'],3)) for b in r.get('radial_bands',[])])
    (args.folder/'robust_review.json').write_text(json.dumps({'observations':rows,
        'navigation_approved':False,'live_matching_changed':False,'scope':'Offline radial consensus, not calibrated confidence'},ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
