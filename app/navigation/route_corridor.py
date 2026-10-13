"""Polyline geometry in game coordinate units; no game interaction."""
import math


def segment_position(point,start,end):
    dx,dy=end[0]-start[0],end[1]-start[1]
    length=math.hypot(dx,dy)
    if length<=1e-9:
        raise ValueError('路线相邻点不能重合')
    along=((point[0]-start[0])*dx+(point[1]-start[1])*dy)/length
    fraction=max(0,min(1,along/length))
    closest=(start[0]+fraction*dx,start[1]+fraction*dy)
    return dict(along=along,length=length,fraction=fraction,closest=closest,
                cross_track=abs((point[0]-start[0])*dy-(point[1]-start[1])*dx)/length,
                segment_distance=math.dist(point[:2],closest))


def waypoint_reached(point,start,end,terminal=False,width=4):
    """Intermediate points can be passed within the corridor; final point needs proximity."""
    if math.dist(point[:2],end[:2])<=width:return True
    if terminal:return False
    position=segment_position(point,start,end)
    return position['along']>=position['length'] and position['cross_track']<=width
