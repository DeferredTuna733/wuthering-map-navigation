import unittest
import numpy as np
import tempfile
from pathlib import Path
from tests.unit import test_moving_scan as fixture
from app.navigation.rolling_background import RollingBackground


class RollingTests(unittest.TestCase):
    def setUp(self):
        self.scene = fixture.MovingScanTests()
        self.scene.setUp()
        self.model = RollingBackground(self.scene.frames[-1], self.scene.background, (100,100),100)

    def test_refresh_then_turn_does_not_burn_sector_into_background(self):
        for shift, angle in (((3,7),235),((3,7),300),((5,10),90)):
            frame = self.scene.render(self.scene.shifted(*shift),angle)
            r = self.model.observe(frame)
            self.assertTrue(r['background_updated'])
            self.assertLess(abs((r['direction_deg']-angle+180)%360-180),6)
            self.assertFalse(r['navigation_approved'])

    def test_rejected_frame_does_not_mutate_reference(self):
        before = self.model.background.copy()
        r = self.model.observe(self.scene.render(self.scene.shifted(3,7),None))
        self.assertFalse(r['background_updated'])
        np.testing.assert_array_equal(before,self.model.background)
        self.assertEqual(self.model.updates,0)

    def test_travel_limit_stops_chained_drift(self):
        self.model.travel = 24
        r = self.model.observe(self.scene.render(self.scene.shifted(3,7),235))
        self.assertEqual(r['status'],'refresh_travel_limit')
        self.assertIsNone(r['direction_deg'])
        self.assertEqual(self.model.updates,0)

    def test_insufficient_inherited_coverage_rejects_without_mutating_state(self):
        self.model.valid[:]=0
        before=self.model.background.copy()
        r=self.model.observe(self.scene.render(self.scene.shifted(3,7),235))
        self.assertEqual(r['status'],'refresh_coverage_failed')
        self.assertIsNone(r['direction_deg'])
        np.testing.assert_array_equal(before,self.model.background)
        self.assertEqual(self.model.updates,0)

    def test_continuous_small_steps_track_turns_then_stop_at_travel_limit(self):
        accepted=0
        rejected=False
        for index in range(1,17):
            angle=(235+index*17)%360
            frame=self.scene.render(self.scene.shifted(index*2,0),angle)
            before=self.model.background.copy()
            r=self.model.observe(frame)
            if r['direction_deg'] is None:
                self.assertIn(r['status'],('refresh_travel_limit','refresh_coverage_failed'))
                np.testing.assert_array_equal(before,self.model.background)
                rejected=True
                break
            accepted+=1
            self.assertLess(abs((r['direction_deg']-angle+180)%360-180),6)
            self.assertLessEqual(self.model.travel,24)
        self.assertGreaterEqual(accepted,6)
        self.assertTrue(rejected)

    def test_saved_reference_preserves_budget_and_rejects_other_model(self):
        self.model.observe(self.scene.render(self.scene.shifted(3,7),235))
        provenance={'reference_report':'model-A'}
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)/'state'
            self.model.save(folder,provenance)
            loaded=RollingBackground.load(folder,provenance,(200,200),(100,100),100)
            self.assertEqual(loaded.travel,self.model.travel)
            self.assertEqual(loaded.updates,self.model.updates)
            np.testing.assert_array_equal(loaded.background,self.model.background)
            with self.assertRaises(ValueError):
                RollingBackground.load(folder,{'reference_report':'model-B'},(200,200),(100,100),100)

    def test_minimap_exterior_is_never_known_map(self):
        self.assertEqual(self.model.valid[0,0],0)
        frame=self.scene.render(self.scene.background,235)
        r=self.model.observe(frame)
        self.assertTrue(r['background_updated'])
        self.assertEqual(self.model.valid[0,0],0)

    def test_unknown_hidden_sector_cannot_be_repaired_from_overlay(self):
        from app.navigation.moving_scan import sector
        yy,xx=np.indices((200,200))
        distance=np.hypot(xx-100,yy-100)
        hidden=sector((200,200),(100,100),100,235)&(distance>30)&(distance<82)
        # Less than 2% of the whole ring, but more than 2% of the hidden region.
        indices=np.argwhere(hidden)
        chosen=indices[:100]
        self.model.valid[chosen[:,0],chosen[:,1]]=0
        before=self.model.background.copy()
        r=self.model.observe(self.scene.render(self.scene.background,235))
        self.assertEqual(r['status'],'hidden_background_unknown')
        self.assertIsNone(r['direction_deg'])
        np.testing.assert_array_equal(before,self.model.background)

    def test_fixed_view_straight_path_tracks_then_reports_its_limit(self):
        accepted=0
        for index in range(1,17):
            r=self.model.observe(self.scene.render(self.scene.shifted(index*2,0),0))
            if r['direction_deg'] is None:
                self.assertIn(r['status'],('refresh_travel_limit','refresh_coverage_failed','hidden_background_unknown'))
                break
            accepted+=1
            self.assertLess(abs((r['direction_deg']+180)%360-180),6)
            self.assertGreaterEqual(r['hidden_background_coverage'],.98)
        else:self.fail('Unvalidated straight trajectory must stop at its finite limit')
        self.assertGreaterEqual(accepted,6)
