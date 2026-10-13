"""Draw independent spatial/temporal predictions on saved images only."""
import json
import math
from pathlib import Path
import cv2
from app import project_paths as paths
from app.navigation.scan_geometry import boundary_evidence,corroborate
from app.navigation.minimap_heading import detect_scan_heading,observation_dict


def main():
    output=paths.ROOT/'outputs/navigation/geometry_review';output.mkdir(parents=True,exist_ok=True)
    inputs=list((paths.ROOT/'data/navigation/scan_segmentation/images').glob('*.png'))
    label=json.loads((paths.ROOT/'config/navigation/scan_reference.json').read_text(encoding='utf-8'))
    inputs.insert(0,Path(label['source_image']))
    results=[]
    for index,source in enumerate(inputs):
        image=cv2.imread(str(source))
        result=boundary_evidence(image,(100,100),100)
        legacy=observation_dict(detect_scan_heading(image,(100,100),100))
        result.update(source=str(source),legacy=legacy)
        result['spatial_consensus']=corroborate(result,legacy['angle_deg'])
        if index==0:
            result['human_direction_deg']=label['annotated_direction_deg']
            angle=result['direction_deg']
            result['human_angle_error_deg']=None if angle is None else abs((angle-label['annotated_direction_deg']+180)%360-180)
        preview=image.copy()
        best=result.get('best_evidence')
        if best:
            for angle in best['boundaries_deg']:
                r=math.radians(angle);end=(round(100+86*math.cos(r)),round(100+86*math.sin(r)))
                cv2.line(preview,(100,100),end,(0,0,255),1)
            angle=math.radians(best['direction_deg'])
            cv2.arrowedLine(preview,(100,100),(round(100+70*math.cos(angle)),round(100+70*math.sin(angle))),(0,255,255),1)
        cv2.putText(preview,result['status'],(5,195),cv2.FONT_HERSHEY_SIMPLEX,.35,(0,0,255),1)
        target=output/f'{index:02d}_{source.stem}.png';cv2.imwrite(str(target),cv2.resize(preview,None,fx=3,fy=3))
        result['preview']=str(target);results.append(result)
    (output/'report.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    for r in results:print(Path(r['source']).name,r['status'],r['direction_deg'],r.get('human_angle_error_deg'))


if __name__=='__main__':main()
