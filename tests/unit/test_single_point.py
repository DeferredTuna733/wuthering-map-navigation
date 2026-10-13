import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock
from app.navigation.single_point_test import run_single,load_point,Limits,StopTest

class Clock:
    def __init__(self):self.now=0
    def __call__(self):return self.now
    def sleep(self,seconds):self.now+=seconds

class SinglePointTests(unittest.TestCase):
    def run_case(self,points,guard=None,limits=Limits(),move=None):
        clock=Clock();reads=iter(points);down=Mock();up=Mock();mouse=move or Mock()
        result=run_single((0,0),(10,0),lambda:next(reads),down,up,mouse,guard or (lambda:None),limits,clock,clock.sleep)
        return result,down,up,mouse
    def test_arrival_confirmed_only_single_target(self):
        result,down,up,mouse=self.run_case([(0,0,10),(0,0,10),(4,0,10),(8,0,10),(8,0,10)])
        self.assertEqual(result['status'],'arrived');self.assertEqual(result['steps'],2)
        self.assertEqual(down.call_count,2);self.assertEqual(up.call_count,2);mouse.assert_not_called()
    def test_bad_start_no_input(self):
        result,down,up,_=self.run_case([(100,0,10),(100,0,10)])
        self.assertEqual(result['status'],'not_near_route_start');down.assert_not_called();up.assert_not_called()
    def test_initial_read_instability_no_input(self):
        result,down,_,_=self.run_case([(0,0,10),(4,0,10)])
        self.assertEqual(result['status'],'initial_read_unstable');down.assert_not_called()
    def test_ocr_failure_after_step_releases(self):
        result,down,up,_=self.run_case([(0,0,10),(0,0,10),None,None,None])
        self.assertEqual(result['status'],'ocr_failed');up.assert_called_once_with('w')
    def test_focus_lost_during_hold_releases(self):
        down=Mock();up=Mock();clock=Clock();read=Mock(return_value=(0,0,10))
        def guard():
            if down.call_count:raise StopTest('game_not_foreground')
        result=run_single((0,0),(10,0),read,down,up,Mock(),guard,clock=clock,sleep=clock.sleep)
        self.assertEqual(result['status'],'game_not_foreground');up.assert_called_once_with('w')
    def test_moving_away_stops_before_mouse(self):
        result,_,up,mouse=self.run_case([(0,0,10),(0,0,10),(-4,0,10)])
        self.assertEqual(result['status'],'moving_away');mouse.assert_not_called();up.assert_called_once()
    def test_step_limit(self):
        result,down,up,_=self.run_case([(0,0,10),(0,0,10),(1,0,10)],limits=Limits(max_steps=1))
        self.assertEqual(result['status'],'step_limit');self.assertEqual(down.call_count,1)
    def test_time_limit_releases(self):
        result,down,up,_=self.run_case([(0,0,10),(0,0,10)],limits=Limits(max_seconds=.03))
        self.assertEqual(result['status'],'time_limit');up.assert_called_once()
    def test_height_change_stops(self):
        result,_,_,_=self.run_case([(0,0,10),(0,0,10),(2,0,20)])
        self.assertEqual(result['status'],'height_changed')
    def test_turn_is_clamped(self):
        result,_,_,mouse=self.run_case([(0,0,10),(0,0,10),(1,2,10)],limits=Limits(max_steps=1))
        self.assertEqual(result['status'],'step_limit')
        self.assertLessEqual(abs(mouse.call_args.args[0]),120)
    def test_no_fallback_or_point_filtering(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'route.json'
            draft={'source':'wuthering.gg','navigation_approved':False,'points':[[0,0],[10,0]]}
            path.write_text(json.dumps(draft))
            self.assertEqual(load_point(path),((0.,0.),(10.,0.)))
            draft['points'][1]=[True,0];path.write_text(json.dumps(draft))
            with self.assertRaises(ValueError):load_point(path)
            draft['points'][1]=[30,0];path.write_text(json.dumps(draft))
            with self.assertRaises(ValueError):load_point(path)

if __name__=='__main__':unittest.main()
