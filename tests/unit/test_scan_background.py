import unittest
from tests.unit import test_moving_scan as fixture
from app.navigation.scan_background import build_sweep_background
import numpy as np


class SweepBackgroundTests(unittest.TestCase):
    def setUp(self):self.scene=fixture.MovingScanTests();self.scene.setUp()

    def test_full_sweep_removes_overlay_without_direction_labels(self):
        frames=[self.scene.render(self.scene.background,a) for a in range(0,360,40)]
        background,model=build_sweep_background(frames,(100,100),100)
        self.assertLess(np.mean(np.abs(background-self.scene.background)),1)
        self.assertFalse(model['navigation_approved'])

    def test_fixed_or_narrow_views_rejected(self):
        for angles in ([270]*9,list(range(270,315,5))):
            frames=[self.scene.render(self.scene.background,a) for a in angles]
            with self.assertRaises(ValueError):build_sweep_background(frames,(100,100),100)

    def test_changed_map_rejected(self):
        frames=[self.scene.render(self.scene.background,a) for a in range(0,360,40)]
        frames[-1]=np.roll(frames[-1],12,axis=1)
        with self.assertRaises(ValueError):build_sweep_background(frames,(100,100),100)
