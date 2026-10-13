"""Reproducible screenshot-to-GG registration audit, not game navigation."""
import json
from pathlib import Path
import cv2
import numpy as np

from app.project_paths import ROOT
OUT=ROOT/'data/map_validation/research/registration_z4'
OUT.mkdir(parents=True,exist_ok=True)
base=cv2.imread(str(ROOT/'data/map_validation/research/wuthering_gg/main_z4.png'))
if base is None: raise ValueError('Missing GG reference map')
sift=cv2.SIFT_create(nfeatures=12000)
kp2,des2=sift.detectAndCompute(cv2.cvtColor(base,cv2.COLOR_BGR2GRAY),None)
rows=[]
for path in sorted((ROOT/'data/map_validation/samples').glob('*.json')):
 sample=json.loads(path.read_text(encoding='utf-8-sig'))
 image=cv2.imdecode(np.fromfile(ROOT / sample['image_path'],dtype=np.uint8),cv2.IMREAD_COLOR)
 if image is None: raise ValueError(f'Missing screenshot: {path}')
 # Mask fixed UI panels rather than crop coordinates or use resized chat image.
 gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
 h,w=gray.shape
 mask=np.full((h,w),255,np.uint8)
 mask[:int(h*.12),:]=0
 mask[int(h*.89):,:]=0
 mask[:int(h*.29),:int(w*.29)]=0
 mask[:,int(w*.92):]=0
 kp1,des1=sift.detectAndCompute(gray,mask)
 matches=cv2.BFMatcher().knnMatch(des1,des2,k=2)
 good=[pair[0] for pair in matches if len(pair)==2 and pair[0].distance<.7*pair[1].distance]
 row={'sample':sample['id'],'game_xyz':sample['game_xyz'],'original_size':[w,h],
      'good_matches':len(good),'reference_zoom':4,'reference_tile_origin':[0,0],
      'status':'insufficient_matches','navigation_approved':False}
 if len(good)>=6:
  src=np.float32([kp1[m.queryIdx].pt for m in good])
  dst=np.float32([kp2[m.trainIdx].pt for m in good])
  affine,inliers=cv2.estimateAffinePartial2D(src,dst,method=cv2.RANSAC,ransacReprojThreshold=3,maxIters=10000,confidence=.999)
  if affine is not None and inliers is not None:
   selected=inliers.ravel().astype(bool)
   predicted=src @ affine[:,:2].T+affine[:,2]
   errors=np.linalg.norm(predicted-dst,axis=1)[selected]
   count=int(selected.sum())
   spread=np.ptp(src[selected],axis=0)
   row.update(affine_original_pixels_to_gg_z4=affine.tolist(),inlier_count=count,
      median_error_gg_z4_pixels=float(np.median(errors)),p95_error_gg_z4_pixels=float(np.percentile(errors,95)),
      inlier_spread_original_pixels=spread.tolist(),scale=float(np.linalg.norm(affine[:,0])),
      status='provisional_requires_visual_and_higher_resolution_check' if count>=15 and min(spread)>150 else 'weak_do_not_use_for_coordinate_fit')
   chosen=[m for m,keep in zip(good,selected) if keep]
   visual=cv2.drawMatches(image,kp1,base,kp2,chosen,None,flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)
   factor=min(1,2200/visual.shape[1])
   visual=cv2.resize(visual,None,fx=factor,fy=factor)
   cv2.imwrite(str(OUT/(sample['id']+'_matches.jpg')),visual)
   row['inlier_pairs']=[{'screenshot_xy':a.tolist(),'gg_z4_xy':b.tolist()} for a,b in zip(src[selected],dst[selected])]
 rows.append(row)
(OUT/'registration_audit.json').write_text(json.dumps({'method':'SIFT ratio + RANSAC partial affine','warning':'Low-resolution matching only; player anchor not measured. Game mapping not fitted.','samples':rows},ensure_ascii=False,indent=2),encoding='utf-8')
for r in rows: print(r['sample'],r.get('inlier_count',0),r['status'],r.get('p95_error_gg_z4_pixels'))
