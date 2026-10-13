import unittest
from unittest.mock import patch
import numpy as np
from app.navigation.coordinate_reader import parse_coordinate_text,inspect_crop


class DatetimeCoordinateTests(unittest.TestCase):
    def test_observed_slash_at_valid_date_boundary_only(self):
        text='-622,1051,4/2026-10-1202:28:56+8 * HD'
        self.assertEqual(parse_coordinate_text(text,True,True)[0],(-622,1051,4))
        self.assertIsNone(parse_coordinate_text(text,False,True)[0])
        for text in ('-622,1051,4/','-622/1051,4/2026-10-12','-622,1051,4//2026-10-12','-622,1051,4/2026-02-30'):
            self.assertIsNone(parse_coordinate_text(text,True,True)[0])

    def test_coordinate_lengths_and_signs_are_not_fixed(self):
        for point in ((1,2,4),(-666,1020,4),(-5000,5000,33),(0,0,0),(1234,-4567,-20)):
            text=','.join(map(str,point))+' 2026-10-12 01:35:00'
            self.assertEqual(parse_coordinate_text(text,require_datetime=True)[0],point)

    def test_date_year_merged_with_height_is_separated(self):
        for height in (4,33,-20):
            self.assertEqual(parse_coordinate_text(f'-666,1020,{height}2026-10-12',require_datetime=True)[0],(-666,1020,height))
        self.assertEqual(parse_coordinate_text('-666,1020.4 2026-10-12',True,True)[0],(-666,1020,4))

    def test_actual_game_time_zone_and_hd_footer(self):
        for text in ('-626,1049,4 2026-10-12 01:47:28+8 * HD',
                     '-626,1049,4 2026-10-1201:47:28+8* HD'):
            self.assertEqual(parse_coordinate_text(text,require_datetime=True)[0],(-626,1049,4))
        for tail in ('01:47:28+25 * HD','01:47:28+8:99 * HD','01:47:28+14:01 * HD'):
            self.assertIsNone(parse_coordinate_text('-626,1049,4 2026-10-12 '+tail,require_datetime=True)[0])

    def test_incomplete_invalid_or_extra_date_text_is_rejected(self):
        for text in ('-666,1020,42','-666,1020,4 2','-666,1020,4 2026-10-',
                     '-666,1020,4 2026-02-30','-666,1020,4 2026-10-12 25:01',
                     '-666,1020,4 2026-10-12 2026-10-13',
                     '-666,1020,4 2026-10-12 unrelated'):
            self.assertIsNone(parse_coordinate_text(text,require_datetime=True)[0])

    def test_crop_requires_both_variants_to_agree_after_date_split(self):
        results=[([['-666,1020,42026-10-12',.99]],None),
                 ([['-666,1020,4 2026-10-12',.99]],None)]
        with patch('app.navigation.coordinate_reader.get_ocr',return_value=iter_ocr(results)):
            result=inspect_crop(np.zeros((28,480,3),np.uint8),require_datetime=True)
        self.assertEqual(result['coordinate'],(-666,1020,4))


def iter_ocr(results):
    iterator=iter(results)
    return lambda *args,**kwargs:next(iterator)
