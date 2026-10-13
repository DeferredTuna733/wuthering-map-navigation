"""Bounded local-atlas recovery. OCR proposals are seeds, never final positions."""
import math
from collections import OrderedDict
import numpy as np
from app.map_editor.map_assets import candidate_game_to_pixel_xy,stitch_tiles
from app.navigation.terrain_registration import register


def ocr_seeds(diagnostics):
    seeds=[]
    for diagnostic in diagnostics:
        for variant in diagnostic.get('variants',[]):
            point=variant.get('coordinate')
            if (point is not None and len(point)==3 and variant.get('confidence',0)>=.8
                    and all(math.isfinite(v) for v in point)
                    and not any(tuple(point[:2])==tuple(old[:2]) for old in seeds)):
                seeds.append(list(point))
    return seeds[:4]


def registration_usable(result, expected_affine):
    if result['status']!='terrain_registration_candidate':return False
    affine=np.asarray(result.get('affine'),dtype=float)
    xy=result.get('mapped_game_xy')
    if affine.shape!=(2,3) or xy is None or not np.isfinite(affine).all() or not np.isfinite(xy).all():return False
    expected=np.asarray(expected_affine,dtype=float)[:,:2]
    relative=affine[:,:2]@np.linalg.inv(expected)
    scale=float(np.linalg.norm(relative[:,0]))
    rotation=math.degrees(math.atan2(relative[1,0],relative[0,0]))
    return (result.get('heldout_supported',0)>=4
            and result.get('heldout_supported',0)/max(1,result.get('heldout_total',0))>=.75
            and .95<=scale<=1.05 and abs(rotation)<=3
            and math.dist(xy,result['coordinate'][:2])<=4)


class TerrainRelocalizer:
    def __init__(self, tile_root, expected_affine):
        self.tile_root=tile_root
        self.expected_affine=expected_affine
        self.cache=OrderedDict()

    def locate(self, frame, circle, seeds):
        rows=[]
        for seed in seeds[:4]:
            px,py=candidate_game_to_pixel_xy(*seed[:2],6)
            tx,ty=int(px//256),int(py//256)
            if not 0<=tx<64 or not 0<=ty<64:
                rows.append(dict(status='outside_cached_map',coordinate=seed));continue
            bounds=(max(0,tx-1),max(0,ty-1),min(63,tx+1),min(63,ty+1))
            try:
                if bounds not in self.cache:
                    image,records=stitch_tiles(self.tile_root,6,bounds)
                    self.cache[bounds]=(np.asarray(image)[:,:,::-1].copy(),records)
                    while len(self.cache)>2:self.cache.popitem(last=False)
                atlas,records=self.cache[bounds]
                result,_=register(frame,seed,circle,atlas,dict(z=6,origin_tile=list(bounds[:2])))
                result.update(tile_bounds=list(bounds),tiles=records,
                              accepted=registration_usable(result,self.expected_affine))
                rows.append(result)
            except (OSError,ValueError) as error:
                rows.append(dict(status='map_unavailable',coordinate=seed,error=str(error)))
        accepted=[r for r in rows if r.get('accepted')]
        output=dict(status='relocalization_unresolved',coordinate_xy=None,attempts=rows,navigation_approved=False)
        if not accepted:return output
        if any(math.dist(a['mapped_game_xy'],b['mapped_game_xy'])>2 for a in accepted for b in accepted):
            return dict(output,status='ambiguous_relocalization')
        chosen=max(accepted,key=lambda r:r['heldout_supported'])
        return dict(output,status='terrain_relocalized',coordinate_xy=chosen['mapped_game_xy'],
                    affine=chosen['affine'],source=chosen)
