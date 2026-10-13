import unittest
from app.navigation.route_corridor import segment_position,waypoint_reached


class CorridorTests(unittest.TestCase):
    def test_lateral_deviation_and_projection_on_diagonal(self):
        p=segment_position((3,4),(0,0),(10,10))
        self.assertAlmostEqual(p['cross_track'],2**-.5)
        self.assertAlmostEqual(p['fraction'],.35)

    def test_waypoint_passage_does_not_mean_terminal_arrival(self):
        self.assertTrue(waypoint_reached((15,3),(0,0),(10,0)))
        self.assertFalse(waypoint_reached((15,3),(0,0),(10,0),terminal=True))
        self.assertFalse(waypoint_reached((15,5),(0,0),(10,0)))

    def test_last_live_point_within_four_unit_arrival_radius(self):
        self.assertTrue(waypoint_reached((-754,1126),(-748,1133),(-757.239,1125.378),terminal=True))

    def test_distance_to_segment_includes_overshooting_end(self):
        self.assertEqual(segment_position((20,0),(0,0),(10,0))['segment_distance'],10)


if __name__=='__main__':unittest.main()
