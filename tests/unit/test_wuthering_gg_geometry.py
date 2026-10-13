import unittest
from app.map_editor.geometry import *

class GGGeometryTests(unittest.TestCase):
    def test_roundtrip(self):
        for point in [(0,0),(-998900,-7462500),(1234567,-3210000)]:
            for zoom in range(2,7):
                result=global_pixel_to_site_xy(*site_xy_to_global_pixel(*point,zoom),zoom)
                for actual,expected in zip(result,point):
                    self.assertAlmostEqual(actual,expected,places=6)
    def test_origin(self):
        self.assertEqual(site_xy_to_global_pixel(-17000000,-17000000,2),(0,0))
    def test_tile_local(self):
        tx,ty,x,y=site_xy_to_tile(0,0,2)
        self.assertTrue(0 <= x < 256 and 0 <= y < 256)
        self.assertEqual((tx,ty),(1,1))
    def test_invalid(self):
        with self.assertRaises(ValueError):
            site_xy_to_global_pixel(0,0,True)
        with self.assertRaises(ValueError):
            site_xy_to_leaflet(float('nan'),0)

if __name__=='__main__':
    unittest.main()
