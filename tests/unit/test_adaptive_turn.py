import unittest
from unittest.mock import Mock
from app.navigation.adaptive_turn import TurnModel,adaptive_turn
from app.navigation.single_point_test import StopTest


class AdaptiveTurnTests(unittest.TestCase):
    def simulate(self,gain,initial=180,requested=120):
        camera=[initial];commands=[];model=TurnModel()
        def move(x,y):
            commands.append(x)
            camera[0]=(camera[0]+gain*x)%360
        result=adaptive_turn(requested,lambda:camera[0],move,lambda:None,lambda seconds:None,model)
        return result,commands,model

    def test_larger_actual_response_is_learned_and_corrected_without_stopping(self):
        result,commands,model=self.simulate(13/120)
        self.assertLessEqual(abs(result['residual']),2)
        self.assertGreater(model.gain,1/16)
        self.assertLessEqual(len(commands),3)
        self.assertTrue(all(abs(x)<=120 for x in commands))
        self.assertLess(commands[1],0)

    def test_opposite_response_updates_sign_and_corrects(self):
        result,commands,model=self.simulate(-.08)
        self.assertLess(model.gain,0)
        self.assertLess(abs(result['residual']),3)
        self.assertTrue(all(abs(x)<=120 for x in commands))

    def test_wrapping_heading_keeps_correct_delta(self):
        result,commands,model=self.simulate(.1,initial=357)
        self.assertLessEqual(abs(result['residual']),2)

    def test_zero_response_does_not_create_a_fake_gain_or_infinite_loop(self):
        result,commands,model=self.simulate(0)
        self.assertEqual(result['status'],'correction_pending')
        self.assertEqual(len(commands),3)
        self.assertEqual(model.samples,[])

    def test_emergency_prevents_any_mouse_action(self):
        move=Mock()
        def guard():raise StopTest('emergency_key')
        with self.assertRaises(StopTest):adaptive_turn(120,lambda:0,move,guard,lambda s:None,TurnModel())
        move.assert_not_called()

    def test_excessive_actual_turn_still_rejects(self):
        with self.assertRaises(StopTest):self.simulate(.5)
