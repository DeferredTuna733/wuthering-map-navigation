import cv2
import unittest
import numpy as np
from app.navigation.minimap_heading import detect_scan_heading,resolve_minimap_region,MINIMAP_REGION_FILE

class HeadingTests(unittest.TestCase):
 def test_invalid(self):self.assertEqual(detect_scan_heading(None).reason,'invalid_image')
 def test_region_requires_config(self):
  import tempfile
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as tmp:
   with patch('app.navigation.minimap_heading.MINIMAP_REGION_FILE',__import__('pathlib').Path(tmp)/'missing.json'):
    with self.assertRaises(ValueError): resolve_minimap_region({0:{}})
 def test_synthetic_right_wedge(self):
  image=np.zeros((200,200,3),np.uint8);cx=cy=100
  for y in range(35,166):
   for x in range(cx+5,166):
    if (x-cx)**2+(y-cy)**2<70**2 and abs(np.degrees(np.arctan2(-(y-cy),x-cx)))<18:image[y,x]=(230,230,230)
  result=detect_scan_heading(image,(cx,cy),70)
  self.assertIsNotNone(result.angle_deg);self.assertLess(_distance(result.angle_deg,0),20)
 def test_bgra_capture_supported(self):
  image=np.zeros((200,200,4),np.uint8)
  cv2.ellipse(image,(100,100),(70,70),0,-25,25,(220,220,220,255),-1)
  result=detect_scan_heading(image,(100,100),70)
  self.assertIsNotNone(result.angle_deg)
  self.assertLess(_distance(result.angle_deg,0),10)
 def test_fixed_white_icon_is_rejected(self):
  image=np.zeros((200,200,3),np.uint8)
  cv2.circle(image,(100,45),16,(255,255,255),-1)
  result=detect_scan_heading(image,(100,100),100)
  self.assertIsNone(result.angle_deg)
 def test_sector_direction_with_brighter_icon(self):
  for angle in (0,90,180,270):
   with self.subTest(angle=angle):
    image=np.zeros((200,200,3),np.uint8)
    cv2.ellipse(image,(100,100),(80,80),0,angle-30,angle+30,(180,180,180),-1)
    cv2.circle(image,(100,45),12,(255,255,255),-1)
    result=detect_scan_heading(image,(100,100),100)
    self.assertIsNotNone(result.angle_deg)
    self.assertLess(_distance(result.angle_deg,angle),10)
 def test_two_sectors_are_ambiguous(self):
  image=np.zeros((200,200,3),np.uint8)
  for angle in (0,180):
   cv2.ellipse(image,(100,100),(80,80),0,angle-30,angle+30,(220,220,220),-1)
  self.assertIsNone(detect_scan_heading(image,(100,100),100).angle_deg)
 def test_user_annotated_transparent_sector(self):
  from pathlib import Path
  import json
  root=Path(__file__).resolve().parents[2]
  label=json.loads((root/'config/navigation/scan_reference.json').read_text(encoding='utf-8'))
  result=detect_scan_heading(cv2.imread(label['source_image']),(100,100),100)
  self.assertIsNotNone(result.angle_deg)
  self.assertLess(_distance(result.angle_deg,label['annotated_direction_deg']),5)
  self.assertEqual(result.reason,'boundary_pair')
 def test_map_lines_with_competing_sectors_rejected(self):
  image=np.zeros((200,200,3),np.uint8)
  for angle in (0,180):
   cv2.ellipse(image,(100,100),(85,85),0,angle-32,angle+32,(120,120,120),-1)
  self.assertIsNone(detect_scan_heading(image,(100,100),100).angle_deg)
 def test_weak_sector_can_use_threshold_consensus(self):
  image=np.zeros((200,200,3),np.uint8)
  cv2.ellipse(image,(100,100),(85,85),0,238,302,(10,10,10),-1)
  result=detect_scan_heading(image,(100,100),100)
  self.assertIsNotNone(result.angle_deg)
  self.assertLess(_distance(result.angle_deg,270),10)
  self.assertEqual(result.reason,'weak_boundary_consensus')
 def test_latest_low_contrast_map_is_not_guessed(self):
  from pathlib import Path
  root=Path(__file__).resolve().parents[2]
  frame=root/'outputs/navigation/heading_readings/20261011_123612_429280/01_before.png'
  result=detect_scan_heading(cv2.imread(str(frame)),(100,100),100)
  self.assertIsNone(result.angle_deg)
 def test_yellow_arrow_is_not_white_heading(self):
  image=np.zeros((200,200,3),np.uint8);cv2.arrowedLine(image,(100,100),(160,100),(0,220,255),8)
  result=detect_scan_heading(image,(100,100),70)
  self.assertIn(result.reason,('scan_not_found','scan_ambiguous'))

def _distance(a,b):return abs((a-b+180)%360-180)
if __name__=='__main__':unittest.main()
