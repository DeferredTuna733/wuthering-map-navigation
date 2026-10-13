import unittest
import cv2
import numpy as np
from app.navigation.moving_scan import sector,build_background,estimate_moving_heading


class MovingScanTests(unittest.TestCase):
    def setUp(self):
        rng=np.random.default_rng(41)
        self.background=cv2.GaussianBlur(rng.integers(20,110,(200,200),dtype=np.uint8),(3,3),0).astype(np.float32)
        self.angles=[240]*8+list(range(243,301,3))+[300]*8
        self.frames=[self.render(self.background,a) for a in self.angles]

    def render(self,background,angle):
        overlay=0 if angle is None else sector(background.shape,(100,100),100,angle)*18
        return cv2.cvtColor(np.clip(background+overlay,0,255).astype(np.uint8),cv2.COLOR_GRAY2BGR)

    def shifted(self,dx,dy):
        return cv2.warpAffine(self.background,np.float32([[1,0,dx],[0,1,dy]]),(200,200),borderMode=cv2.BORDER_REFLECT)

    def test_background_recovered_without_shifting_overlay(self):
        background,amplitude=build_background(self.frames,self.angles,(100,100),100)
        self.assertAlmostEqual(amplitude,18,delta=.2)
        self.assertLess(np.mean(np.abs(background-self.background)),1)

    def test_translation_with_fixed_and_changed_view(self):
        background,_=build_background(self.frames,self.angles,(100,100),100)
        for angle in (300,315,0,90):
            with self.subTest(angle=angle):
                current=self.render(self.shifted(-1,3),angle)
                result=estimate_moving_heading(self.frames[-1],background,current,(100,100),100)
                self.assertEqual(result['status'],'separated_candidate')
                self.assertLess(abs((result['direction_deg']-angle+180)%360-180),6)
                self.assertFalse(result['navigation_approved'])

    def test_missing_overlay_and_large_movement_rejected(self):
        background,_=build_background(self.frames,self.angles,(100,100),100)
        for current in (self.render(self.shifted(-1,3),None),self.render(self.shifted(12,0),300)):
            self.assertIsNone(estimate_moving_heading(self.frames[-1],background,current,(100,100),100)['direction_deg'])

    def test_stationary_reference_without_rotation_rejected(self):
        with self.assertRaises(ValueError):build_background(self.frames[:8],[240]*8,(100,100),100)
