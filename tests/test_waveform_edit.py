import math
import unittest
from sinisistar_dglab.waveform_edit import apply_stroke,sanitize_points

class WaveformDrawing(unittest.TestCase):
    def test_one_fast_drag_fills_every_crossed_node(self):
        result=apply_stroke([0.]*16,0,0,1,1)
        for index,value in enumerate(result):self.assertAlmostEqual(value,index/15)
    def test_drag_backwards_changes_the_same_line(self):
        result=apply_stroke([0.]*16,1,1,0,0)
        self.assertEqual(result,apply_stroke([0.]*16,0,0,1,1))
    def test_drag_only_changes_its_local_span(self):
        result=apply_stroke([.7]*16,4/15,.1,8/15,.9)
        self.assertEqual(result[:4],[.7]*4);self.assertEqual(result[9:],[.7]*7)
        self.assertAlmostEqual(result[6],.5)
    def test_repeated_vertical_move_changes_the_current_node(self):
        result=apply_stroke([.5]*16,7/15,.2,7/15,.8)
        self.assertAlmostEqual(result[7],.8)
        self.assertEqual(result[:7]+result[8:],[.5]*15)
    def test_edge_and_outside_strokes_are_clamped(self):
        result=apply_stroke([.4]*16,-1,-1,2,2)
        self.assertEqual(result[0],0);self.assertEqual(result[-1],1)
        self.assertEqual(apply_stroke([0.]*16,.5,0,.5,1)[8],1)
    def test_invalid_draft_or_pointer_is_rejected(self):
        for points in ([0.]*15,[math.nan]*16,[True]*16):
            with self.assertRaises(ValueError):sanitize_points(points)
        with self.assertRaises(ValueError):apply_stroke([0.]*16,0,0,math.inf,1)
