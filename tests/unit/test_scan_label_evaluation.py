import unittest
from tools.evaluate_scan_labels import polygon_heading


class LabelDirectionTests(unittest.TestCase):
    def test_polygon_order_does_not_change_direction(self):
        points=[(150,15),(100,100),(50,15),(100,2)]
        for polygon in (points,points[::-1],points[2:]+points[:2]):
            heading,aperture=polygon_heading(polygon)
            self.assertAlmostEqual(heading,270)
            self.assertTrue(60<aperture<65)

    def test_missing_central_apex_rejected(self):
        with self.assertRaises(ValueError):polygon_heading([(0,0),(50,0),(50,50),(0,50)])
