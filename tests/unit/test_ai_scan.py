import unittest
import numpy as np
from types import SimpleNamespace
from unittest.mock import Mock
from app.navigation.moving_scan import sector
from app.navigation.ai_scan import mask_heading,predict_heading


class AiMaskTests(unittest.TestCase):
    def test_sector_angles_including_wraparound(self):
        for angle in (0,73,235,300,359):
            result=mask_heading(sector((200,200),(100,100),100,angle),(100,100),100)
            self.assertEqual(result['status'],'ai_heading_candidate')
            self.assertLess(abs((result['direction_deg']-angle+180)%360-180),2)
            self.assertFalse(result['navigation_approved'])

    def test_empty_and_full_masks_cannot_supply_direction(self):
        for mask in (np.zeros((200,200)),np.ones((200,200))):
            self.assertIsNone(mask_heading(mask,(100,100),100)['direction_deg'])

    def test_wrong_opening_rejected_even_with_clear_sector(self):
        yy,xx=np.indices((200,200))
        angle=np.degrees(np.arctan2(yy-100,xx-100))
        for opening in (30,95):
            mask=(np.abs(angle)<opening/2)&(np.hypot(xx-100,yy-100)<94)
            self.assertEqual(mask_heading(mask,(100,100),100)['status'],'sector_aperture_unresolved')

    def test_missing_yellow_anchor_rejects_before_model_inference(self):
        model=Mock()
        result,_=predict_heading(model,np.zeros((200,200,3),np.uint8),
                                dict(center_xy=[100,100],player_center_xy=[100,102],radius=100))
        self.assertEqual(result['status'],'player_anchor_not_supported')
        model.predict.assert_not_called()

    def test_low_model_score_rejects_clear_mask(self):
        mask=sector((200,200),(100,100),100,0).astype(float)
        tensor=SimpleNamespace(cpu=lambda:SimpleNamespace(numpy=lambda:mask))
        score=SimpleNamespace(cpu=lambda:.46)
        model=Mock()
        model.predict.return_value=[SimpleNamespace(masks=SimpleNamespace(data=[tensor]),
                                                    boxes=SimpleNamespace(conf=[score]))]
        result,_=predict_heading(model,np.zeros((200,200,3),np.uint8),dict(center_xy=[100,100],radius=100))
        self.assertEqual(result['status'],'low_model_support')
        self.assertIsNone(result['direction_deg'])

    def test_two_valid_sectors_are_never_resolved_by_top_score(self):
        masks=[sector((200,200),(100,100),100,a).astype(float) for a in (0,180)]
        tensors=[SimpleNamespace(cpu=lambda m=m:SimpleNamespace(numpy=lambda:m)) for m in masks]
        scores=[SimpleNamespace(cpu=lambda s=s:s) for s in (.99,.80)]
        model=Mock()
        model.predict.return_value=[SimpleNamespace(masks=SimpleNamespace(data=tensors),boxes=SimpleNamespace(conf=scores))]
        result,_=predict_heading(model,np.zeros((200,200,3),np.uint8),dict(center_xy=[100,100],radius=100))
        self.assertEqual(result['status'],'multiple_sectors_detected')
        self.assertIsNone(result['direction_deg'])

    def test_one_valid_sector_survives_an_invalid_extra_mask(self):
        masks=[sector((200,200),(100,100),100,0).astype(float),np.ones((200,200))]
        tensors=[SimpleNamespace(cpu=lambda m=m:SimpleNamespace(numpy=lambda:m)) for m in masks]
        scores=[SimpleNamespace(cpu=lambda:.95),SimpleNamespace(cpu=lambda:.99)]
        model=Mock()
        model.predict.return_value=[SimpleNamespace(masks=SimpleNamespace(data=tensors),boxes=SimpleNamespace(conf=scores))]
        result,_=predict_heading(model,np.zeros((200,200,3),np.uint8),dict(center_xy=[100,100],radius=100))
        self.assertEqual(result['status'],'ai_heading_candidate')
        self.assertLess(abs((result['direction_deg']+180)%360-180),2)
