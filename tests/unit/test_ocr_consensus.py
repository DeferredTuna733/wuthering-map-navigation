import unittest
from unittest.mock import patch
import app.navigation.route_runner as w

class OCRConsensusTests(unittest.TestCase):
    def test_consensus_rejects_outliers(self):
        values=[(-485,1047,14),(-485,1048,14),(-483,1054,15),(-468,1078,15)]
        with patch.object(w,'read_once',side_effect=values), patch.object(w.time,'sleep'):
            self.assertEqual(w.read_coord(None,None,4),(-484,1050,14))
    def test_no_consensus_returns_none(self):
        values=[(-500,900,1),(-400,1000,15),(-300,1100,50)]
        with patch.object(w,'read_once',side_effect=values), patch.object(w.time,'sleep'):
            self.assertIsNone(w.read_coord(None,None,3))
    def test_mss_api_is_current(self):
        self.assertTrue(hasattr(w.mss,'MSS'))

if __name__=='__main__': unittest.main()
