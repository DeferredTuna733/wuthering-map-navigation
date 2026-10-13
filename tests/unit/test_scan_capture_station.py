import unittest
import queue
import ctypes
from tools.scan_capture_station import mapped_region,mapped_circle,CircleSelection,Hotkeys,KeyEdges


class CaptureStationTests(unittest.TestCase):
    def test_poll_fallback_only_on_press_edges(self):
        edges=KeyEdges()
        self.assertEqual(edges.update({'capture':True,'finish':False}),['capture'])
        self.assertEqual(edges.update({'capture':True,'finish':False}),[])
        self.assertEqual(edges.update({'capture':False,'finish':False}),[])
        self.assertEqual(edges.update({'capture':True,'finish':True}),['capture','finish'])
    def test_creation_gesture_never_switches_to_move(self):
        circle=CircleSelection(800,600);circle.begin(200,200)
        circle.drag(220,200);circle.drag(250,200);circle.end()
        self.assertEqual(circle.center,(200,200));self.assertEqual(circle.radius,50)
        circle.begin(210,200);circle.drag(230,220);circle.end()
        self.assertEqual(circle.center,(220,220));self.assertEqual(circle.radius,50)
        circle.resize(70);self.assertEqual(circle.radius,70)
        circle.begin(600,400);circle.drag(620,400);circle.end()
        self.assertEqual(circle.center,(600,400));self.assertEqual(circle.radius,20)

    def test_circle_mapping_negative_monitor_and_clamp(self):
        region,geometry=mapped_circle((100,100),50,(1920,1080),(960,540),{'left':-1920,'top':0})
        self.assertEqual(region,{'left':-1820,'top':100,'width':200,'height':200})
        self.assertEqual(geometry,{'center_xy':[100,100],'radius':100})
        circle=CircleSelection(800,600);circle.begin(100,100);circle.resize(50)
        circle.begin(100,100);circle.drag(-200,-200);circle.end()
        self.assertEqual(circle.center,(50,50))
        with self.assertRaises(ValueError):mapped_circle((100,100),2,(1920,1080),(960,540),{'left':0,'top':0})

    def test_reverse_drag_and_negative_monitor_origin(self):
        r=mapped_region((200,150),(100,50),(1920,1080),(960,540),{'left':-1920,'top':-200})
        self.assertEqual(r,{'left':-1720,'top':-100,'width':200,'height':200})

    def test_outside_and_tiny_regions_rejected(self):
        for a,b in [((0,0),(10,10)),((-10,0),(100,100)),((0,0),(2000,100))]:
            with self.assertRaises(ValueError):mapped_region(a,b,(1920,1080),(960,540),{'left':0,'top':0})

    def test_hotkey_message_and_cleanup_without_keyboard_input(self):
        events=queue.Queue();hook=Hotkeys(events,'F10','F11')
        hook.start()
        try:
            self.assertTrue(ctypes.WinDLL('user32').PostThreadMessageW(hook.thread_id,0x312,1,0))
            self.assertEqual(events.get(timeout=2),'capture')
            self.assertTrue(ctypes.WinDLL('user32').PostThreadMessageW(hook.thread_id,0x312,2,0))
            self.assertEqual(events.get(timeout=2),'finish')
        finally:hook.stop()
        self.assertFalse(hook.thread.is_alive())
