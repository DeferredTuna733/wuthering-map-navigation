"""Experimental background/overlay separation, offline diagnostics only."""
import math
import cv2
import numpy as np


def sector(shape,center,radius,angle):
    yy,xx=np.indices(shape);dx=xx-center[0];dy=yy-center[1]
    direction=np.degrees(np.arctan2(dy,dx))%360
    return (np.abs((direction-angle+180)%360-180)<33)&(np.hypot(dx,dy)<radius*.94)


def build_background(frames,angles,center,radius):
    """Fit the additive overlay from pixels covered and uncovered in reference.

    This is an approximation, not an asserted physical rendering model.
    """
    if len(frames)!=len(angles) or len(frames)<8 or any(a is None for a in angles):
        raise ValueError('A complete stationary heading reference is required')
    gray=np.asarray([cv2.cvtColor(f,cv2.COLOR_BGR2GRAY).astype(np.float32) for f in frames])
    masks=np.asarray([sector(gray.shape[1:],center,radius,a) for a in angles])
    covered=masks.sum(axis=0);uncovered=len(masks)-covered
    on=(gray*masks).sum(axis=0)/np.maximum(covered,1)
    off=(gray*(~masks)).sum(axis=0)/np.maximum(uncovered,1)
    yy,xx=np.indices(gray.shape[1:]);distance=np.hypot(xx-center[0],yy-center[1])
    usable=(covered>=4)&(uncovered>=4)&(distance>.3*radius)&(distance<.82*radius)
    if usable.sum()<100:raise ValueError('Reference has insufficient changed overlay pixels')
    amplitude=float(np.median((on-off)[usable]))
    if not 3<=amplitude<=60:raise ValueError('Overlay contrast unresolved')
    background=np.median(gray-amplitude*masks,axis=0).astype(np.float32)
    return background,amplitude


def estimate_moving_heading(reference,background,frame,center,radius,limit=4):
    """Translate the background only; keep each candidate overlay screen anchored."""
    yy,xx=np.indices(background.shape);distance=np.hypot(xx-center[0],yy-center[1])
    ring=(distance>.25*radius)&(distance<.85*radius)
    gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY).astype(np.float32)
    previous=cv2.cvtColor(reference,cv2.COLOR_BGR2GRAY).astype(np.float32)
    window=cv2.createHanningWindow((gray.shape[1],gray.shape[0]),cv2.CV_32F)
    shift,response=cv2.phaseCorrelate(cv2.Laplacian(previous,cv2.CV_32F)*ring,
                                    cv2.Laplacian(gray,cv2.CV_32F)*ring,window)
    result={'status':'unresolved','direction_deg':None,'shift_xy':list(shift),
            'alignment_response':response,'navigation_approved':False,'confidence_calibrated':False}
    if response<.3 or math.hypot(*shift)>limit:return dict(result,status='map_alignment_failed')
    # A phase peak alone is not enough: check texture agreement after alignment.
    aligned_reference=cv2.warpAffine(previous,np.float32([[1,0,shift[0]],[0,1,shift[1]]]),
        (gray.shape[1],gray.shape[0]),borderMode=cv2.BORDER_REFLECT)
    texture_a=cv2.Laplacian(aligned_reference,cv2.CV_32F)[ring]
    texture_b=cv2.Laplacian(gray,cv2.CV_32F)[ring]
    similarity=float(np.dot(texture_a,texture_b)/max(float(np.linalg.norm(texture_a)*np.linalg.norm(texture_b)),1))
    result['aligned_texture_similarity']=similarity
    if similarity<.65:return dict(result,status='map_alignment_failed')
    aligned=cv2.warpAffine(background,np.float32([[1,0,shift[0]],[0,1,shift[1]]]),
        (gray.shape[1],gray.shape[0]),borderMode=cv2.BORDER_REFLECT)
    sample=(distance>.30*radius)&(distance<.82*radius)
    difference=gray-aligned
    difference-=float(np.median(difference[sample]))
    observed=difference[sample];energy=float(np.dot(observed,observed))
    hypotheses=[]
    for angle in range(0,360,3):
        mask=sector(gray.shape,center,radius,angle)[sample].astype(np.float32)
        amplitude=float(np.clip(np.dot(observed,mask)/max(mask.sum(),1),0,60))
        residual=observed-amplitude*mask
        cost=float(np.dot(residual,residual))
        hypotheses.append((cost,angle,amplitude))
    hypotheses.sort();cost,angle,amplitude=hypotheses[0]
    competitor=min(c for c,a,_ in hypotheses if abs((a-angle+180)%360-180)>15)
    explained=1-cost/max(energy,1)
    result.update(explained_fraction=explained,overlay_amplitude=amplitude,
                  competitor_cost_ratio=competitor/max(cost,1))
    if amplitude<3 or explained<.55 or competitor<cost*1.2:return result
    return dict(result,status='separated_candidate',direction_deg=angle)
