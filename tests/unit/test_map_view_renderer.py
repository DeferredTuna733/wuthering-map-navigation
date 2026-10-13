import unittest
from unittest.mock import Mock,patch
from PIL import Image
from app.map_editor.viewport_renderer import MapViewportRenderer
from app.map_editor.gui import MapDrawApp


class ViewportTests(unittest.TestCase):
    def test_zoom_and_pan_preserve_map_position(self):
        image=Image.new('RGB',(512,512),'red')
        image.paste(Image.new('RGB',(256,256),'blue'),(256,256))
        renderer=MapViewportRenderer(image)
        frame=renderer.render((100,100),2,(-600,-600))
        self.assertEqual(frame.size,(100,100))
        self.assertEqual(frame.getpixel((50,50)),(0,0,255))
        frame=renderer.render((100,100),1,(20,20))
        self.assertEqual(frame.getpixel((0,0)),(16,16,16))
        self.assertEqual(frame.getpixel((50,50)),(255,0,0))
    def test_large_zoom_has_bounded_output(self):
        renderer=MapViewportRenderer(Image.new('RGB',(4096,4096),'green'))
        frame=renderer.render((800,700),20,(-1234,-3456))
        self.assertEqual(frame.size,(800,700))
        self.assertIs(frame,renderer.render((800,700),20,(-1234,-3456)))
    def test_zoomed_out_and_odd_dimensions(self):
        renderer=MapViewportRenderer(Image.new('RGB',(1025,769),(12,34,56)))
        frame=renderer.render((300,300),.2,(10,10))
        self.assertEqual(frame.getpixel((100,100)),(12,34,56))
        self.assertEqual(frame.getpixel((299,299)),(16,16,16))
    def test_invalid_camera(self):
        renderer=MapViewportRenderer(Image.new('RGB',(32,32)))
        for size,scale,offset in [((0,1),1,(0,0)),((1,1),0,(0,0)),((1,1),1,(float('nan'),0))]:
            with self.assertRaises(ValueError): renderer.render(size,scale,offset)
    def test_add_undo_overlay_only(self):
        app=MapDrawApp.__new__(MapDrawApp)
        app.transform=(1,0,0,0,1,0);app.route_px=[]
        app._history=[];app.start_xy=Mock()
        app.selected_route_index=None;app.route_list=Mock();app.route_list.selection.return_value=();app.lbl_selected_route=Mock()
        app.offset=(0,0);app.scale=1;app.canvas=Mock();app._route_items=[]
        app.lbl_route=Mock();app._set_status=Mock();app._redraw_overlay=Mock();app._render=Mock()
        app._add_route_point(10,20)
        self.assertEqual(app.route_px,[(10,20)])
        app.undo_route()
        self.assertEqual(app.route_px,[])
        app._render.assert_not_called()
        app._redraw_overlay.assert_not_called()
        self.assertEqual(app.canvas.create_oval.call_count,1)
    def test_overlay_replaces_only_tags(self):
        app=MapDrawApp.__new__(MapDrawApp)
        app.map_img=True;app.canvas=Mock();app.calib_points=[];app.route_px=[]
        app._redraw_overlay()
        self.assertEqual([call.args for call in app.canvas.delete.call_args_list],[('calib',),('route',)])
    def test_render_events_coalesce(self):
        app=MapDrawApp.__new__(MapDrawApp)
        app.root=Mock();app.root.after.return_value='job';app._render_job=None;app._preview_pending=False;app._quality_job=None
        app._schedule_render();app._schedule_render()
        app.root.after.assert_called_once()
    def test_screen_coordinate_roundtrip(self):
        app=MapDrawApp.__new__(MapDrawApp)
        for scale,offset in [(.1,(-5.3,20)),(3.7,(-1800.8,-300.2))]:
            app.scale=scale;app.offset=offset
            point=app._screen_to_img(*app._img_to_screen(855,1886))
            self.assertAlmostEqual(point[0],855);self.assertAlmostEqual(point[1],1886)

class CacheTests(unittest.TestCase):
    def test_lazy_pyramid(self):
        renderer=MapViewportRenderer(Image.new('RGB',(4096,4096),'red'))
        self.assertEqual(len(renderer.levels),1)
        renderer.render((100,100),.1,(0,0))
        self.assertGreater(len(renderer.levels),1)
    def test_byte_bound_and_quality_separation(self):
        renderer=MapViewportRenderer(Image.new('RGB',(512,512),'red'),cache_bytes=60000)
        final=renderer.render((100,100),1,(0,0))
        preview=renderer.render((100,100),1,(0,0),'preview')
        self.assertIsNot(final,preview)
        for i in range(10):renderer.render((100,100),1,(i,0))
        self.assertLessEqual(renderer.frame_bytes,60000)
        self.assertEqual(len(renderer.frames),2)
    def test_pan_reuses_canvas_background(self):
        app=MapDrawApp.__new__(MapDrawApp);app.canvas=Mock()
        app.canvas.winfo_width.return_value=800;app.canvas.winfo_height.return_value=700
        app._background_item=7;app._background_view=(800,700,1,(0,0),128)
        app.scale=1;app.offset=(50,-70)
        self.assertTrue(app._move_cached_background())
        app.canvas.coords.assert_called_once_with(7,-78,-198)
        app.offset=(129,0)
        self.assertFalse(app._move_cached_background())
    def test_incremental_long_route(self):
        app=MapDrawApp.__new__(MapDrawApp);app.canvas=Mock();app.scale=1;app.offset=(0,0)
        app.route_px=[(i,i) for i in range(1000)];app._route_items=[(i,i) for i in range(1000)]
        app._history=[];app.start_xy=Mock()
        app.transform=(1,0,0,0,1,0);app.lbl_route=Mock();app._set_status=Mock()
        app.selected_route_index=None;app.route_list=Mock();app.route_list.selection.return_value=();app.lbl_selected_route=Mock()
        app._add_route_point(1001,1001)
        app.canvas.create_line.assert_called_once();app.canvas.create_oval.assert_called_once()
        self.assertEqual(len(app._route_items),1001)
        app.undo_route();self.assertEqual(len(app._route_items),1000)
        self.assertEqual(app.canvas.delete.call_count,2)

if __name__=='__main__':unittest.main()
