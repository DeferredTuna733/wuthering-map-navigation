"""Estimate stationary map backgrounds from diverse views, without labels."""
import math
import cv2
import numpy as np
from app.navigation.moving_scan import estimate_moving_heading


def build_sweep_background(frames,center,radius):
    if len(frames)<8 or any(f.shape!=frames[0].shape for f in frames):
        raise ValueError('At least eight same-sized sweep images are required')
    gray=np.asarray([cv2.cvtColor(f,cv2.COLOR_BGR2GRAY).astype(np.float32) for f in frames])
    yy,xx=np.indices(gray.shape[1:]);distance=np.hypot(xx-center[0],yy-center[1])
    ring=(distance>.25*radius)&(distance<.85*radius)
    window=cv2.createHanningWindow((gray.shape[2],gray.shape[1]),cv2.CV_32F)
    edge=cv2.Laplacian(gray[0],cv2.CV_32F)*ring;alignments=[]
    for image in gray:
        shift,response=cv2.phaseCorrelate(edge.copy(),cv2.Laplacian(image,cv2.CV_32F)*ring,window.copy())
        alignments.append({'shift_xy':list(shift),'response':response})
        if response<.3 or math.hypot(*shift)>2:raise ValueError('Sweep map background moved or cannot be aligned')
    background=np.median(gray,axis=0).astype(np.float32)
    observations=[estimate_moving_heading(frames[0],background,f,center,radius) for f in frames]
    angles=[r['direction_deg'] for r in observations if r['direction_deg'] is not None]
    # A usable background does not imply every view is readable. Require six
    # distinct directions plus angular coverage; unreadable views stay unknown.
    if len(angles)<max(6,math.ceil(len(frames)*.7)) or len(set(angles))<6:
        raise ValueError('Insufficient distinct resolved view directions')
    ordered=sorted(set(angles));gaps=[(b-a)%360 for a,b in zip(ordered,ordered[1:]+ordered[:1])]
    if max(gaps)>120:raise ValueError('Sweep does not cover enough directions for a clean background')
    return background,{'status':'sweep_background_candidate','alignment':alignments,
        'observations':observations,'maximum_direction_gap_deg':max(gaps),
        'navigation_approved':False,'confidence_calibrated':False}
