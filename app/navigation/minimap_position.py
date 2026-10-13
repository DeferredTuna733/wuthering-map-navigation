"""Anchor-local optical-flow position candidate. No screen capture or inputs."""
import cv2
import numpy as np
from app.navigation.moving_scan import sector


def track_position(reference,frame,circle,reference_angle,current_angle,anchor_xy,map_affine,zoom=6):
    shape=reference.shape[:2]
    result=dict(status='local_tracking_unresolved',coordinate_xy=None,navigation_approved=False)
    if frame.shape!=reference.shape:return result
    center=np.asarray(circle.get('player_center_xy',circle['center_xy']),np.float32)
    yy,xx=np.indices(shape);r=np.hypot(xx-center[0],yy-center[1])
    mask=(r>.3*circle['radius'])&(r<.85*circle['radius'])
    mask &= ~sector(shape,center,circle['radius'],reference_angle)
    mask &= ~sector(shape,center,circle['radius'],current_angle)
    gray=cv2.cvtColor(reference,cv2.COLOR_BGR2GRAY)
    target=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
    points=cv2.goodFeaturesToTrack(gray,maxCorners=160,qualityLevel=.015,minDistance=4,mask=mask.astype(np.uint8)*255)
    if points is None or len(points)<12:return result
    forward,ok,_=cv2.calcOpticalFlowPyrLK(gray,target,points,None,winSize=(21,21),maxLevel=2)
    if forward is None:return result
    backward,back_ok,_=cv2.calcOpticalFlowPyrLK(target,gray,forward,None,winSize=(21,21),maxLevel=2)
    if backward is None:return result
    good=ok.reshape(-1).astype(bool)&back_ok.reshape(-1).astype(bool)&(np.linalg.norm(backward-points,axis=2).reshape(-1)<.8)
    src=points.reshape(-1,2)[good];dst=forward.reshape(-1,2)[good]
    if len(src)<12:return dict(result,tracked_features=len(src))
    affine,inliers=cv2.estimateAffinePartial2D(src,dst,method=cv2.RANSAC,ransacReprojThreshold=1)
    if affine is None:return result
    supported=inliers.reshape(-1).astype(bool)
    scale=float(np.linalg.norm(affine[:,0]));rotation=float(np.degrees(np.arctan2(affine[1,0],affine[0,0])))
    residual=np.linalg.norm(src@affine[:,:2].T+affine[:,2]-dst,axis=1)
    result.update(tracked_features=len(src),inliers=int(supported.sum()),inlier_ratio=float(supported.mean()),
                  scale=scale,rotation_deg=rotation,median_error_pixels=float(np.median(residual[supported])))
    if supported.sum()<12 or supported.mean()<.8 or not .98<=scale<=1.02 or abs(rotation)>2:return result
    mapped_center=cv2.invertAffineTransform(affine)@np.r_[center,1]
    displacement=mapped_center-center
    if np.linalg.norm(displacement)>12:return dict(result,status='local_tracking_range_exceeded')
    units_per_pixel=5950/(256*2**zoom)
    coordinate=np.asarray(anchor_xy)+np.asarray(map_affine)[:,:2]@displacement*units_per_pixel
    return dict(result,status='local_position_candidate',coordinate_xy=coordinate.tolist(),
                anchor_displacement_pixels=displacement.tolist(),
                reference_to_current_affine=affine.tolist())


class RollingPositionTracker:
    """Chain accepted frames with a bounded distance without external validation."""
    def __init__(self, image, circle, angle, xy, affine, zoom=6, max_unverified_travel=30):
        self.image=image.copy()
        self.circle=circle
        self.angle=angle
        self.xy=np.asarray(xy,dtype=float)
        self.affine=np.asarray(affine,dtype=float)
        self.zoom=zoom
        self.travel=0.
        self.limit=max_unverified_travel
        self.last_time=None
        self.blocked=False
        self.updates=0
        self.relocalizations=0

    def restore(self, frame, angle, timestamp, registration):
        if registration.get('status')!='terrain_relocalized':return False
        xy=np.asarray(registration['coordinate_xy'],dtype=float)
        affine=np.asarray(registration['affine'],dtype=float)
        if (frame.shape!=self.image.shape or angle is None or not np.isfinite(angle)
                or not np.isfinite(timestamp) or xy.shape!=(2,) or affine.shape!=(2,3)
                or not np.isfinite(xy).all() or not np.isfinite(affine).all()
                or abs(np.linalg.det(affine[:,:2]))<1e-8):return False
        self.image=frame.copy()
        self.angle=angle
        self.xy=xy
        self.affine=affine
        self.last_time=timestamp
        self.travel=0.
        self.blocked=False
        self.relocalizations+=1
        return True

    def observe(self, frame, angle, timestamp):
        empty=dict(coordinate_xy=None,navigation_approved=False,reference_updates=self.updates)
        if self.blocked:return dict(empty,status='relocalization_required')
        if angle is None:return dict(empty,status='heading_unresolved')
        if self.last_time is not None and not 0<timestamp-self.last_time<=2:
            self.blocked=True
            return dict(empty,status='tracking_time_gap')
        result=track_position(self.image,frame,self.circle,self.angle,angle,self.xy,self.affine,self.zoom)
        if result['coordinate_xy'] is None:
            self.blocked=True
            return dict(result,reference_updates=self.updates)
        xy=np.asarray(result['coordinate_xy'])
        travel=self.travel+float(np.linalg.norm(xy-self.xy))
        if travel>self.limit:
            self.blocked=True
            return dict(empty,status='unverified_travel_exceeded',unverified_travel=travel)
        # New image pixels -> previous image pixels -> atlas pixels.
        step=np.asarray(result['reference_to_current_affine'])
        inverse=cv2.invertAffineTransform(step)
        self.affine=np.column_stack((self.affine[:,:2]@inverse[:,:2],np.zeros(2)))
        self.xy=xy
        self.image=frame.copy()
        self.angle=angle
        self.last_time=timestamp
        self.travel=travel
        self.updates+=1
        return dict(result,status='rolling_position_candidate',reference_updates=self.updates,
                    unverified_travel=self.travel)

    def corroborate(self, coordinate, capture_time, tolerance=4):
        """Close-in-time OCR can corroborate, never silently overwrite the position."""
        if (self.blocked or self.last_time is None or coordinate is None
                or abs(capture_time-self.last_time)>.3):return False
        if not np.isfinite(coordinate[:2]).all():return False
        if np.linalg.norm(np.asarray(coordinate[:2])-self.xy)>tolerance:return False
        self.travel=0.
        return True
