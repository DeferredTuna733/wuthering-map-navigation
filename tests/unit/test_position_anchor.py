import tempfile
import unittest
from pathlib import Path
import numpy as np
from app.navigation.position_anchor import save_anchor, load_anchor


class AnchorTests(unittest.TestCase):
    def test_changed_capture_and_corrupted_image_are_rejected(self):
        region=dict(width=20,height=20,left=0,top=0)
        circle=dict(center_xy=[10,10],radius=10)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'anchor.json'
            save_anchor(path,np.zeros((20,20,3),np.uint8),region=region,circle=circle,
                        coordinate_xy=[-750,1129],angle=204,
                        affine=[[2,0,0],[0,2,0]],source='test')
            data,image=load_anchor(path,region,circle)
            self.assertEqual(data['coordinate_xy'],[-750,1129])
            self.assertEqual(image.shape,(20,20,3))
            with self.assertRaises(ValueError):
                load_anchor(path,dict(region,left=1),circle)
            path.with_suffix('.png').write_bytes(b'corrupted')
            with self.assertRaises(ValueError):
                load_anchor(path,region,circle)
