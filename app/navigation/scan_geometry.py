"""Independent polar boundary evidence; experimental, never a steering source."""
import cv2
import numpy as np


def corroborate(geometry,edge_angle,temporal_angle=None):
    """Require independent spatial agreement, with an optional temporal veto."""
    angle=geometry.get('direction_deg')
    result={'status':'unresolved','direction_deg':None,'confidence_calibrated':False,
            'navigation_approved':False}
    if angle is None or edge_angle is None:return result
    if abs((angle-edge_angle+180)%360-180)>10:
        return dict(result,status='spatial_conflict')
    direction=(edge_angle+((angle-edge_angle+180)%360-180)/2)%360
    if temporal_angle is not None and abs((direction-temporal_angle+180)%360-180)>10:
        return dict(result,status='temporal_conflict')
    return dict(result,status='corroborated_candidate',direction_deg=direction)


def boundary_evidence(image,center,radius):
    """Require a brightening and darkening boundary across several radii.

    Scores describe image evidence, not calibrated correctness probabilities.
    The aperture is searched rather than fixing a labeled direction.
    """
    cx,cy=center
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY).astype(np.float32)
    angles=np.deg2rad(np.arange(360))[:,None]
    radii=np.linspace(radius*.30,radius*.86,48)[None,:]
    polar=cv2.remap(gray,(cx+np.cos(angles)*radii).astype(np.float32),
                    (cy+np.sin(angles)*radii).astype(np.float32),cv2.INTER_LINEAR)
    # Suppress isolated bright markers by requiring support at many radii.
    gradient=(sum(np.roll(polar,-i,axis=0) for i in range(2,6))-
              sum(np.roll(polar,i,axis=0) for i in range(2,6)))/4
    candidates=[]
    for start in range(360):
        for aperture in range(54,79,3):
            end=(start+aperture)%360
            support=np.minimum(gradient[start],-gradient[end])
            coverage=float(np.mean(support>3))
            strength=float(np.median(support))
            if coverage>=.65 and strength>=3:
                candidates.append({'direction_deg':(start+aperture/2)%360,
                    'boundaries_deg':[start,end],'aperture_deg':aperture,
                    'radial_support':coverage,'contrast':strength,'score':coverage*strength})
    candidates.sort(key=lambda c:c['score'],reverse=True)
    result={'status':'not_found','direction_deg':None,'navigation_approved':False,
            'confidence_calibrated':False,'candidates':candidates[:8]}
    if not candidates:return result
    best=candidates[0]
    competitor=max((c['score'] for c in candidates
        if abs((c['direction_deg']-best['direction_deg']+180)%360-180)>15),default=0)
    result['best_evidence']=best;result['competitor_ratio']=competitor/best['score']
    if competitor>=best['score']*.8:
        result['status']='ambiguous';return result
    result.update(status='geometry_candidate',direction_deg=best['direction_deg'])
    return result
