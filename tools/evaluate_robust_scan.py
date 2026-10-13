"""Development regression, including previously human-labeled movement frames."""
import json
from pathlib import Path
import cv2
import numpy as np
from app import project_paths as paths
from app.navigation.robust_scan import estimate_robust_heading
from tools.scan_labeler import DATA
from tools.evaluate_scan_labels import polygon_heading


def main():
    records=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'));models={};rows=[]
    for record in records:
        kind=record.get('sample_kind')
        if kind=='hotkey_capture':
            model_folder=paths.ROOT/'outputs/navigation/sweep_backgrounds'/record['group']
        elif kind=='background_step':
            report_folder=Path(record['source']).parent
            report=json.loads((report_folder/'report.json').read_text(encoding='utf-8'))
            model_folder=Path(report['reference_report']).parent
        else:continue
        if not (model_folder/'report.json').exists() or record['status']!='labeled':continue
        if str(model_folder) not in models:
            models[str(model_folder)]=(np.load(model_folder/'background.npy',allow_pickle=False),cv2.imread(str(model_folder/'reference.png')))
        background,reference=models[str(model_folder)];circle=record['circle']
        frame=cv2.imread(str(DATA/'images'/(record['id']+'.png')))
        label=json.loads((DATA/'annotations'/(record['id']+'.json')).read_text(encoding='utf-8'))
        heading,_=polygon_heading(label['polygon_xy'],circle['center_xy'])
        result=estimate_robust_heading(reference,background,frame,circle['center_xy'],circle['radius'])
        angle=result['direction_deg']
        rows.append({'id':record['id'],'group':record['group'],'kind':kind,'human_direction_deg':heading,
            'candidate_direction_deg':angle,'status':result['status'],
            'error_deg':None if angle is None else abs((angle-heading+180)%360-180)})
    summary={}
    for group in sorted(set(r['group'] for r in rows)):
        selected=[r for r in rows if r['group']==group];errors=[r['error_deg'] for r in selected if r['error_deg'] is not None]
        summary[group]={'accepted':len(errors),'total':len(selected),
            'mean_error_deg':sum(errors)/len(errors) if errors else None,'maximum_error_deg':max(errors,default=None)}
    result={'scope':'Development regression; sweep images contributed to backgrounds. Not independent-scene validation.',
            'navigation_approved':False,'live_matching_changed':False,'summary':summary,'samples':rows}
    target=paths.ROOT/'outputs/navigation/geometry_review/robust_regression.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary))


if __name__=='__main__':main()
