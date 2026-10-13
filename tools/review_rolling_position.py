"""Replay saved monitor captures through the same continuous tracker as live UI."""
import argparse
import json
import math
from pathlib import Path
import cv2
from app import project_paths as paths
from app.navigation.position_anchor import load_anchor
from app.navigation.minimap_position import RollingPositionTracker


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('folder',type=Path)
    args=parser.parse_args()
    report=json.loads((args.folder/'report.json').read_text(encoding='utf-8'))
    anchor,image=load_anchor(paths.ROOT/'data/navigation/position_anchor.json',report['region'],report['circle'])
    tracker=RollingPositionTracker(image,report['circle'],anchor['angle'],anchor['coordinate_xy'],anchor['affine'],anchor['zoom'])
    rows=[]
    for original in report['observations']:
        frame=cv2.imread(str(args.folder/f"frame_{original['index']:03d}.png"))
        row=tracker.observe(frame,original['direction_deg'],original['frame_monotonic'])
        row.update(index=original['index'],ocr=original.get('coordinate'))
        xy=row['coordinate_xy']
        row['ocr_difference']=None if xy is None or row['ocr'] is None else math.dist(xy,row['ocr'][:2])
        row['ocr_corroborates_tracking']=tracker.corroborate(row['ocr'],original.get('coordinate_monotonic',-1))
        rows.append(row)
    output=dict(scope='Development replay; asynchronous OCR corroboration, not independent accuracy',
                samples=len(rows),accepted=sum(row['coordinate_xy'] is not None for row in rows),
                navigation_approved=False,observations=rows)
    (args.folder/'rolling_replay.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(samples=output['samples'],accepted=output['accepted'],
                         rejections=[(r['index'],r['status']) for r in rows if r['coordinate_xy'] is None],
                         ocr_checks=[(r['index'],r['ocr_difference'],r['ocr_corroborates_tracking']) for r in rows if r['ocr'] is not None]),ensure_ascii=False))


if __name__=='__main__':main()
