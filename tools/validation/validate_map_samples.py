import json
from pathlib import Path
import cv2
import numpy as np
from app.map_editor.map_assets import stitch_tiles, candidate_pixel_to_game_xy, candidate_game_to_pixel_xy

from app.project_paths import ROOT
OUT=ROOT/'data/map_validation/research/final_validation'
OUT.mkdir(parents=True,exist_ok=True)
PATCHES={'jinzhou_user_sample_001':(11,27,15,31),
         'huko_user_sample_002':(10,34,14,38),
         'jinzhou_east_island_user_sample_003':(19,24,23,28),
         'origin_station_user_sample_004':(19,24,23,28)}


def run():
    results=[]
    seeds={r['sample']:r['affine_original_pixels_to_gg_z4'] for r in json.loads((ROOT/'data/map_validation/research/registration_z4/registration_audit.json').read_text())['samples']}
    sift=cv2.SIFT_create(nfeatures=16000)
    for path in sorted((ROOT/'data/map_validation/samples').glob('*.json')):
        sample=json.loads(path.read_text(encoding='utf-8-sig'))
        bounds=PATCHES[sample['id']]
        ref,tiles=stitch_tiles(ROOT/'data/map_validation/research/wuthering_gg/tiles_z6',6,bounds)
        ref.save(OUT/(sample['id']+'_base_z6.png'))
        target=cv2.cvtColor(np.asarray(ref),cv2.COLOR_RGB2BGR)
        image=cv2.imdecode(np.fromfile(ROOT / sample['image_path'],np.uint8),cv2.IMREAD_COLOR)
        h,w=image.shape[:2]
        mask=np.full((h,w),255,np.uint8)
        mask[:int(h*.12)]=0;mask[int(h*.89):]=0
        mask[:int(h*.29),:int(w*.29)]=0;mask[:,int(w*.92):]=0
        seed=np.array(seeds[sample['id']],dtype=float)*4
        seed[:,2]-=np.array([bounds[0]*256,bounds[1]*256])
        warped_seed=cv2.warpAffine(image,seed,(1280,1280))
        warped_mask=cv2.warpAffine(mask,seed,(1280,1280),flags=cv2.INTER_NEAREST)
        kp1,d1=sift.detectAndCompute(cv2.cvtColor(warped_seed,cv2.COLOR_BGR2GRAY),warped_mask)
        kp2,d2=sift.detectAndCompute(cv2.cvtColor(target,cv2.COLOR_BGR2GRAY),None)
        pairs=cv2.BFMatcher().knnMatch(d1,d2,k=2)
        candidates_matches=[pair[0] for pair in pairs if len(pair)==2 and pair[0].distance<.7*pair[1].distance]
        # Each reference feature may be used once: reject many-to-one repetition.
        used=set()
        good=[]
        for match in sorted(candidates_matches,key=lambda m:m.distance):
            if match.trainIdx not in used:
                good.append(match)
                used.add(match.trainIdx)
        if len(good)<20:
            raise ValueError(f'Insufficient z6 matches: {sample["id"]}')
        patch_src=np.float32([kp1[m.queryIdx].pt for m in good])
        seed_inverse=cv2.invertAffineTransform(seed)
        src=(patch_src@seed_inverse[:,:2].T+seed_inverse[:,2]).astype(np.float32)
        dst=np.float32([kp2[m.trainIdx].pt for m in good])
        # Train/test split before RANSAC: withheld matches never affect fit.
        train=np.arange(len(good))%3!=0
        affine,inliers=cv2.estimateAffinePartial2D(src[train],dst[train],method=cv2.RANSAC,
              ransacReprojThreshold=3,maxIters=10000,confidence=.999)
        if affine is None: raise ValueError('Registration failed')
        scale=float(np.linalg.norm(affine[:,0]))
        if not .5 < scale < 6:
            raise ValueError(f'Degenerate registration: {sample["id"]} scale={scale}')
        error=np.linalg.norm(src@affine[:,:2].T+affine[:,2]-dst,axis=1)
        tested=~train
        accepted=tested & (error<=3)
        support=error<=3
        if accepted.sum()<6: raise ValueError(f'Not enough withheld support: {sample["id"]} good={len(good)} accepted={accepted.sum()}')
        # Mark centroid is a proxy with explicit uncertainty, NOT an exact anchor.
        hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
        yellow=cv2.inRange(hsv,np.array([18,85,175]),np.array([42,255,255]))
        yellow[:int(h*.3)]=0;yellow[int(h*.88):]=0
        yellow[:,:int(w*.25)]=0;yellow[:,int(w*.85):]=0
        count,labels,stats,centers=cv2.connectedComponentsWithStats(yellow)
        candidates=[]
        for stat,center in zip(stats[1:],centers[1:]):
            x,y,ww,hh,area=stat
            if area>=100 and 15<=ww<=100 and 15<=hh<=100:
                candidates.append((int(area),center.tolist(),[int(x),int(y),int(ww),int(hh)]))
        if not candidates: raise ValueError('Marker not detected')
        # Largest yellow glyph selected, not whichever yields closest game coordinate.
        area,marker,box=max(candidates)
        pixel=affine[:,:2]@marker+affine[:,2]
        mapped=np.array(candidate_pixel_to_game_xy(*pixel,6,(bounds[0],bounds[1])))
        game=np.array(sample['game_xyz'][:2],float)
        expected=np.array(candidate_game_to_pixel_xy(*game,6,(bounds[0],bounds[1])))
        units_per_pixel=5950/(256*2**6)
        bbox_width,bbox_height=box[2:]
        anchor_proxy_radius=.5*np.hypot(bbox_width,bbox_height)*np.linalg.norm(affine[:,0])*units_per_pixel
        # Seam-spanning features support the grid arrangement in sampled regions.
        accepted_dst=dst[support]
        seam_counts=[]
        for axis in (0,1):
            for seam in (256,512,768,1024):
                seam_counts.append({'axis':'x' if axis==0 else 'y','seam_local_px':seam,
                                    'supported_matches_within_24px':int((np.abs(accepted_dst[:,axis]-seam)<24).sum())})
        row={'sample':sample['id'],'game_xyz':sample['game_xyz'],'bounds_z6':list(bounds),
             'train_match_count':int(train.sum()),'train_inlier_count':int(inliers.sum()),
             'withheld_match_count':int(tested.sum()),'withheld_accepted_count':int(accepted.sum()),
             'withheld_accepted_p95_error_z6_px':float(np.percentile(error[accepted],95)),
             'withheld_all_median_error_z6_px':float(np.median(error[tested])),
             'affine_screenshot_to_patch':affine.tolist(),
             'marker_centroid_original_xy':marker,'marker_bbox':box,'marker_method':'largest yellow connected component centroid; not exact anchor',
             'mapped_game_xy_candidate':mapped.tolist(),'game_xy_residual':(mapped-game).tolist(),
             'game_xy_residual_norm':float(np.linalg.norm(mapped-game)),
             'conservative_marker_bbox_radius_game_units':float(anchor_proxy_radius),
             'terrain_withheld_p95_game_units':float(np.percentile(error[accepted],95)*units_per_pixel),
             'navigation_approved':False,'seam_feature_support':seam_counts,'tile_manifest':tiles}
        results.append(row)
        # Render local comparison in game screenshot coordinates; only original game map and official gg image.
        inverse=cv2.invertAffineTransform(affine)
        warped=cv2.warpAffine(target,inverse,(w,h),flags=cv2.INTER_LINEAR)
        valid=cv2.warpAffine(np.full(target.shape[:2],255,np.uint8),inverse,(w,h))>250
        blend=image.copy()
        blend[valid]=(image[valid].astype(float)*.5+warped[valid].astype(float)*.5).astype(np.uint8)
        mx,my=map(int,marker)
        expected_screen=inverse[:,:2]@expected+inverse[:,2]
        cv2.circle(blend,(mx,my),9,(0,255,255),2)
        cv2.drawMarker(blend,tuple(np.round(expected_screen).astype(int)),(255,255,0),cv2.MARKER_CROSS,20,2)
        # Three panes around marker: user screenshot, GG projected terrain, overlay.
        pad=200
        x0,y0=max(0,mx-pad),max(0,my-pad)
        x1,y1=min(w,mx+pad),min(h,my+pad)
        panes=[im[y0:y1,x0:x1] for im in (image,warped,blend)]
        comparison=np.hstack(panes)
        cv2.imwrite(str(OUT/(sample['id']+'_comparison.jpg')),comparison)
    report={'date':'2026-10-09','map':'wuthering.gg main Huanglong map',
            'candidate_relation':'game_xy = gg_site_xy / 10000',
            'fit_policy':'No game-coordinate fit; fixed website geometry, independently checked against all four user samples.',
            'status':'terrain_registration_supported; approximately_3_unit_xy_consistency; exact_anchor_and_subunit_accuracy_not_proven',
            'height_policy':'User-provided z stored only; never inferred from 2D map',
            'samples':results}
    (OUT/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    for r in results:
        print(r['sample'],'withheld',r['withheld_accepted_count'],'p95 pixels',round(r['withheld_accepted_p95_error_z6_px'],3),
              'game residual',round(r['game_xy_residual_norm'],3),'bbox radius',round(r['conservative_marker_bbox_radius_game_units'],3))
    return report

if __name__=='__main__':
    run()

