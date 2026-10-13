import unittest
import cv2
import numpy as np
from app.navigation.scan_sequence import analyze_sequence,scheduled_turn,summarize_fixed_turn


class SequenceTests(unittest.TestCase):
    def test_recorded_weak_turn_and_stationary_frames(self):
        from pathlib import Path
        folder=Path('outputs/navigation/fixed_turn_sequences/20261011_131211_466464')
        frames=[cv2.imread(str(p)) for p in sorted(folder.glob('frame_*.png'))]
        self.assertEqual(len(frames),40)
        result=analyze_sequence(frames,(100,100),100)
        self.assertEqual(result['status'],'temporal_estimates')
        self.assertTrue(result['weak_signal'])
        self.assertEqual(result['estimates'][0]['angle_deg'],300)
        self.assertEqual(result['estimates'][-1]['angle_deg'],315)
        stationary=analyze_sequence(frames[-8:]*5,(100,100),100)
        self.assertNotEqual(stationary['status'],'temporal_estimates')

    def test_recorded_low_quality_turn_stays_rejected(self):
        from pathlib import Path
        folder=Path('outputs/navigation/fixed_turn_sequences/20261011_125236_446748')
        frames=[cv2.imread(str(p)) for p in sorted(folder.glob('frame_*.png'))]
        self.assertEqual(analyze_sequence(frames,(100,100),100)['status'],'weak_scan_unverified')

    def test_fixed_turn_exact_amount_no_reverse(self):
        moves=[];events=[]
        for index in range(40):
            scheduled_turn(index,120,lambda x,y:moves.append((x,y)),lambda:None,events)
        self.assertEqual(sum(x for x,y in moves),120)
        self.assertEqual(len(moves),12)
        self.assertTrue(all(x>0 and y==0 for x,y in moves))
        self.assertTrue(all(e['completed'] for e in events))

    def test_guard_rejects_before_input(self):
        def fail():raise RuntimeError('focus lost')
        with self.assertRaises(RuntimeError):
            scheduled_turn(8,120,lambda x,y:self.fail('Unexpected input'),fail,[])

    def test_left_turn_signed_amount_and_candidate(self):
        events=[];moves=[]
        for index in range(40):
            scheduled_turn(index,240,lambda x,y:moves.append((x,y)),lambda:None,events,-1)
        self.assertEqual(sum(x for x,y in moves),-240)
        self.assertTrue(all(x<0 and y==0 for x,y in moves))
        result=summarize_fixed_turn({'estimates':[{'angle_deg':a} for a in [303]*8+[288]*8]},events)
        self.assertAlmostEqual(result['relative_units_per_degree'],16)
        self.assertFalse(result['calibration_verified'])

    def test_candidate_does_not_approve_calibration(self):
        analysis={'estimates':[{'angle_deg':a} for a in [270]*8+[300]*8]}
        result=summarize_fixed_turn(analysis,[{'relative_x':120,'completed':True}])
        self.assertEqual(result['relative_units_per_degree'],4)
        self.assertFalse(result['calibration_verified'])
    def frames(self,angles):
        rng=np.random.default_rng(7)
        base=rng.integers(25,85,(200,200),dtype=np.uint8)
        base=cv2.GaussianBlur(base,(3,3),0)
        yy,xx=np.indices(base.shape)
        radius=np.hypot(xx-100,yy-100)
        directions=np.degrees(np.arctan2(yy-100,xx-100))%360
        frames=[]
        for i,angle in enumerate(angles):
            gray=base.astype(np.float32)+i*.3
            if angle is not None:
                mask=(np.abs((directions-angle+180)%360-180)<32)&(radius<90)
                gray[mask]+=18
            frame=cv2.cvtColor(np.clip(gray,0,255).astype(np.uint8),cv2.COLOR_GRAY2BGR)
            cv2.circle(frame,(100,45),12,(240,240,240),-1)
            frames.append(frame)
        return frames

    def test_stationary_frames_not_direction(self):
        result=analyze_sequence(self.frames([270]*12),(100,100),100)
        self.assertEqual(result['status'],'insufficient_view_change')

    def test_rotating_faint_sector_against_fixed_icon(self):
        angles=list(range(0,360,30))
        result=analyze_sequence(self.frames(angles),(100,100),100)
        self.assertEqual(result['status'],'temporal_estimates')
        usable=0
        for expected,estimate in zip(angles,result['estimates']):
            actual=estimate['angle_deg']
            if actual is not None:
                usable+=1
                self.assertLess(abs((actual-expected+180)%360-180),12)
        self.assertGreaterEqual(usable,8)

    def test_map_displacement_rejected(self):
        frames=self.frames([270]*12)
        frames[-1]=np.roll(frames[-1],8,axis=1)
        self.assertEqual(analyze_sequence(frames,(100,100),100)['status'],'map_alignment_failed')

    def test_quarter_turn_has_usable_estimates(self):
        angles=list(range(180,271,6))
        result=analyze_sequence(self.frames(angles),(100,100),100)
        self.assertEqual(result['status'],'temporal_estimates')
        estimates=[(angle,e['angle_deg']) for angle,e in zip(angles,result['estimates'])
                   if e['angle_deg'] is not None]
        self.assertGreaterEqual(len(estimates),4)
        for expected,actual in estimates:
            self.assertLess(abs((actual-expected+180)%360-180),15)

    def test_insufficient_frames(self):
        self.assertEqual(analyze_sequence(self.frames([0]*3),(100,100),100)['status'],'insufficient_frames')

    def test_late_rotation_does_not_erase_initial_sector(self):
        angles=[270]*25+list(range(276,367,6))
        result=analyze_sequence(self.frames(angles),(100,100),100)
        self.assertEqual(result['status'],'temporal_estimates')
        self.assertLess(abs((result['initial_direction_deg']-270+180)%360-180),9)
        last=result['estimates'][-1]['angle_deg']
        self.assertIsNotNone(last)
        self.assertLess(abs((last-angles[-1]+180)%360-180),12)
