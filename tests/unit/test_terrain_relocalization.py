import copy
import unittest
import numpy as np
from app.navigation.terrain_relocalization import ocr_seeds,registration_usable
from app.navigation.minimap_position import RollingPositionTracker


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.affine=[[2.45,0,0],[0,2.45,0]]
        self.registration=dict(status='terrain_registration_candidate',affine=self.affine,
                               mapped_game_xy=[-750.5,1129.1],coordinate=[-750,1129,33],
                               heldout_supported=4,heldout_total=4)

    def test_rejected_geometry_and_sign_do_not_relocalize(self):
        self.assertTrue(registration_usable(self.registration,self.affine))
        for change in (dict(heldout_supported=3),dict(heldout_total=8),
                       dict(coordinate=[750,1129,33]),dict(affine=[[3.5,0,0],[0,3.5,0]]),
                       dict(status='terrain_registration_rejected')):
            candidate=dict(self.registration,**change)
            self.assertFalse(registration_usable(candidate,self.affine))

    def test_ocr_seeds_preserve_observed_signs_and_skip_low_confidence(self):
        seeds=ocr_seeds([dict(variants=[dict(coordinate=[750,1129,33],confidence=.9),
                                       dict(coordinate=[-750,1129,33],confidence=.9),
                                       dict(coordinate=[123,456,33],confidence=.7)])])
        self.assertEqual(seeds,[[750,1129,33],[-750,1129,33]])

    def test_list_and_tuple_candidates_share_one_xy_seed(self):
        seeds=ocr_seeds([dict(variants=[dict(coordinate=(-750,1129,33),confidence=.9),
                                       dict(coordinate=[-750,1129,34],confidence=.9)])])
        self.assertEqual(seeds,[[-750,1129,33]])

    def test_only_valid_registration_restores_blocked_tracker(self):
        image=np.random.default_rng(12).integers(0,256,(200,200,3),dtype=np.uint8)
        tracker=RollingPositionTracker(image,dict(center_xy=[100,100],radius=100),0,[0,0],self.affine)
        tracker.blocked=True
        self.assertFalse(tracker.restore(image,0,1,dict(status='relocalization_unresolved')))
        accepted=dict(status='terrain_relocalized',coordinate_xy=[-750,1129],affine=self.affine)
        invalid=copy.deepcopy(accepted);invalid['affine'][0][0]=float('nan')
        self.assertFalse(tracker.restore(image,0,1,invalid))
        self.assertTrue(tracker.restore(image,0,1,accepted))
        self.assertFalse(tracker.blocked)
        observed=tracker.observe(image,0,1.3)
        np.testing.assert_allclose(observed['coordinate_xy'],[-750,1129],atol=.01)
