"""Convert segmentation masks to guarded camera-heading candidates."""
import cv2
import numpy as np
from app.navigation.robust_scan import fit_profile


def mask_heading(mask,center,radius):
    angles=np.deg2rad(np.arange(360))[:,None];bands=[]
    for low,high in ((.30,.82),(.30,.56),(.56,.82)):
        radii=np.linspace(low*radius,high*radius,40)[None,:]
        polar=cv2.remap(mask.astype(np.float32)*18,
            (center[0]+np.cos(angles)*radii).astype(np.float32),
            (center[1]+np.sin(angles)*radii).astype(np.float32),cv2.INTER_LINEAR)
        profile=np.mean(polar,axis=1)
        bands.append(fit_profile(profile,aperture_deg=64))
        if not bands[:-1]:
            occupied=profile>=9
            # Measure opening independently from the fixed-width fitting template.
            runs=[];run=0
            for present in np.r_[occupied,occupied]:
                run=run+1 if present else 0
                runs.append(run)
            opening=min(360,max(runs,default=0))
    result=dict(status='mask_shape_unresolved',direction_deg=None,radial_bands=bands,
                aperture_deg=opening,center_xy=list(center),
                navigation_approved=False,confidence_calibrated=False)
    if not 57<=opening<=73:return dict(result,status='sector_aperture_unresolved')
    full=bands[0]
    if full['amplitude']<3 or full['explained_fraction']<.70 or full['competitor_cost_ratio']<1.4:return result
    for band in bands[1:]:
        if band['amplitude']<3 or band['explained_fraction']<.55 or band['competitor_cost_ratio']<1.2 or abs((band['direction_deg']-full['direction_deg']+180)%360-180)>6:return result
    return dict(result,status='ai_heading_candidate',direction_deg=full['direction_deg'])


def predict_heading(model,frame,circle,device='cpu'):
    anchor=None
    if 'player_center_xy' in circle:
        center=np.asarray(circle['player_center_xy'],dtype=float)
        yy,xx=np.indices(frame.shape[:2])
        hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
        yellow=cv2.inRange(hsv,(18,85,175),(42,255,255))>0
        distance=np.hypot(xx-center[0],yy-center[1])
        yellow&=distance<26
        count=int(np.count_nonzero(yellow))
        nearest=float(distance[yellow].min()) if count else None
        anchor=dict(calibrated_center_xy=center.tolist(),yellow_pixels=count,
                    nearest_yellow_distance_pixels=nearest,
                    supported=count>=25 and nearest<=8 if nearest is not None else False,
                    use='position support only; yellow direction is not camera heading')
        if not anchor['supported']:
            return dict(status='player_anchor_not_supported',direction_deg=None,
                        player_anchor=anchor,navigation_approved=False,confidence_calibrated=False),None
    prediction=model.predict(frame,imgsz=320,conf=.25,iou=.5,device=device,verbose=False,retina_masks=True)[0]
    result=dict(status='sector_not_detected',direction_deg=None,navigation_approved=False,confidence_calibrated=False)
    if prediction.masks is None:return result,None
    candidates=[];evaluated=[]
    for index,tensor in enumerate(prediction.masks.data):
        mask=tensor.cpu().numpy()
        if mask.shape!=frame.shape[:2]:
            mask=cv2.resize(mask,(frame.shape[1],frame.shape[0]),interpolation=cv2.INTER_NEAREST)
        row=mask_heading(mask,circle.get('player_center_xy',circle['center_xy']),circle['radius'])
        row['model_score']=float(prediction.boxes.conf[index].cpu())
        if anchor is not None:row['player_anchor']=anchor
        if row['direction_deg'] is not None and row['model_score']<.7:
            row.update(status='low_model_support',direction_deg=None)
        evaluated.append((row,mask))
        if row['direction_deg'] is not None:candidates.append((row,mask))
    diagnostics=[dict(status=r['status'],model_score=r['model_score'],
                      aperture_deg=r['aperture_deg'],direction_deg=r['direction_deg']) for r,_ in evaluated]
    if len(candidates)==1:
        row,mask=candidates[0]
        return dict(row,detected_sectors=len(evaluated),sector_candidates=diagnostics),mask
    if len(evaluated)==1:
        return evaluated[0]
    # Never choose a top score when two geometrically valid sectors remain.
    return dict(result,status='multiple_sectors_detected' if candidates else 'no_valid_sector',
                detected_sectors=len(evaluated),sector_candidates=diagnostics),None
