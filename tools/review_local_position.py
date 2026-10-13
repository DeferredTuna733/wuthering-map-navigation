"""Local tracker replay with calibration from successful atlas registration."""
import json
import math
import cv2
from app import project_paths as paths
from app.navigation.minimap_position import track_position


def main():
    root=paths.ROOT/'outputs/navigation/geometry_review/current_relocalization'
    registrations=json.loads((root/'report.json').read_text())['samples']
    anchor=next(r for r in registrations if r['status']=='terrain_registration_candidate' and r['seed_offset']==[0,0])
    folder=paths.ROOT/'outputs/navigation/ai_single_point_tests/20261012_004118_558666'
    evidence=json.loads((folder/'report.json').read_text())['evidence']
    reference=cv2.imread(str(folder/anchor['frame']))
    index=int(anchor['frame'][8:11]);angle=evidence[index]['direction_deg']
    config=json.loads((paths.ROOT/'config/navigation/scan_capture_station.json').read_text())
    calibration=json.loads((paths.ROOT/'config/navigation/ai_sector_geometry.json').read_text())
    circle=dict(config['circle'],player_center_xy=calibration['player_center_xy'])
    rows=[]
    for r in registrations:
        if r['seed_offset']!=[0,0]:continue
        n=int(r['frame'][8:11])
        row=track_position(reference,cv2.imread(str(folder/r['frame'])),circle,angle,evidence[n]['direction_deg'],
                           anchor['mapped_game_xy'],anchor['affine'])
        row.update(frame=r['frame'],reference_coordinate=r['reference_coordinate'])
        if row['coordinate_xy'] is not None:row['error_vs_last_ocr']=math.dist(row['coordinate_xy'],r['reference_coordinate'][:2])
        rows.append(row);print(row,flush=True)
    (root/'local_tracking.json').write_text(json.dumps(dict(scope='Development replay, asynchronous OCR references, one atlas anchor; not independent accuracy',samples=rows),ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
