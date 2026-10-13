import json
import unittest
from pathlib import Path
from unittest.mock import patch
import app.navigation.route_runner as w

class WalkRouteTests(unittest.TestCase):
    def test_ocr_failure_stops_without_movement(self):
        with patch.object(w,'read_coord',return_value=None), patch.object(w.keyboard,'is_pressed',return_value=False), patch.object(w.keyboard,'press') as press, patch.object(w.time,'sleep'):
            self.assertFalse(w.walk_to_target(None,None,(20,20,None),0,1))
            press.assert_not_called()
    def test_emergency_releases_key(self):
        with patch.object(w,'read_coord',return_value=(0,0,0)), patch.object(w.keyboard,'is_pressed',side_effect=[False,True]), patch.object(w.keyboard,'press'), patch.object(w.keyboard,'release') as release:
            with self.assertRaises(KeyboardInterrupt):
                w.walk_to_target(None,None,(20,20,None),0,1)
            release.assert_called_once_with('w')
    def test_load_gg_draft(self):
        draft={'source':'wuthering.gg','navigation_approved':False,'points':[[-488.5,1006.2],[-459.4,1042.5]],'height':None}
        with patch('app.navigation.route_runner.os.path.exists',return_value=True), patch('builtins.open',mock_open_json(draft)):
            targets, source=w.load_targets()
        self.assertEqual(source,'gg_route_draft.json')
        self.assertEqual(targets[0],(-488.5,1006.2,None))
    def test_draft_rejects_approved_flag(self):
        draft={'source':'wuthering.gg','navigation_approved':True,'points':[[0,0]]}
        with patch('app.navigation.route_runner.os.path.exists',return_value=True), patch('builtins.open',mock_open_json(draft)):
            targets, source=w.load_targets()
        self.assertEqual(targets,[])
    def test_heightless_route_keeps_none(self):
        draft={'source':'wuthering.gg','navigation_approved':False,'points':[[0,1704]]}
        with patch('app.navigation.route_runner.os.path.exists',return_value=True), patch('builtins.open',mock_open_json(draft)):
            targets, _=w.load_targets()
        self.assertEqual(targets,[(0.0,1704.0,None)])

def mock_open_json(value):
    import io
    class Ctx:
      def __enter__(self):return io.StringIO(json.dumps(value))
      def __exit__(self,*a):pass
    return lambda *a,**k:Ctx()
if __name__=='__main__':unittest.main()
