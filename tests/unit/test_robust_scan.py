import unittest
import numpy as np
import cv2
from tests.unit import test_moving_scan as fixture
from app.navigation.robust_scan import estimate_robust_heading,fit_profile


class RobustScanTests(unittest.TestCase):
    def setUp(self):self.scene=fixture.MovingScanTests();self.scene.setUp()

    def test_translated_views_without_label_or_prior_angle(self):
        for angle in (300,0,90):
            frame=self.scene.render(self.scene.shifted(-1,3),angle)
            r=estimate_robust_heading(self.scene.frames[-1],self.scene.background,frame,(100,100),100)
            self.assertEqual(r['status'],'robust_candidate')
            self.assertLess(abs((r['direction_deg']-angle+180)%360-180),6)

    def test_no_overlay_or_large_translation_rejected(self):
        for frame in [self.scene.render(self.scene.shifted(-1,3),None),self.scene.render(self.scene.shifted(12,0),300)]:
            r=estimate_robust_heading(self.scene.frames[-1],self.scene.background,frame,(100,100),100)
            self.assertIsNone(r['direction_deg'])

    def test_blank_profile_cannot_supply_positive_evidence(self):
        r=fit_profile(np.zeros(360,dtype=np.float32))
        self.assertEqual(r['amplitude'],0)

    def test_larger_translation_diagnostic_keeps_overlay_screen_anchored(self):
        for shift in ((3,7),(-7,3),(0,-10)):
            for angle in (0,90,235):
                with self.subTest(shift=shift,angle=angle):
                    frame=self.scene.render(self.scene.shifted(*shift),angle)
                    r=estimate_robust_heading(self.scene.frames[-1],self.scene.background,frame,(100,100),100,alignment_limit=12)
                    self.assertEqual(r['status'],'robust_candidate')
                    self.assertLess(abs((r['direction_deg']-angle+180)%360-180),6)
                    self.assertFalse(r['navigation_approved'])

    def test_larger_limit_rejects_missing_overlay_unrelated_map_and_excess_shift(self):
        unrelated=cv2.GaussianBlur(np.random.default_rng(87).integers(20,110,(200,200),dtype=np.uint8),(3,3),0).astype(np.float32)
        frames=(self.scene.render(self.scene.shifted(3,7),None),
                self.scene.render(unrelated,235),self.scene.render(self.scene.shifted(18,0),235))
        for frame in frames:
            r=estimate_robust_heading(self.scene.frames[-1],self.scene.background,frame,(100,100),100,alignment_limit=12)
            self.assertIsNone(r['direction_deg'])

    def test_isolated_marker_and_conflicting_radial_sectors_rejected(self):
        marker=self.scene.render(self.scene.background,None)
        cv2.circle(marker,(100,45),10,(240,240,240),-1)
        yy,xx=np.indices((200,200));distance=np.hypot(xx-100,yy-100)
        from app.navigation.moving_scan import sector
        residual=(sector((200,200),(100,100),100,0)&(distance<56))*18
        residual+=(sector((200,200),(100,100),100,90)&(distance>=56))*18
        conflicting=cv2.cvtColor(np.clip(self.scene.background+residual,0,255).astype(np.uint8),cv2.COLOR_GRAY2BGR)
        for frame in (marker,conflicting):
            r=estimate_robust_heading(self.scene.frames[-1],self.scene.background,frame,(100,100),100)
            self.assertIsNone(r['direction_deg'])
