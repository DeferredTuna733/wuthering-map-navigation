"""Reuse cached atlas tiles and existing terrain registration on recent steps."""
import json
import math
from pathlib import Path
import cv2
import numpy as np
from app import project_paths as paths
from app.map_editor.map_assets import stitch_tiles,candidate_game_to_pixel_xy
from tools.review_minimap_relocalization import register


def main():
    folder=paths.ROOT/'outputs/navigation/ai_single_point_tests/20261012_004118_558666'
    report=json.loads((folder/'report.json').read_text())
    config=json.loads((paths.ROOT/'config/navigation/scan_capture_station.json').read_text())
    calibration=json.loads((paths.ROOT/'config/navigation/ai_sector_geometry.json').read_text())
    circle=dict(config['circle'],player_center_xy=calibration['player_center_xy'])
    seed=report['events'][0]['coordinate']
    px,py=candidate_game_to_pixel_xy(*seed[:2],6)
    tx,ty=int(px//256),int(py//256)
    bounds=(max(0,tx-2),max(0,ty-2),min(63,tx+2),min(63,ty+2))
    image,_=stitch_tiles(paths.OFFLINE_TILES/'6',6,bounds)
    atlas=np.asarray(image)[:,:,::-1].copy()
    meta=dict(z=6,origin_tile=[bounds[0],bounds[1]])
    current=None;rows=[]
    for index,item in enumerate(report['evidence']):
        if item['kind']=='coordinate' and item['coordinate'] is not None:current=item['coordinate']
        if item['kind']!='heading' or index not in (4,9,21,31,33):continue
        frame=cv2.imread(str(folder/f'heading_{index:03d}.png'))
        for offset in ((0,0),(100,0),(0,100)):
            chosen=[seed[0]+offset[0],seed[1]+offset[1],seed[2]]
            result,_=register(frame,chosen,circle,atlas,meta)
            result.update(frame=f'heading_{index:03d}.png',seed_offset=offset,reference_coordinate=current,
                          reference_time_note='Last OCR precedes heading; captures not synchronized')
            if result['status']=='terrain_registration_candidate':
                result['error_vs_last_ocr_xy']=math.dist(result['mapped_game_xy'],current[:2])
            rows.append(result)
            print(result['frame'],offset,result['status'],result.get('matches'),result.get('mapped_game_xy'),result.get('error_vs_last_ocr_xy'),flush=True)
    out=paths.ROOT/'outputs/navigation/geometry_review/current_relocalization'
    out.mkdir(exist_ok=True)
    (out/'report.json').write_text(json.dumps(dict(scope='Development replay; OCR references asynchronous, not independent truth',samples=rows,navigation_approved=False),ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
