import unittest
from tools.scan_labeler import validate_polygon


class PolygonTests(unittest.TestCase):
    def test_normalized_segmentation_format(self):
        line=validate_polygon([(100,100),(140,40),(170,70),(180,100)],(200,200))
        self.assertEqual(line.split()[0],'0')
        self.assertEqual(len(line.split()),9)
        self.assertTrue(all(0<=float(x)<=1 for x in line.split()[1:]))

    def test_tiny_and_outside_rejected(self):
        for points in [[(1,1),(2,1),(2,2),(1,2)],[(0,0),(201,0),(201,100),(0,100)]]:
            with self.assertRaises(ValueError):validate_polygon(points,(200,200))

    def test_crossing_rejected(self):
        with self.assertRaises(ValueError):validate_polygon([(0,0),(100,100),(0,100),(150,0)],(200,200))
