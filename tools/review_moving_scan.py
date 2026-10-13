"""Replay a step using its recorded reference, not the current configuration."""
import json
from pathlib import Path
import cv2
from app.navigation.scan_sequence import analyze_sequence
from app.navigation.moving_scan import build_background,estimate_moving_heading


def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path);args=parser.parse_args()
    report=json.loads((args.folder/'report.json').read_text(encoding='utf-8'))
    ref=Path(report['reference_report']).parent
    frames=[cv2.imread(str(p)) for p in sorted(ref.glob('frame_*.png'))]
    analysis=analyze_sequence(frames,(100,100),100)
    background,amplitude=build_background(frames,[e['angle_deg'] for e in analysis['estimates']],(100,100),100)
    observations=[]
    for file in sorted(args.folder.glob('after_[0-9][0-9].png')):
        result=estimate_moving_heading(frames[0],background,cv2.imread(str(file)),(100,100),100)
        result['source']=str(file);observations.append(result)
    output={'reference_report':report['reference_report'],'background_overlay_amplitude':amplitude,
            'navigation_approved':False,'live_matching_changed':False,'observations':observations,
            'limitation':'Approximate additive overlay and one recorded movement; independent labels required.'}
    (args.folder/'separated_background_review.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print(amplitude)
    for r in observations:print(r['status'],r['direction_deg'],r['shift_xy'],r.get('explained_fraction'))


if __name__=='__main__':main()
