import unittest
import cv2
from pathlib import Path
from app.navigation.temporal_step_probe import one_step,load_reference,match_heading


class TemporalStepTests(unittest.TestCase):
    def test_guard_prevents_movement(self):
        events=[]
        def stop():raise RuntimeError('lost focus')
        with self.assertRaises(RuntimeError):one_step(stop,lambda:events.append('down'),lambda:events.append('up'))
        self.assertEqual(events,[])

    def test_release_after_input_error(self):
        events=[]
        def down():events.append('down');raise RuntimeError('input error')
        with self.assertRaises(RuntimeError):one_step(lambda:None,down,lambda:events.append('up'))
        self.assertEqual(events,['down','up'])

    def test_release_after_focus_loss(self):
        events=[];checks=[]
        def guard():
            checks.append(1)
            if len(checks)>1:raise RuntimeError('focus lost')
        with self.assertRaises(RuntimeError):one_step(guard,lambda:events.append('down'),lambda:events.append('up'))
        self.assertEqual(events,['down','up'])

    def test_recorded_reference_matching(self):
        import json
        reference,coordinate,path=load_reference()
        report=json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(coordinate,tuple(report['after_coordinate']))
        angle,_=match_heading(reference,reference[-8:],(100,100),100)
        self.assertIsNotNone(angle)
        self.assertLess(abs((angle-report['fixed_turn']['scan_after_deg']+180)%360-180),6)

    def test_map_mismatch_rejected(self):
        import numpy as np
        reference,_,_=load_reference()
        shifted=[np.roll(frame,12,axis=1) for frame in reference[-8:]]
        angle,_=match_heading(reference,shifted,(100,100),100)
        self.assertIsNone(angle)
