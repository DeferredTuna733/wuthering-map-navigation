"""Estimate player rotation center independent of game coordinate fitting."""
import json
from pathlib import Path
import cv2
import numpy as np
from app.map_editor.map_assets import candidate_pixel_to_game_xy
from app.project_paths import ROOT
OUT=ROOT/'data/map_validation/research/rotation_validation';OUT.mkdir(parents=True,exist_ok=True)
sample=json.loads((ROOT/'data/map_validation/samples/rotation_qichi/sample.json').read_text())
images=[cv2.imread(str(ROOT / r['image'])) for r in sample['images']]

def glyph(image,roi):
 x0,y0,x1,y1=roi
 hsv=cv2.cvtColor(image[y0:y1,x0:x1],cv2.COLOR_BGR2HSV)
 mask=cv2.inRange(hsv,(18,85,175),(42,255,255))
 n,labels,stats,centers=cv2.connectedComponentsWithStats(mask)
 idx=1+np.argmax(stats[1:,4]); ys,xs=np.where(labels==idx)
 return np.column_stack((xs+x0,ys+y0)).astype(float),mask

p1,_=glyph(images[0],(765,445,835,520));p2,_=glyph(images[1],(765,445,835,520))
# Symmetric nearest-neighbor rigid fit, robust loss; no use of supplied xyz.
step1=p1[::2];step2=p2[::2]
c0=(p1.mean(axis=0)+p2.mean(axis=0))/2
fits=[]
for angle0 in np.linspace(-np.pi,np.pi,25):
 R=np.array([[np.cos(angle0),-np.sin(angle0)],[np.sin(angle0),np.cos(angle0)]])
 translation=c0-R@c0
 for _ in range(60):
  pred=step1@R.T+translation
  distances=np.sum((pred[:,None,:]-step2[None,:,:])**2,axis=2)
  nearest=step2[distances.argmin(axis=1)]
  ca=step1.mean(axis=0);cb=nearest.mean(axis=0)
  U,_,Vt=np.linalg.svd((step1-ca).T@(nearest-cb))
  Rnew=Vt.T@U.T
  if np.linalg.det(Rnew)<0:Vt[-1]*=-1;Rnew=Vt.T@U.T
  tnew=cb-Rnew@ca
  change=np.linalg.norm(Rnew-R)+np.linalg.norm(tnew-translation)
  R,translation=Rnew,tnew
  if change<1e-7:break
 pred=step1@R.T+translation
 d=np.sum((pred[:,None,:]-step2[None,:,:])**2,axis=2)
 score=float(np.sqrt(np.mean(np.r_[d.min(axis=0),d.min(axis=1)])))
 fits.append((score,R,translation))
rot_error,R,translation=min(fits,key=lambda f:f[0])
angle=float(np.arctan2(R[1,0],R[0,0]))
if abs(np.linalg.det(np.eye(2)-R))<.1:raise ValueError('Rotation insufficient for stable anchor')
center=np.linalg.solve(np.eye(2)-R,translation)
# Check unchanging background away from the marker: same map placement is prerequisite.
diff=cv2.absdiff(images[0],images[1]);diff[440:525,760:840]=0
background_median=float(np.median(diff[150:800,400:1400]))
base=cv2.imread(str(ROOT/'data/map_validation/research/wuthering_gg/main_z4.png'))
sift=cv2.SIFT_create(nfeatures=12000);k2,d2=sift.detectAndCompute(cv2.cvtColor(base,cv2.COLOR_BGR2GRAY),None)
rows=[]
for i,image in enumerate(images):
 h,w=image.shape[:2];mask=np.full((h,w),255,np.uint8);mask[:145]=0;mask[820:]=0;mask[:300,:400]=0;mask[:,1480:]=0
 k1,d1=sift.detectAndCompute(cv2.cvtColor(image,cv2.COLOR_BGR2GRAY),mask)
 matches=cv2.BFMatcher().knnMatch(d1,d2,k=2)
 good=[m for m,n in matches if m.distance<.7*n.distance]
 used=set();unique=[]
 for m in sorted(good,key=lambda m:m.distance):
  if m.trainIdx not in used:unique.append(m);used.add(m.trainIdx)
 src=np.float32([k1[m.queryIdx].pt for m in unique]);dst=np.float32([k2[m.trainIdx].pt for m in unique])
 train=np.arange(len(src))%3!=0
 A,inliers=cv2.estimateAffinePartial2D(src[train],dst[train],method=cv2.RANSAC,ransacReprojThreshold=2,maxIters=10000,confidence=.999)
 if A is None:raise ValueError('registration failed')
 scale=np.linalg.norm(A[:,0])
 if not .1<scale<4:raise ValueError('degenerate registration')
 errors=np.linalg.norm(src@A[:,:2].T+A[:,2]-dst,axis=1)
 held=~train;accepted=held&(errors<2)
 if accepted.sum()<10:raise ValueError('insufficient withheld support')
 point=center if i<3 else glyph(image,(915,480,975,550))[0].mean(axis=0)
 pixel=A[:,:2]@point+A[:,2];game=np.array(candidate_pixel_to_game_xy(*pixel,4))
 row={'view':i+1,'anchor_method':'rotation_center' if i<3 else 'yellow_centroid_zoom_check_only',
 'screenshot_anchor_xy':point.tolist(),'gg_z4_xy':pixel.tolist(),'mapped_game_xy':game.tolist(),
 'residual_to_user_game_xy':(game-[-454,444]).tolist(),'residual_norm':float(np.linalg.norm(game-[-454,444])),
 'withheld_total':int(held.sum()),'withheld_accepted':int(accepted.sum()),
 'withheld_accepted_p95_z4_pixels':float(np.percentile(errors[accepted],95)),
 'withheld_all_median_z4_pixels':float(np.median(errors[held])), 'affine':A.tolist()}
 rows.append(row)
 crop=image[430:530,750:850].copy() if i<3 else image[470:560,900:990].copy()
 if i<3:cv2.drawMarker(crop,tuple(np.round(center-[750,430]).astype(int)),(255,255,0),cv2.MARKER_CROSS,12,1)
 cv2.imwrite(str(OUT/f'view_{i+1}_anchor.png'),cv2.resize(crop,None,fx=3,fy=3))
result={'game_xyz':[-454,444,50],'rotation_center_xy':center.tolist(),'rotation_degrees':float(np.degrees(angle)),
 'symmetric_mask_match_rms_original_pixels':rot_error,'background_absolute_difference_median':background_median,
 'warning':'Two distinct orientations only; rigid mask estimate affected by glyph rasterization. Fourth view uses centroid, not exact anchor. No guarantee of subunit or global accuracy.',
 'navigation_approved':False,'samples':rows}
(OUT/'rotation_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print('CENTER',center,'rotation',np.degrees(angle),'mask RMS',rot_error)
for r in rows:print(r['view'],r['mapped_game_xy'],'residual',r['residual_norm'],'withheld',r['withheld_accepted'])
