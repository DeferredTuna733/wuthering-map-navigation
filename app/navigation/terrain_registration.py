"""Coordinate-seeded local atlas registration. Screenshot-only candidates."""
import cv2
import numpy as np
from app.map_editor.map_assets import candidate_game_to_pixel_xy,candidate_pixel_to_game_xy


def register(frame,coordinate,circle,atlas,meta):
    px,py=candidate_game_to_pixel_xy(*coordinate[:2],meta['z'],meta['origin_tile'])
    x0=max(0,int(px)-200);y0=max(0,int(py)-200)
    result=dict(scope='Coordinate-seeded offline terrain matching; not a heading or background brightness model',navigation_approved=False,coordinate=coordinate)
    if not 0<=px<atlas.shape[1] or not 0<=py<atlas.shape[0]:
        return dict(result,status='coordinate_outside_local_atlas'),None
    patch=atlas[y0:min(atlas.shape[0],int(py)+200),x0:min(atlas.shape[1],int(px)+200)]
    yy,xx=np.indices(frame.shape[:2]);distance=np.hypot(xx-circle['center_xy'][0],yy-circle['center_xy'][1])
    mask=((distance>.30*circle['radius'])&(distance<.85*circle['radius'])).astype(np.uint8)*255
    image=cv2.resize(frame,None,fx=3,fy=3,interpolation=cv2.INTER_CUBIC)
    mask=cv2.resize(mask,(image.shape[1],image.shape[0]),interpolation=cv2.INTER_NEAREST)
    sift=cv2.SIFT_create(nfeatures=3000)
    k1,d1=sift.detectAndCompute(cv2.cvtColor(image,cv2.COLOR_BGR2GRAY),mask)
    k2,d2=sift.detectAndCompute(cv2.cvtColor(patch,cv2.COLOR_BGR2GRAY),None)
    matches=[]
    if d1 is not None and d2 is not None:
        pairs=cv2.BFMatcher().knnMatch(d1,d2,k=2)
        used=set()
        for pair in sorted(pairs,key=lambda p:p[0].distance):
            if len(pair)==2 and pair[0].distance<.7*pair[1].distance and pair[0].trainIdx not in used:
                matches.append(pair[0]);used.add(pair[0].trainIdx)
    result.update(minimap_features=len(k1),map_features=len(k2),matches=len(matches),status='insufficient_terrain_matches')
    if len(matches)>=12:
        src=np.float32([k1[m.queryIdx].pt for m in matches])/3
        dst=np.float32([k2[m.trainIdx].pt for m in matches])
        train=np.arange(len(matches))%3!=0
        affine,inliers=cv2.estimateAffinePartial2D(src[train],dst[train],method=cv2.RANSAC,ransacReprojThreshold=2)
        if affine is not None:
            errors=np.linalg.norm(src@affine[:,:2].T+affine[:,2]-dst,axis=1)
            heldout=errors[~train];supported=int(np.count_nonzero(heldout<=2))
            mapped=affine[:,:2]@np.asarray(circle.get('player_center_xy',circle['center_xy']))+affine[:,2]+[x0,y0]
            seed_error=float(np.linalg.norm(mapped-[px,py]))
            result.update(affine=affine.tolist(),heldout_supported=supported,heldout_total=len(heldout),coordinate_seed_error_map_pixels=seed_error)
            result['mapped_game_xy']=list(candidate_pixel_to_game_xy(*mapped,meta['z'],meta['origin_tile']))
            result['status']='terrain_registration_candidate' if supported>=4 and seed_error<=25 else 'terrain_registration_rejected'
    return result,patch

