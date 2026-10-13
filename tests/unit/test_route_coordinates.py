import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from app.map_editor.route_coordinates import parse_xy, game_to_pixel, import_points
from app.map_editor.gui import MapDrawApp, affine_apply


class RouteCoordinateTests(unittest.TestCase):
    transform = (1.45263671875, 0, -1700, 0, 1.45263671875, -1700)

    def test_fractional_start_round_trip(self):
        point = (-740.1234, 1136.5678)
        px = game_to_pixel(self.transform, point, (4096, 4096))
        for actual, expected in zip(affine_apply(self.transform, *px), point):
            self.assertAlmostEqual(actual, expected, places=10)

    def test_inverse_with_rotated_affine(self):
        transform = (2, .5, -10, -.2, 3, -20)
        self.assertEqual(game_to_pixel(transform, affine_apply(transform, 40, 50), (100,100)), (40,50))

    def test_invalid_manual_or_outside_coordinates(self):
        self.assertEqual(parse_xy('-740，1136'), (-740,1136))
        for value in ('nan,2', '1,2,3', '1,b', '9000,0'):
            with self.assertRaises(ValueError): parse_xy(value)
        with self.assertRaises(ValueError): game_to_pixel(self.transform, (-2000,0), (4096,4096))
        with self.assertRaises(ValueError): game_to_pixel((1,1,0,1,1,0), (0,0), (100,100))

    def test_import_validates_all_points_and_mapping(self):
        draft = dict(source='wuthering.gg', image_size=[4096,4096],
                     pixel_to_game_affine=list(self.transform), points=[[-740,1136],[-730,1136]])
        self.assertEqual(len(import_points(draft, self.transform, (4096,4096))), 2)
        draft['points'].append([True,1])
        with self.assertRaises(ValueError): import_points(draft,self.transform,(4096,4096))
        draft['points']=[[-740,1136]];draft['image_size']=[100,100]
        with self.assertRaises(ValueError): import_points(draft,self.transform,(4096,4096))

    def test_drag_edits_point_not_viewport_and_undo_restores_it(self):
        app=MapDrawApp.__new__(MapDrawApp)
        app.route_px=[(10,20),(50,60)];app._history=[]
        app.offset=(0,0);app.scale=2;app.mode='draw'
        app.img_w=100;app.img_h=100;app._moved=False;app._point_drag=None
        app._select_route_point=Mock();app._update_overlay_positions=Mock()
        app._sync_start=Mock();app.route_list=Mock();app._route_row=Mock()
        app.on_press(SimpleNamespace(x=20,y=40))
        app.on_drag(SimpleNamespace(x=30,y=50))
        self.assertEqual(app.route_px,[(15,25),(50,60)])
        self.assertEqual(app.offset,(0,0))
        self.assertEqual(app._history,[[(10,20),(50,60)]])
        app._replace_route=Mock();app.undo_edit()
        app._replace_route.assert_called_once_with([(10,20),(50,60)])


if __name__=='__main__': unittest.main()
