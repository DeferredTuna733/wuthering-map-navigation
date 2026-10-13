import unittest
from tests.unit import test_moving_scan as fixture
from app.navigation.local_background import LocalBackground
from app.navigation.rolling_background import RollingBackground


class LocalBackgroundTests(unittest.TestCase):
    def setUp(self):
        self.scene=fixture.MovingScanTests();self.scene.setUp()
        self.model=LocalBackground(RollingBackground(self.scene.frames[-1],self.scene.background,(100,100),100))

    def test_stationary_diverse_views_rebuild_without_labels(self):
        for angle in range(0,360,40):
            result=self.model.observe(self.scene.render(self.scene.background,angle))
        self.assertEqual(self.model.rebuilds,1)
        self.assertIsNotNone(result['direction_deg'])

    def test_repeated_view_cannot_reset_travel_budget(self):
        self.model.rolling.travel=10
        for _ in range(9):self.model.observe(self.scene.render(self.scene.background,235))
        self.assertEqual(self.model.rebuilds,0)
        self.assertGreaterEqual(self.model.rolling.travel,10)
