import unittest
from unittest.mock import Mock
from app.navigation.short_route_test import run_short_route
from app.navigation.single_point_test import Limits
from tests.unit.test_single_point import Clock


class ShortRouteTests(unittest.TestCase):
    def run_route(self,reads,limits=Limits(),first_point=2):
        clock=Clock();reader=iter(reads);self.down=Mock();self.up=Mock();self.turn=Mock()
        return run_short_route([(0,0),(8,0),(16,0)],lambda:next(reader),self.down,self.up,self.turn,
                               lambda:None,limits,clock,clock.sleep,first_point=first_point)

    def test_advances_only_after_arrival_confirmation(self):
        result=self.run_route([(x,0,4) for x in (0,0,5,5,5,5,9,13,13)])
        self.assertEqual(result['status'],'arrived')
        self.assertEqual(result['completed_points'],[2,3])
        self.assertEqual(result['steps'],3)
        self.assertEqual(self.up.call_count,3)

    def test_resume_preserves_actual_point_numbers(self):
        result=self.run_route([(x,0,4) for x in (0,0,5,5,5,5,9,13,13)],first_point=3)
        self.assertEqual(result['completed_points'],[3,4])

    def test_step_limit_shared_between_segments(self):
        result=self.run_route([(x,0,4) for x in (0,0,5,5,5,5,9)],Limits(max_steps=2))
        self.assertEqual(result['status'],'step_limit')
        self.assertEqual(result['completed_points'],[2])
        self.assertEqual(self.down.call_count,2)

    def test_height_budget_does_not_reset_between_segments(self):
        result=self.run_route([(0,0,4),(0,0,4),(5,0,9),(5,0,9),(5,0,10)])
        self.assertEqual(result['status'],'height_changed')
        self.assertEqual(self.down.call_count,1)

    def test_unconfirmed_first_arrival_never_advances(self):
        result=self.run_route([(0,0,4),(0,0,4),(5,0,4),(1,0,4)])
        self.assertEqual(result['status'],'arrival_not_confirmed')
        self.assertEqual(len(result['segments']),1)

    def test_time_budget_shared_between_segments(self):
        clock=Clock();points=iter([(x,0,4) for x in (0,0,5,5,5)])
        def read():
            clock.sleep(4)
            return next(points)
        down=Mock()
        result=run_short_route([(0,0),(8,0),(16,0)],read,down,Mock(),Mock(),lambda:None,
                               Limits(max_seconds=20),clock,clock.sleep)
        self.assertEqual(result['status'],'time_limit')
        self.assertEqual(result['completed_points'],[2])
        self.assertEqual(down.call_count,1)
