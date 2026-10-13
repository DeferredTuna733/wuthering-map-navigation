"""Rebuild a local reference from diverse stationary observations, not labels."""
import cv2
import numpy as np
from app.navigation.scan_background import build_sweep_background
from app.navigation.rolling_background import RollingBackground


class LocalBackground:
    def __init__(self, rolling):
        self.rolling=rolling
        self.frames=[]
        self.angles=[]
        self.rebuilds=0

    def observe(self, frame):
        result=self.rolling.observe(frame)
        result['local_background_rebuilt']=False
        if result['direction_deg'] is None:
            self.frames=[];self.angles=[]
            return result
        # Keep distinct views only. Repeating an unchanged view cannot establish
        # a clean map under its translucent sector.
        if self.frames:
            previous=self.frames[-1]
            yy,xx=np.indices(frame.shape[:2])
            ring=(np.hypot(xx-self.rolling.center[0],yy-self.rolling.center[1])<.85*self.rolling.radius)
            a=cv2.Laplacian(cv2.cvtColor(previous,cv2.COLOR_BGR2GRAY).astype(np.float32),cv2.CV_32F)*ring
            b=cv2.Laplacian(cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY).astype(np.float32),cv2.CV_32F)*ring
            shift,response=cv2.phaseCorrelate(a,b)
            if response<.3 or np.hypot(*shift)>2:self.frames=[]
        angle=result['direction_deg']
        if not self.frames or all(abs((angle-a+180)%360-180)>=15 for a in self.angles):
            if not self.frames:self.angles=[]
            self.frames.append(frame.copy());self.angles.append(angle)
        if len(self.frames)>16:
            self.frames.pop(0);self.angles.pop(0)
        if len(self.frames)>=8:
            try:
                background,_=build_sweep_background(self.frames,self.rolling.center,self.rolling.radius)
                # Only a newly observed complete local background can reset the
                # chained-travel budget. Preserve the old model on failure.
                candidate=RollingBackground(self.frames[0],background,self.rolling.center,self.rolling.radius)
                confirmation=candidate.observe(frame)
                if confirmation['direction_deg'] is not None and abs((confirmation['direction_deg']-angle+180)%360-180)<=6:
                    self.rolling=candidate;self.rebuilds+=1
                    self.frames=[];self.angles=[]
                    result['local_background_rebuilt']=True
                    result['local_rebuild_count']=self.rebuilds
            except ValueError:
                pass
        return result
