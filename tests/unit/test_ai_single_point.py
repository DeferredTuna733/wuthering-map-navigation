import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock,patch
import numpy as np
from app.navigation.enhanced_coordinate import inspect_enhanced_crop
from app.navigation.ai_single_point import turn_response_ok,CoordinateGate,trial_points,trial_limits
from app.navigation.single_point_test import run_single, Limits
from tests.unit.test_single_point import Clock
from app.navigation.coordinate_reader import parse_coordinate_text


class AISinglePointTests(unittest.TestCase):
    def test_full_route_budget_preserves_motion_limits(self):
        limits=trial_limits(2,7)
        self.assertEqual((limits.max_steps,limits.max_seconds),(32,75))
        self.assertEqual((limits.step_seconds,limits.max_mouse_pixels,limits.corridor_stop_distance),(.35,120,6))
        self.assertEqual(trial_limits(5,7).max_steps,16)
        self.assertEqual(trial_limits(3,4).max_seconds,25)

    def test_resume_selects_consecutive_segments_without_changing_route(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'route.json'
            contents=json.dumps(dict(source='wuthering.gg',navigation_approved=False,points=[[0,0],[8,0],[16,0],[24,0]]))
            path.write_text(contents,encoding='utf-8')
            self.assertEqual(trial_points(path,3,4),[(8,0),(16,0),(24,0)])
            self.assertEqual(path.read_text(encoding='utf-8'),contents)
            with self.assertRaises(ValueError):trial_points(path,4,3)

    def test_resume_remaining_route_validates_each_segment(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'route.json'
            points=[[i*8,0] for i in range(7)]
            path.write_text(json.dumps(dict(source='wuthering.gg',navigation_approved=False,points=points)),encoding='utf-8')
            self.assertEqual(trial_points(path,5,7),[(24,0),(32,0),(40,0),(48,0)])
            points[5]=[100,0]
            path.write_text(json.dumps(dict(source='wuthering.gg',navigation_approved=False,points=points)),encoding='utf-8')
            with self.assertRaises(ValueError):trial_points(path,5,7)

    def test_enhancement_requires_signed_agreement_and_rejects_jump(self):
        crop=np.zeros((28,177,3),np.uint8)
        with patch('app.navigation.enhanced_coordinate.get_ocr') as backend:
            backend.return_value.side_effect=[([('-750,1133,32',.95)],None)]*3
            self.assertEqual(inspect_enhanced_crop(crop,(-748,1133,32))['coordinate'],(-750,1133,32))
            backend.return_value.side_effect=[([('-750,1133,32',.95)],None)]*3
            self.assertEqual(inspect_enhanced_crop(crop,(-748,1133))['coordinate'],(-750,1133,32))
            backend.return_value.side_effect=[([('750,1133,32',.95)],None)]*3
            self.assertIsNone(inspect_enhanced_crop(crop,(-748,1133,32))['coordinate'])
            backend.return_value.side_effect=[([('-750,1133,32',.95)],None),([('750,1133,32',.95)],None),([('750,1133,32',.95)],None)]
            self.assertIsNone(inspect_enhanced_crop(crop,(-748,1133,32))['coordinate'])
            backend.return_value.side_effect=[([('-750,1133,32',.75)],None)]*3
            self.assertIsNone(inspect_enhanced_crop(crop,(-748,1133,32))['coordinate'])

    def test_bad_sign_is_discarded_then_valid_pair_can_recover(self):
        gate=CoordinateGate((-748,1133,32))
        self.assertIsNone(gate.offer((750,1133,32)))
        self.assertIsNone(gate.offer((750,1133,32)))
        self.assertEqual(gate.anchor,(-748,1133,32))
        self.assertIsNone(gate.offer((-750,1133,32)))
        self.assertEqual(gate.offer((-750,1133,32)),(-750,1133,32))

    def test_integer_row_separator_dot_is_opt_in_and_does_not_repair_sign(self):
        self.assertIsNone(parse_coordinate_text('-750,1132.32')[0])
        self.assertEqual(parse_coordinate_text('-750,1132.32',True)[0],(-750,1132,32))
        self.assertEqual(parse_coordinate_text('750,1132.32',True)[0],(750,1132,32))
        for text in ('A750,1132,32','h750,1132,32','-750.1,1132,32','-750,1132.3,32','-750.1132.32'):
            self.assertIsNone(parse_coordinate_text(text,True)[0])

    def test_turn_wrap_and_reversed_input(self):
        self.assertTrue(turn_response_ok(357,4,120))
        self.assertTrue(turn_response_ok(4,357,-120))
        self.assertFalse(turn_response_ok(20,12,120))
        self.assertFalse(turn_response_ok(20,20,120))
        self.assertFalse(turn_response_ok(20,65,120))

    def test_strict_sign_jump_stops_without_turn(self):
        clock=Clock();points=iter([(-748,1133,31),(-748,1133,31),(749,1133,31)])
        down,up,turn=Mock(),Mock(),Mock()
        result=run_single((-748,1133),(-757,1125),lambda:next(points),down,up,turn,
                          lambda:None,Limits(),clock,clock.sleep,correct_sign=False)
        self.assertEqual(result['status'],'abnormal_displacement')
        up.assert_called_once_with('w');turn.assert_not_called()


if __name__=='__main__':unittest.main()
