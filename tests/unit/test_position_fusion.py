import unittest
from app.navigation.position_fusion import fuse_coordinate


def diagnostic(first,second):
    return dict(coordinate=first if first==second else None,
                variants=[dict(coordinate=p,confidence=.95) for p in (first,second)])


class FusionTests(unittest.TestCase):
    def test_terrain_supplies_xy_when_ocr_sign_variants_disagree(self):
        result=fuse_coordinate(dict(coordinate_xy=[-626.2,1049.1]),
                               diagnostic((626,1049,4),(-626,1049,4)),1,1.1)
        self.assertEqual(result['coordinate'],(-626.2,1049.1,4))

    def test_height_disagreement_or_unrelated_digits_rejects(self):
        position=dict(coordinate_xy=[-626.2,1049.1])
        for d in (diagnostic((-626,1049,4),(-626,1049,42)),
                  diagnostic((123,456,4),(123,456,4)),diagnostic(None,None)):
            self.assertIsNone(fuse_coordinate(position,d,1,1.1)['coordinate'])

    def test_missing_terrain_allows_only_strict_ocr_and_stale_frames_reject(self):
        d=diagnostic((-626,1049,4),(-626,1049,4))
        self.assertEqual(fuse_coordinate(dict(coordinate_xy=None),d,1,1.1)['source'],'strict_ocr')
        self.assertIsNone(fuse_coordinate(dict(coordinate_xy=[-626,1049]),d,1,2)['coordinate'])

    def test_map_near_zero_cannot_resolve_conflicting_sign(self):
        result=fuse_coordinate(dict(coordinate_xy=[-3.5,1049]),diagnostic((3,1049,4),(3,1049,4)),1,1.1)
        self.assertIsNone(result['coordinate'])
