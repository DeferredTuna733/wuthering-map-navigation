import unittest
from tools.check_background_heading import summarize,load_model


class HeadingCheckTests(unittest.TestCase):
    def test_circular_stability_does_not_verify_accuracy(self):
        result=summarize([{'direction_deg':a} for a in [357,0,3,0,0,0,None,None]])
        self.assertEqual(result['status'],'stable_candidate')
        self.assertFalse(result['accuracy_verified'])
        self.assertFalse(result['navigation_approved'])

    def test_missing_and_conflicting_samples_rejected(self):
        self.assertEqual(summarize([{'direction_deg':None}]*8)['status'],'insufficient_heading_samples')
        self.assertEqual(summarize([{'direction_deg':a} for a in [0,0,0,0,60,60,60,60]])['status'],'unstable_heading')

    def test_saved_model_dimensions_match(self):
        _,report,background,reference=load_model()
        self.assertEqual(background.shape,reference.shape[:2])
        self.assertEqual(background.shape,(report['region']['height'],report['region']['width']))
