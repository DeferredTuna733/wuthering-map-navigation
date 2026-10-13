import tempfile
import unittest
from pathlib import Path
from PIL import Image
from app.map_editor.map_assets import stitch_tiles,candidate_game_to_pixel_xy,candidate_pixel_to_game_xy

class GGMapTests(unittest.TestCase):
 def test_order_and_no_flips(self):
  with tempfile.TemporaryDirectory() as tmp:
   colors={(0,0):(255,0,0),(1,0):(0,255,0),(0,1):(0,0,255),(1,1):(255,255,0)}
   for (x,y),color in colors.items():
    Image.new('RGB',(256,256),color).save(Path(tmp)/f'{x}_{y}.png')
   image,records=stitch_tiles(tmp,2,(0,0,1,1))
   self.assertEqual(image.size,(512,512))
   self.assertEqual(len(records),4)
   for (x,y),color in colors.items():self.assertEqual(image.getpixel((x*256+10,y*256+10)),color)
 def test_missing_not_silently_filled(self):
  with tempfile.TemporaryDirectory() as tmp:
   with self.assertRaises(FileNotFoundError):stitch_tiles(tmp,2,(0,0,0,0))
 def test_wrong_size_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   Image.new('RGB',(255,256)).save(Path(tmp)/'0_0.png')
   with self.assertRaises(ValueError):stitch_tiles(tmp,2,(0,0,0,0))
 def test_transparent_background(self):
  with tempfile.TemporaryDirectory() as tmp:
   Image.new('RGBA',(256,256),(0,0,0,0)).save(Path(tmp)/'0_0.png')
   image,_=stitch_tiles(tmp,2,(0,0,0,0))
   self.assertEqual(image.getpixel((10,10)),(5,38,53))
 def test_mapping_roundtrip_includes_huko(self):
  for xyz in [(-487,1007,15),(-516,1704,11),(279,789,1),(269,795,1)]:
   for zoom,origin in [(4,(0,0)),(6,(19,24))]:
    result=candidate_pixel_to_game_xy(*candidate_game_to_pixel_xy(*xyz[:2],zoom,origin),zoom,origin)
    for value,expected in zip(result,xyz[:2]): self.assertAlmostEqual(value,expected,places=8)

if __name__=='__main__':unittest.main()
