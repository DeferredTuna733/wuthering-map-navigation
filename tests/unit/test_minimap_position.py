import unittest
import cv2
import numpy as np
from app.navigation.minimap_position import track_position,RollingPositionTracker


class MinimapPositionTests(unittest.TestCase):
    def setUp(self):
        self.image=np.random.default_rng(21).integers(0,256,(200,200,3),dtype=np.uint8)
        self.circle=dict(center_xy=[100,100],radius=100)
        self.affine=[[2,0,0],[0,2,0]]

    def test_background_shift_means_opposite_player_motion(self):
        frame=cv2.warpAffine(self.image,np.float32([[1,0,3],[0,1,-2]]),(200,200))
        result=track_position(self.image,frame,self.circle,0,0,[10,20],self.affine)
        self.assertEqual(result['status'],'local_position_candidate')
        scale=5950/16384
        self.assertAlmostEqual(result['coordinate_xy'][0],10-6*scale,delta=.1)
        self.assertAlmostEqual(result['coordinate_xy'][1],20+4*scale,delta=.1)

    def test_unrelated_scene_cannot_update_position(self):
        frame=np.random.default_rng(99).integers(0,256,(200,200,3),dtype=np.uint8)
        self.assertIsNone(track_position(self.image,frame,self.circle,0,0,[10,20],self.affine)['coordinate_xy'])

    def test_rotation_and_large_travel_are_rejected(self):
        for matrix in (cv2.getRotationMatrix2D((100,100),10,1),np.float32([[1,0,20],[0,1,0]])):
            frame=cv2.warpAffine(self.image,matrix,(200,200))
            self.assertIsNone(track_position(self.image,frame,self.circle,0,0,[10,20],self.affine)['coordinate_xy'])

    def test_adjacent_frames_cover_more_than_fixed_anchor_range(self):
        tracker=RollingPositionTracker(self.image,self.circle,0,[10,20],self.affine)
        for step in range(1,9):
            frame=cv2.warpAffine(self.image,np.float32([[1,0,step*2],[0,1,0]]),(200,200))
            result=tracker.observe(frame,0,step*.3)
            self.assertIsNotNone(result['coordinate_xy'])
        self.assertAlmostEqual(result['coordinate_xy'][0],10-32*5950/16384,delta=.15)
        self.assertEqual(tracker.updates,8)

    def test_scene_failure_blocks_future_updates(self):
        tracker=RollingPositionTracker(self.image,self.circle,0,[10,20],self.affine)
        unrelated=np.random.default_rng(99).integers(0,256,(200,200,3),dtype=np.uint8)
        self.assertIsNone(tracker.observe(unrelated,0,0)['coordinate_xy'])
        self.assertEqual(tracker.observe(self.image,0,.3)['status'],'relocalization_required')
        np.testing.assert_equal(tracker.xy,[10,20])

    def test_gap_and_uncorrected_distance_stop_tracking(self):
        tracker=RollingPositionTracker(self.image,self.circle,0,[10,20],self.affine)
        tracker.observe(self.image,0,0)
        self.assertEqual(tracker.observe(self.image,0,3)['status'],'tracking_time_gap')
        tracker=RollingPositionTracker(self.image,self.circle,0,[10,20],self.affine,max_unverified_travel=1)
        frame=cv2.warpAffine(self.image,np.float32([[1,0,3],[0,1,0]]),(200,200))
        self.assertEqual(tracker.observe(frame,0,0)['status'],'unverified_travel_exceeded')

    def test_ocr_validation_requires_nearby_position_and_time(self):
        tracker=RollingPositionTracker(self.image,self.circle,0,[10,20],self.affine)
        tracker.observe(self.image,0,1)
        tracker.travel=12
        self.assertFalse(tracker.corroborate([-10,20,0],1.1))
        self.assertFalse(tracker.corroborate([10,20,0],2))
        self.assertTrue(tracker.corroborate([10,20,0],1.1))
        self.assertEqual(tracker.travel,0)


if __name__=='__main__':unittest.main()
