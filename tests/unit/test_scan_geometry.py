import unittest
import cv2
import numpy as np
from app.navigation.scan_geometry import boundary_evidence,corroborate


class GeometryTests(unittest.TestCase):
    def test_conflicts_and_wraparound(self):
        self.assertEqual(corroborate({'direction_deg':201},74)['status'],'spatial_conflict')
        self.assertEqual(corroborate({'direction_deg':300},302,200)['status'],'temporal_conflict')
        self.assertEqual(corroborate({'direction_deg':358},2)['direction_deg'],0)
        self.assertIsNone(corroborate({'direction_deg':300},None)['direction_deg'])
    def image(self,angles):
        image=np.full((200,200,3),40,dtype=np.uint8)
        for a in angles:cv2.ellipse(image,(100,100),(90,90),0,a-32,a+32,(60,60,60),-1)
        return image

    def test_four_directions(self):
        for angle in (0,90,180,270):
            r=boundary_evidence(self.image([angle]),(100,100),100)
            self.assertEqual(r['status'],'geometry_candidate')
            self.assertLess(abs((r['direction_deg']-angle+180)%360-180),5)
            self.assertFalse(r['confidence_calibrated'])

    def test_icon_only_rejected(self):
        image=self.image([]);cv2.circle(image,(100,45),12,(255,255,255),-1)
        self.assertIsNone(boundary_evidence(image,(100,100),100)['direction_deg'])

    def test_competing_sectors_rejected(self):
        self.assertEqual(boundary_evidence(self.image([0,180]),(100,100),100)['status'],'ambiguous')
