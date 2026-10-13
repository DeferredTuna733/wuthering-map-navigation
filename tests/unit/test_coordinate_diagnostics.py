import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
import numpy as np
from app.navigation import screen_region as region
from app.navigation import coordinate_reader as reader
from app.navigation import route_runner as runner

DESKTOP={'left':-1920,'top':0,'width':3840,'height':1080}

class CoordinateDiagnosticTests(unittest.TestCase):
    def test_default_monitor_origin(self):
        with tempfile.TemporaryDirectory() as tmp:
            crop,label=region.resolve_region([DESKTOP,{'left':-1920,'top':0,'width':1920,'height':1080}],Path(tmp)/'absent.json')
            self.assertEqual(crop,{'left':-1910,'top':1045,'width':175,'height':35})
    def test_config_roundtrip_and_invalid_region(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'ocr.json'
            crop={'left':400,'top':500,'width':190,'height':40}
            region.save_region(crop,DESKTOP,file)
            self.assertEqual(region.resolve_region([DESKTOP,DESKTOP],file)[0],crop)
            with self.assertRaises(ValueError):region.save_region({**crop,'width':True},DESKTOP,file)
            with self.assertRaises(ValueError):region.save_region({**crop,'left':3000},DESKTOP,file)
    def test_no_double_crop(self):
        sct=Mock();sct.grab.return_value=np.zeros((35,175,4),dtype=np.uint8)
        with patch.object(reader,'inspect_crop',return_value={'coordinate':(-454,444,50)}) as inspect:
            self.assertEqual(reader.read_once(sct,{'left':3}),(-454,444,50))
            self.assertEqual(inspect.call_args.args[0].shape,(35,175,4))
    def test_raw_evidence_keeps_text(self):
        engine=Mock(return_value=([['−454,444,50',.97]],0))
        with patch.object(reader,'get_ocr',return_value=engine):
            result=reader.inspect_crop(np.zeros((35,175,4),dtype=np.uint8))
        self.assertEqual(result['coordinate'],(-454,444,50))
        self.assertEqual(result['text'],'−454,444,50')
        self.assertEqual(result['confidence'],.97)
    def test_conflicting_variants_rejected(self):
        engine=Mock(side_effect=[([['-489,1054,14',.98]],0),([['-489,1051,14',.98]],0)])
        with patch.object(reader,'get_ocr',return_value=engine):
            result=reader.inspect_crop(np.zeros((28,177,4),dtype=np.uint8))
        self.assertIsNone(result['coordinate'])
        self.assertEqual(result['reason'],'variant_disagreement')
    def test_unrelated_text_and_low_confidence_rejected(self):
        for text,confidence in [('UID 123 456 78',.99),('-454,444,50',.6),('-454,444,50,20',.99)]:
            with patch.object(reader,'get_ocr',return_value=Mock(return_value=([[text,confidence]],0))):
                self.assertIsNone(reader.inspect_crop(np.zeros((28,177,4),dtype=np.uint8))['coordinate'])
    def test_extra_numbers_rejected(self):
        engine=Mock(return_value=([['123,-454,444,50',.97]],0))
        with patch.object(reader,'get_ocr',return_value=engine):
            self.assertIsNone(reader.inspect_crop(np.zeros((35,175,4),dtype=np.uint8))['coordinate'])
    def test_diagnostic_output_without_game_input(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner.paths,'ROOT',Path(tmp)), patch.object(runner.time,'sleep'), patch.object(runner.mss,'MSS') as capture, patch.object(runner,'resolve_region',return_value=({'left':0,'top':0,'width':175,'height':35},'test')), patch.object(reader,'inspect_crop',return_value={'coordinate':(-454,444,50),'text':'-454,444,50','confidence':.9,'reason':'parsed'}), patch.object(runner.keyboard,'press') as press, patch.object(runner.keyboard,'release') as release, patch.object(runner.pydirectinput,'moveRel') as move:
            capture.return_value.__enter__.return_value.grab.return_value=np.zeros((35,175,4),dtype=np.uint8)
            self.assertEqual(runner.read_only_loop(samples=2,interval=0,delay=2,diagnostics=True),0)
            report=next((Path(tmp)/'outputs/navigation/ocr_checks').rglob('report.json'))
            data=json.loads(report.read_text(encoding='utf-8'))
            self.assertEqual(data['consensus_count'],2)
            self.assertEqual(len(data['samples'][0]['raw_reads']),4)
            self.assertFalse(data['game_input_performed'])
            self.assertEqual(len(list(report.parent.glob('crop_*.png'))),2)
            press.assert_not_called();release.assert_not_called();move.assert_not_called()
    def test_read_only_and_execute_mutually_exclusive(self):
        with patch('sys.argv',['route','--execute','--read-only']),patch.object(runner,'read_only_loop') as loop:
            with self.assertRaises(SystemExit):runner.main()
            loop.assert_not_called()

if __name__=='__main__':unittest.main()
