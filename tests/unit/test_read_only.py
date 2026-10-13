import unittest
from unittest.mock import patch
import app.navigation.route_runner as w

class ReadOnlyTests(unittest.TestCase):
    def test_read_only_bounds(self):
        with patch.object(w,'read_coord',side_effect=[(1,2,3),None,(4,5,6)]), patch.object(w.time,'sleep'):
            with patch.object(w.mss,'MSS') as mss_cls:
                ctx=mss_cls.return_value.__enter__.return_value
                ctx.monitors={0:{'left':0,'top':0,'height':1080,'width':1920},1:{'left':0,'top':0,'height':1080,'width':1920}}
                with patch.object(w,'resolve_region',return_value=({'left':10,'top':1045,'width':175,'height':35},'test')):
                    self.assertEqual(w.read_only_loop(3,0),0)
    def test_read_only_invalid_samples(self):
        with patch('sys.argv',['route','--read-only','--samples','0']), patch.object(w,'read_only_loop') as loop:
            with self.assertRaises(SystemExit) as error:
                w.main()
            self.assertEqual(error.exception.code,2)
            loop.assert_not_called()

if __name__=='__main__':unittest.main()
