"""Offline terrain registration against a coordinate-localized map patch."""
import json
from pathlib import Path
import cv2
import numpy as np
from app import project_paths as paths
from app.map_editor.map_assets import candidate_game_to_pixel_xy,candidate_pixel_to_game_xy


from app.navigation.terrain_registration import register

def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('session',type=Path);args=parser.parse_args()
    report=json.loads((args.session/'report.json').read_text(encoding='utf-8'))
    coordinate=report['observations'][0]['coordinate'];circle=report['circle']
    frame=cv2.imread(str(args.session/'frame_000.png'))
    meta=json.loads((paths.ROOT/'data/maps/wuthering_gg/jinzhou_z6.meta.json').read_text(encoding='utf-8'))
    atlas=cv2.imread(str(paths.ROOT/'data/maps/wuthering_gg/jinzhou_z6.png'))
    result,patch=register(frame,coordinate,circle,atlas,meta)
    target=paths.ROOT/'outputs/navigation/geometry_review/minimap_relocalization_review.json'
    target.write_text(json.dumps(result,indent=2),encoding='utf-8')
    if patch is not None:cv2.imwrite(str(target.parent/'relocalization_map_patch.png'),patch)
    print(json.dumps(result))


if __name__=='__main__':main()
