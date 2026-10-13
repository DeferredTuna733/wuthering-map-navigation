import unittest
from tools.monitor_ai_heading import consistent_coordinate_pair,coordinate_continuity_ok


class CoordinatePairTests(unittest.TestCase):
    def test_small_actual_motion_is_retained(self):
        self.assertTrue(consistent_coordinate_pair((-733,1195,30),(-732,1193,30)))

    def test_large_jump_or_height_error_is_rejected(self):
        for point in ((-700,1195,30),(-733,1195,34),(733,1195,30)):
            self.assertFalse(consistent_coordinate_pair((-733,1195,30),point))

    def test_missing_or_nonfinite_reading_is_rejected(self):
        for point in (None,(float('nan'),1195,30)):
            self.assertFalse(consistent_coordinate_pair((-733,1195,30),point))

    def test_missing_minus_never_updates_history_as_large_positive_jump(self):
        self.assertFalse(coordinate_continuity_ok((-739,1136,31),(740,1136,31),10))
        self.assertTrue(coordinate_continuity_ok((-739,1136,31),(-740,1136,31),10))
