"""Experimental radial consensus on aligned background residuals."""
import cv2
import numpy as np
from app.navigation.moving_scan import estimate_moving_heading


def fit_profile(profile, aperture_deg=66):
    angles=np.arange(360)
    templates=(np.abs((angles[None,:]-angles[:,None]+180)%360-180)<aperture_deg/2).astype(np.float32)
    profile=profile-float(np.median(profile))
    energy=float(np.dot(profile,profile));norm=templates.sum(axis=1)
    dot=templates@profile;amplitudes=np.clip(dot/norm,0,60)
    costs=energy-2*amplitudes*dot+amplitudes**2*norm
    angle=int(np.argmin(costs));cost=float(costs[angle])
    competitors=np.abs((angles-angle+180)%360-180)>15
    ratio=float(costs[competitors].min())/max(cost,1)
    return {'direction_deg':angle,'amplitude':float(amplitudes[angle]),
            'explained_fraction':1-cost/max(energy,1),'competitor_cost_ratio':ratio}


def estimate_robust_heading(reference,background,frame,center,radius,alignment_limit=4):
    alignment=estimate_moving_heading(reference,background,frame,center,radius,limit=alignment_limit)
    result={'status':'unresolved','direction_deg':None,'alignment':alignment,
            'navigation_approved':False,'confidence_calibrated':False}
    if alignment['status']=='map_alignment_failed':return dict(result,status='map_alignment_failed')
    dx,dy=alignment['shift_xy']
    aligned=cv2.warpAffine(background,np.float32([[1,0,dx],[0,1,dy]]),
        (frame.shape[1],frame.shape[0]),borderMode=cv2.BORDER_REFLECT)
    difference=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY).astype(np.float32)-aligned
    angles=np.deg2rad(np.arange(360))[:,None]
    bands=[]
    for low,high in ((.30,.82),(.30,.56),(.56,.82)):
        radii=np.linspace(low*radius,high*radius,40)[None,:]
        polar=cv2.remap(difference,(center[0]+np.cos(angles)*radii).astype(np.float32),
                       (center[1]+np.sin(angles)*radii).astype(np.float32),cv2.INTER_LINEAR)
        bands.append(fit_profile(np.median(polar,axis=1)))
    result['radial_bands']=bands;full=bands[0];angle=full['direction_deg']
    if full['amplitude']<3 or full['explained_fraction']<.70 or full['competitor_cost_ratio']<1.4:return result
    for band in bands[1:]:
        if (band['amplitude']<3 or band['explained_fraction']<.55
                or band['competitor_cost_ratio']<1.2
                or abs((band['direction_deg']-angle+180)%360-180)>6):
            return dict(result,status='radial_conflict')
    if alignment['direction_deg'] is not None and abs((alignment['direction_deg']-angle+180)%360-180)>6:
        return dict(result,status='pixel_profile_conflict')
    return dict(result,status='robust_candidate',direction_deg=angle)
