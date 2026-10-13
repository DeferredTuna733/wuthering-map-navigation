import unittest
import cv2
import numpy as np
from tools.review_step_translation import compensate_translation


class TranslationReviewTests(unittest.TestCase):
    def setUp(self):
        rng=np.random.default_rng(31)
        self.frame=cv2.GaussianBlur(rng.integers(20,180,(200,200,3),dtype=np.uint8),(3,3),0)

    def test_small_translation_recovers_background(self):
        shifted=cv2.warpAffine(self.frame,np.float32([[1,0,-1],[0,1,3]]),(200,200))
        corrected,measurements=compensate_translation(self.frame,[shifted],(100,100),100)
        self.assertIsNotNone(corrected)
        np.testing.assert_allclose(measurements[0]['shift_xy'],[-1,3],atol=.25)
        error=np.mean(np.abs(corrected[0][25:175,25:175].astype(float)-self.frame[25:175,25:175]))
        self.assertLess(error,4)

    def test_large_translation_rejected(self):
        shifted=np.roll(self.frame,12,axis=1)
        corrected,_=compensate_translation(self.frame,[shifted],(100,100),100)
        self.assertIsNone(corrected)

    def test_unrelated_background_rejected(self):
        corrected,_=compensate_translation(self.frame,[np.zeros_like(self.frame)],(100,100),100)
        self.assertIsNone(corrected)
