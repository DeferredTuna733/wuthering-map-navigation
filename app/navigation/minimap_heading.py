import json
from app import project_paths as paths
MINIMAP_REGION_FILE=paths.ROOT/'config/navigation/minimap_region.json'
def resolve_minimap_region(monitors):
 if not MINIMAP_REGION_FILE.exists(): raise ValueError('尚未设置小地图区域，请运行设置小地图区域.bat')
 data=json.loads(MINIMAP_REGION_FILE.read_text(encoding='utf-8-sig'))
 region=data.get('region')
 if data.get('schema')!=1 or not isinstance(region,dict):raise ValueError('小地图区域配置无效')
 circle=data.get('circle') or {'center_xy':[region['width']/2,region['height']/2],'radius':min(region['width'],region['height'])/2}
 if not isinstance(circle,dict) or len(circle.get('center_xy',[]))!=2 or circle.get('radius',0)<=10:raise ValueError('小地图圆形参数无效')
 return region,circle
from dataclasses import dataclass, asdict
import math
from pathlib import Path
import cv2
import numpy as np

@dataclass(frozen=True)
class HeadingObservation:
    angle_deg: float | None
    confidence: float
    center_xy: tuple[float,float]
    radius: float
    peak_score: float
    background_score: float
    reason: str


def _angle_distance(a,b):
    return abs((a-b+180)%360-180)


def _detect_sector_edges(bgr, center, radius, thresholds=(25,60), weak_fallback=True):
    """Find two long radial boundaries; never use the reference's labeled angle.

    The user annotation established a roughly 65-degree transparent sector.
    Its boundaries extend towards the rim, unlike the small white map icons.
    Accept a wider aperture range for sampling/line localization error.
    """
    cx,cy=center
    gray=cv2.cvtColor(bgr,cv2.COLOR_BGR2GRAY)
    yy,xx=np.indices(gray.shape)
    distance=np.hypot(xx-cx,yy-cy)
    edges=cv2.Canny(gray,*thresholds)
    edges[(distance<radius*.23)|(distance>radius*.90)]=0
    lines=cv2.HoughLinesP(edges,1,np.pi/720,max(8,round(radius*.15)),
                          minLineLength=radius*.42,maxLineGap=radius*.08)
    rays=[]
    if lines is not None:
        for x1,y1,x2,y2 in lines[:,0]:
            dx,dy=float(x2-x1),float(y2-y1)
            length=math.hypot(dx,dy)
            offset=abs(dx*(cy-y1)-dy*(cx-x1))/max(length,1)
            mx,my=(x1+x2)/2-cx,(y1+y2)/2-cy
            # Both endpoints must lie on the same ray, not a line through the disk.
            same_ray=(x1-cx)*(x2-cx)+(y1-cy)*(y2-cy)>0
            if offset<radius*.08 and math.hypot(mx,my)>radius*.25 and same_ray:
                rays.append((math.degrees(math.atan2(my,mx))%360,length,offset))
    pairs=[]
    for index,(angle,length,offset) in enumerate(rays):
        for other,other_length,other_offset in rays[index+1:]:
            difference=(other-angle+180)%360-180
            if 50<abs(difference)<85:
                score=min(length,other_length)-offset-other_offset
                pairs.append((score,(angle+difference/2)%360))
    pairs.sort(reverse=True)
    if not pairs or pairs[0][0]<radius*.40:
        if weak_fallback:
            observations=[_detect_sector_edges(bgr,center,radius,t,False)
                          for t in ((10,25),(15,35),(20,45))]
            valid=[o for o in observations if o.angle_deg is not None]
            # Weak edges need agreement across thresholds, without conflicting
            # candidates. Merely lowering Canny thresholds exposes map roads.
            if (len(valid)>=2 and all(o.reason!='scan_ambiguous' for o in observations)
                    and all(_angle_distance(o.angle_deg,valid[0].angle_deg)<12 for o in valid)):
                vector=sum(np.array([math.cos(math.radians(o.angle_deg)),
                                     math.sin(math.radians(o.angle_deg))]) for o in valid)
                angle=math.degrees(math.atan2(vector[1],vector[0]))%360
                return HeadingObservation(angle,min(o.confidence for o in valid)*.8,
                    (cx,cy),float(radius),max(o.peak_score for o in valid),0,'weak_boundary_consensus')
            if any(o.reason=='scan_ambiguous' for o in observations):
                return HeadingObservation(None,0,(cx,cy),float(radius),0,0,'scan_ambiguous')
        return HeadingObservation(None,0,(cx,cy),float(radius),0,0,'scan_not_found')
    score,angle=pairs[0]
    competing=max((s for s,a in pairs if _angle_distance(a,angle)>20),default=0)
    if competing>score*.80:
        return HeadingObservation(None,0,(cx,cy),float(radius),score,competing,'scan_ambiguous')
    # Geometric evidence strength, not a probability of correctness.
    confidence=min(.85,score/radius)*(1-competing/max(score,1))
    return HeadingObservation(angle,confidence,(cx,cy),float(radius),score,competing,'boundary_pair')


def detect_scan_heading(image, center=None, radius=None, *, bins=72):
    """Return image-space angle: 0=right, 90=down, 180=left, 270=up.
    Detect broad bright sectors or paired radial edges of a transparent sector.
    Exclude the center/player glyph; do not inspect the yellow arrow direction.
    """
    if image is None or not hasattr(image,'shape') or image.ndim not in (2,3):
        return HeadingObservation(None,0,(0,0),0,0,0,'invalid_image')
    h,w=image.shape[:2]
    if h<20 or w<20:return HeadingObservation(None,0,(0,0),0,0,0,'image_too_small')
    if center is None:center=(w*.42,h*.47)
    cx,cy=map(float,center)
    if radius is None:radius=min(w,h)*.42
    if radius<=10 or not (0<=cx<w and 0<=cy<h):return HeadingObservation(None,0,(cx,cy),float(radius),0,0,'invalid_geometry')
    if image.ndim == 3 and image.shape[2] == 4:
        bgr = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    elif image.ndim == 3 and image.shape[2] == 3:
        bgr = image
    else:
        bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    # A scan is a broad sector spanning several radii, not an isolated white icon.
    # Bright-pixel peaks alone cannot distinguish map markers from the scan overlay.
    angles=np.arange(bins,dtype=float)*360/bins
    radii=np.linspace(radius*.30,radius*.82,32)
    radians=np.deg2rad(angles)
    map_x=(cx+np.cos(radians)[:,None]*radii).astype(np.float32)
    map_y=(cy+np.sin(radians)[:,None]*radii).astype(np.float32)
    hsv=cv2.cvtColor(bgr,cv2.COLOR_BGR2HSV).astype(np.float32)
    polar=cv2.remap(hsv,map_x,map_y,cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_CONSTANT,borderValue=(0,255,0))
    neutral=(polar[:,:,1]<65)&(polar[:,:,2]>150)
    # Require radial coverage independently in the inner and outer half.
    coverage=np.minimum(neutral[:,:16].mean(axis=1),neutral[:,16:].mean(axis=1))
    supported=coverage>=.60
    step=360/bins
    runs=[]
    for i in range(bins):
        if supported[i] and not supported[(i-1)%bins]:
            length=0
            while length<bins and supported[(i+length)%bins]:length+=1
            runs.append((i,length))
    candidates=[(i,n) for i,n in runs if 30<=n*step<=140]
    peak=float(coverage.max())
    background=float(np.median(coverage))
    if len(candidates)!=1:
        return _detect_sector_edges(bgr,(cx,cy),radius)
    first,length=candidates[0]
    indices=(first+np.arange(length))%bins
    # Both edges must separate the sector from its immediate surroundings.
    flank_count=max(2,int(15/step))
    left=(first-np.arange(1,flank_count+1))%bins
    right=(first+length+np.arange(flank_count))%bins
    inside=float(np.median(coverage[indices]))
    outside=max(float(np.mean(coverage[left])),float(np.mean(coverage[right])))
    contrast=inside-outside
    if contrast<.35:
        return _detect_sector_edges(bgr,(cx,cy),radius)
    # Use sector boundaries, not its brightest internal feature, for direction.
    angle=((first+(length-1)/2)*step)%360
    confidence=min(1.,inside*contrast)
    return HeadingObservation(angle,confidence,(cx,cy),float(radius),peak,background,'ok')


def observation_dict(observation):return asdict(observation)
