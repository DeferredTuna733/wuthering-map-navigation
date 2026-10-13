"""Replay existing captures chronologically; no game input or live updates."""
import json
from pathlib import Path
import cv2
import numpy as np
from app import project_paths as paths
from app.navigation.rolling_background import RollingBackground
from tools.evaluate_scan_labels import polygon_heading


def main():
    base = paths.ROOT/'outputs/navigation/background_heading_checks'
    sessions = sorted(p for p in base.glob('20261011_*') if p.name >= '20261011_192419_304539')
    first = json.loads((sessions[0]/'report.json').read_text(encoding='utf-8'))
    model_path = Path(first['reference_report']).parent
    circle = first['circle']
    model = RollingBackground(cv2.imread(str(model_path/'reference.png')),
        np.load(model_path/'background.npy',allow_pickle=False),circle['center_xy'],circle['radius'])
    rows = []
    for folder in sessions:
        report = json.loads((folder/'report.json').read_text(encoding='utf-8'))
        if report['region'] != first['region'] or report['circle'] != circle:
            continue
        for index in (0,3,7):
            result = model.observe(cv2.imread(str(folder/f'frame_{index:02d}.png')))
            label_path = paths.ROOT/'data/navigation/scan_segmentation/annotations'/f'backgroundcheck_{folder.name}_{index:03d}.json'
            if label_path.exists():
                label = json.loads(label_path.read_text(encoding='utf-8'))
                angle,_ = polygon_heading(label['polygon_xy'],circle['center_xy'])
                result['human_direction_deg'] = angle
                result['error_deg'] = None if result['direction_deg'] is None else abs((result['direction_deg']-angle+180)%360-180)
            result.update(session=folder.name,frame=index)
            rows.append(result)
            print(folder.name,index,result['status'],result['direction_deg'],result.get('error_deg'))
    errors = [r['error_deg'] for r in rows if r.get('error_deg') is not None]
    summary = dict(scope='Existing development captures replay; not independent live validation',
        live_updates_enabled=False,navigation_approved=False,total=len(rows),accepted=len(errors),
        mean_error_deg=sum(errors)/len(errors) if errors else None,maximum_error_deg=max(errors,default=None),observations=rows)
    target = paths.ROOT/'outputs/navigation/geometry_review/rolling_background_review.json'
    target.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print('SUMMARY',len(rows),len(errors),summary['mean_error_deg'],summary['maximum_error_deg'])


if __name__ == '__main__':main()
