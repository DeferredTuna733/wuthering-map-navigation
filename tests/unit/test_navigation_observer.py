import unittest
from app.navigation.navigation_observer import NavigationObserver


class Background:
    def __init__(self):self.calls=0;self.angle=235
    def observe(self,frame):
        self.calls+=1
        return dict(status='robust_candidate' if self.angle is not None else 'map_alignment_failed',direction_deg=self.angle)


class ObserverTests(unittest.TestCase):
    def setUp(self):self.background=Background();self.observer=NavigationObserver(self.background)

    def test_coordinates_and_turns_are_reported_without_authorizing_navigation(self):
        a=self.observer.observe(None,(-478,1053,14))
        self.background.angle=299
        b=self.observer.observe(None,(-477,1052,14))
        self.assertEqual(b['coordinate_delta'],[1,-1,0])
        self.assertEqual(b['direction_deg'],299)
        self.assertFalse(a['navigation_approved'])

    def test_lost_minus_sign_stops_before_background_update(self):
        self.observer.observe(None,(-478,1053,14))
        r=self.observer.observe(None,(478,1053,14))
        self.assertEqual(r['status'],'abnormal_coordinate_displacement')
        self.assertEqual(self.background.calls,1)
        self.assertIsNone(self.observer.observe(None,(-478,1053,14))['direction_deg'])

    def test_missing_coordinate_and_heading_stop_session(self):
        r=self.observer.observe(None,None)
        self.assertEqual(r['status'],'coordinate_unresolved')
        self.assertEqual(self.background.calls,0)
        fresh=NavigationObserver(self.background);self.background.angle=None
        self.assertEqual(fresh.observe(None,(0,0,0))['status'],'map_alignment_failed')
