from unittest.mock import Mock
import unittest
from app.navigation.single_point_test import run_single,Limits

class Clock:
 def __init__(self):self.v=0
 def __call__(self):return self.v
 def sleep(self,x):self.v+=x
class SignTests(unittest.TestCase):
 def test_cross_sample_minus_sign_is_fixed(self):
  c=Clock(); values=iter([(0,0,10),(0,0,10),(-1,0,10),(1,0,10),(2,0,10),(3,0,10)])
  out=run_single((0,0),(10,0),lambda:next(values),Mock(),Mock(),Mock(),lambda:None,Limits(max_steps=1),c,c.sleep)
  reads=[e['coordinate'] for e in out['events'] if e['event']=='read']
  self.assertIn((-1,0,10),reads);self.assertNotIn((1,0,10),reads)
  self.assertNotEqual(out['status'],'abnormal_displacement')
if __name__=='__main__':unittest.main()
