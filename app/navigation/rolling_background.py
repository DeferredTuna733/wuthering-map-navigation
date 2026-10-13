"""Conservative offline background refresh; never authorizes navigation."""
import cv2
import numpy as np
import json
from pathlib import Path
from app.navigation.moving_scan import sector
from app.navigation.robust_scan import estimate_robust_heading


class RollingBackground:
    def __init__(self, reference, background, center, radius):
        self.reference = reference.copy()
        self.background = background.copy()
        self.center = center
        self.radius = radius
        yy,xx=np.indices(background.shape)
        # Pixels outside the minimap are UI, not transferable map background.
        self.valid = (np.hypot(xx-center[0],yy-center[1]) < .94*radius).astype(np.uint8)
        self.travel = 0.0
        self.updates = 0

    def save(self, folder, provenance):
        folder=Path(folder)
        folder.mkdir(parents=True,exist_ok=False)
        np.save(folder/'background.npy',self.background,allow_pickle=False)
        np.save(folder/'valid.npy',self.valid,allow_pickle=False)
        if not cv2.imwrite(str(folder/'reference.png'),self.reference):
            raise ValueError('Cannot save rolling reference')
        metadata=dict(provenance=provenance,center=self.center,radius=self.radius,
                      travel=self.travel,updates=self.updates,navigation_approved=False)
        (folder/'state.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')

    @classmethod
    def load(cls, folder, provenance, shape, center, radius):
        folder=Path(folder)
        metadata=json.loads((folder/'state.json').read_text(encoding='utf-8'))
        if (metadata['provenance']!=provenance or metadata['center']!=list(center)
                or metadata['radius']!=radius):
            raise ValueError('Rolling reference does not match the selected map model')
        background=np.load(folder/'background.npy',allow_pickle=False)
        valid=np.load(folder/'valid.npy',allow_pickle=False)
        reference=cv2.imread(str(folder/'reference.png'))
        if (background.shape!=tuple(shape) or valid.shape!=tuple(shape)
                or reference is None or reference.shape[:2]!=tuple(shape)
                or not np.isfinite(background).all() or not np.isin(valid,[0,1]).all()
                or not np.isfinite(metadata['travel']) or not 0<=metadata['travel']<=24
                or type(metadata['updates']) is not int or metadata['updates']<0):
            raise ValueError('Invalid rolling reference state')
        result=cls(reference,background,center,radius)
        result.valid=valid.astype(np.uint8)
        result.travel=metadata['travel'];result.updates=metadata['updates']
        return result

    def observe(self, frame):
        result = estimate_robust_heading(self.reference, self.background, frame,
                                        self.center, self.radius, alignment_limit=12)
        result['background_updated'] = False
        if result['direction_deg'] is None:
            return result
        dx, dy = result['alignment']['shift_xy']
        travel = self.travel + float(np.hypot(dx, dy))
        # Bound chained alignment drift until longer trajectories are validated.
        if travel > 24:
            return dict(result, status='refresh_travel_limit', direction_deg=None)
        transform = np.float32([[1, 0, dx], [0, 1, dy]])
        shape = (frame.shape[1], frame.shape[0])
        support = cv2.warpAffine(self.valid.astype(np.float32), transform, shape,
                                flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        # Every source pixel used by interpolation must be known.
        valid = (support>=.999).astype(np.uint8)
        yy, xx = np.indices(self.background.shape)
        distance = np.hypot(xx-self.center[0], yy-self.center[1])
        ring = (distance > .30*self.radius) & (distance < .82*self.radius)
        inherited_coverage=float(np.mean(valid[ring]))
        result['inherited_background_coverage']=inherited_coverage
        if inherited_coverage < .98:
            return dict(result, status='refresh_coverage_failed', direction_deg=None)
        background = cv2.warpAffine(self.background, transform, shape,
                                    borderMode=cv2.BORDER_CONSTANT)
        # Keep inherited background under the white sector. Only refresh pixels
        # visibly outside a generously widened sector; never subtract a guessed
        # brightness from the overlay to invent hidden map content.
        angle = result['direction_deg']
        covered = sector(background.shape, self.center, self.radius, angle)
        covered |= sector(background.shape, self.center, self.radius, (angle-10)%360)
        covered |= sector(background.shape, self.center, self.radius, (angle+10)%360)
        hidden=ring & covered
        hidden_coverage=float(np.mean(valid[hidden]))
        result['hidden_background_coverage']=hidden_coverage
        if hidden_coverage < .98:
            return dict(result,status='hidden_background_unknown',direction_deg=None)
        refresh_ring=(distance>.30*self.radius)&(distance<.90*self.radius)
        refresh = refresh_ring & ~covered
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
        background[refresh] = gray[refresh]
        valid[refresh] = 1
        self.reference = frame.copy()
        self.background = background
        self.valid = valid
        self.travel = travel
        self.updates += 1
        return dict(result, background_updated=True, refresh_travel_pixels=travel,
                    refresh_count=self.updates,
                    refreshed_pixels=int(refresh.sum()),
                    unknown_sample_pixels=int(np.count_nonzero(ring & (valid==0))))
