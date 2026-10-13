import io
import tempfile
import time
import unittest
from pathlib import Path
from PIL import Image
from app.map_editor.detail_tiles import DetailTiles


def png(color):
    out=io.BytesIO();Image.new('RGB',(256,256),color).save(out,format='PNG');return out.getvalue()

class DetailTests(unittest.TestCase):
    def test_keys_and_camera(self):
        self.assertEqual(DetailTiles.visible_keys((100,100),4,(-256,-256),6),[(6,1,1)])
        self.assertEqual(DetailTiles.visible_keys((100,100),4,(20000,20000),6),[])
    def test_seamless_neighbors_and_no_coordinate_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=DetailTiles(tmp)
            try:
                d.images[(6,0,0)]=Image.new('RGBA',(256,256),'red')
                d.images[(6,1,0)]=Image.new('RGBA',(256,256),'blue')
                frame=d.refine(Image.new('RGB',(512,200),'green'),4,(0,0),request=False)
                self.assertEqual(frame.getpixel((250,100)),(255,0,0))
                self.assertEqual(frame.getpixel((260,100)),(0,0,255))
                for x in range(253,260):self.assertNotEqual(frame.getpixel((x,100)),(0,128,0))
            finally:d.close()
    def test_background_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=DetailTiles(tmp)
            try:
                frame=Image.new('RGB',(100,100),'green')
                self.assertIs(d.refine(frame,1,(0,0)),frame)
                self.assertIs(d.refine(frame,4,(0,0),request=False),frame)
            finally:d.close()
    def test_async_disk_cache_and_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            def fetch(z,x,y):calls.append((z,x,y));return png('red')
            d=DetailTiles(tmp,fetch=fetch)
            try:
                frame=Image.new('RGB',(100,100),'green')
                d.refine(frame,4,(0,0))
                deadline=time.monotonic()+3
                while d.pending and time.monotonic()<deadline:
                    d.poll();time.sleep(.01)
                self.assertFalse(d.pending)
                self.assertEqual(d.refine(frame,4,(0,0)).getpixel((50,50)),(255,0,0))
                self.assertEqual(calls,[(6,0,0)])
            finally:d.close()
            d=DetailTiles(tmp,fetch=lambda *args: self.fail('Should reuse disk cache'))
            try:self.assertEqual(d._load((6,0,0)).getpixel((10,10)),(255,0,0,255))
            finally:d.close()
    def test_download_failure_preserves_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            def fail(*args):raise OSError('offline')
            d=DetailTiles(tmp,fetch=fail)
            try:
                frame=Image.new('RGB',(100,100),'green');d.refine(frame,4,(0,0))
                deadline=time.monotonic()+3
                while d.pending and time.monotonic()<deadline:d.poll();time.sleep(.01)
                self.assertEqual(d.errors,1)
                self.assertIs(d.refine(frame,4,(0,0)),frame)
            finally:d.close()

class OfflineTests(unittest.TestCase):
    def test_offline_default_never_fetches(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            d=DetailTiles(tmp)
            try:
                with patch('app.map_editor.detail_tiles.urlopen',side_effect=AssertionError('Network must not be called')):
                    with self.assertRaises(FileNotFoundError):d._load((6,0,0))
            finally:d.close()

if __name__=='__main__':unittest.main()
