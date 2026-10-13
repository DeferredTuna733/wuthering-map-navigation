import unittest
from tools.background_step_probe import displacement
from app.navigation.single_point_test import StopTest


class BackgroundStepTests(unittest.TestCase):
    def test_local_delta_and_no_movement(self):
        self.assertEqual(displacement((-490,1053,14),(-489,1053,14)),[1,0,0])
        self.assertEqual(displacement((-490,1053,14),(-490,1053,14)),[0,0,0])

    def test_unresolved_abnormal_or_lost_minus_sign_rejected(self):
        for after in (None,(-480,1053,14),(-490,1053,25),(490,1053,14)):
            with self.assertRaises(StopTest):displacement((-490,1053,14),after)
