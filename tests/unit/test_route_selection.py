import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from app.map_editor.gui import MapDrawApp,ROUTE_COL

class RouteSelectionTests(unittest.TestCase):
    def make_app(self):
        app=MapDrawApp.__new__(MapDrawApp)
        app.canvas=Mock();app.route_list=Mock();app.route_list.selection.return_value=()
        app.lbl_selected_route=Mock();app.lbl_route=Mock();app._set_status=Mock()
        app.offset=(20,30);app.scale=2;app.map_img=True;app.map_meta={}
        app.img_w=app.img_h=4096;app.mode='draw';app._drag=True;app._moved=False
        app.route_px=[(100,200),(130,230)];app._route_items=[(None,11),(12,13)]
        app.selected_route_index=None;app.transform=(1,0,-1700,0,1,-1700)
        app._render=Mock();return app
    def test_click_existing_selects_without_adding(self):
        app=self.make_app();app._add_route_point=Mock()
        x,y=app._img_to_screen(130,230)
        app.on_release(SimpleNamespace(x=x,y=y))
        self.assertEqual(app.selected_route_index,1)
        app._add_route_point.assert_not_called()
        app.lbl_selected_route.config.assert_called_with(text='标记点 2：X=-1570.00  Y=-1470.00',fg=__import__('app.map_editor.gui',fromlist=['YELLOW']).YELLOW)
        app._render.assert_not_called()
    def test_nearest_hit_and_zoom_independent_radius(self):
        app=self.make_app();x,y=app._img_to_screen(100,200)
        self.assertEqual(app._hit_route_point(x+8,y),0)
        self.assertIsNone(app._hit_route_point(x+11,y))
    def test_list_selection_highlights(self):
        app=self.make_app();app.route_list.selection.return_value=('0',)
        app._on_route_list_select();self.assertEqual(app.selected_route_index,0)
        app.route_list.see.assert_called_once_with('0')
    def test_undo_selected_item_stays_consistent(self):
        app=self.make_app();app.selected_route_index=1
        app.undo_route()
        self.assertEqual(len(app.route_px),1);self.assertEqual(app.selected_route_index,0)
        app.route_list.delete.assert_called_once_with('1')
    def test_round_strokes_do_not_change_route_geometry(self):
        app=self.make_app();app._route_items=[]
        app._append_route_item(1)
        kwargs=app.canvas.create_line.call_args.kwargs
        self.assertEqual(kwargs['capstyle'],'round');self.assertEqual(kwargs['joinstyle'],'round')
        self.assertNotIn('smooth',kwargs)
        self.assertEqual(app.route_px,[(100,200),(130,230)])
    def test_zoom_limit_40_anchored_at_cursor(self):
        app=self.make_app();app.fit_scale=.2;app.zoom=39;app.scale=7.8
        app._schedule_render=Mock();event=SimpleNamespace(x=250,y=250,delta=120)
        before=app._screen_to_img(event.x,event.y)
        app.on_wheel(event)
        self.assertEqual(app.zoom,40)
        after=app._screen_to_img(event.x,event.y)
        for a,b in zip(before,after):self.assertAlmostEqual(a,b)

if __name__=='__main__':unittest.main()
