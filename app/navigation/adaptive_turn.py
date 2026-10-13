"""Bounded online camera-response learning from screenshot headings."""
import math
from app.navigation.single_point_test import StopTest


def angle_delta(after,before):
    return (after-before+180)%360-180


class TurnModel:
    def __init__(self,gain=1/16):
        if not math.isfinite(gain) or not .015<=abs(gain)<=.25:
            raise ValueError('Invalid turn gain')
        self.gain=gain
        self.samples=[]

    def pixels(self,desired,max_pixels=120):
        return round(max(-max_pixels,min(max_pixels,desired/self.gain)))

    def observe(self,pixels,change):
        if not math.isfinite(change) or abs(change)>30:raise StopTest('excessive_observed_turn')
        if abs(pixels)<12 or abs(change)<1:return False
        measured=change/pixels
        if not .015<=abs(measured)<=.25:return False
        self.gain=measured if measured*self.gain<0 else .65*self.gain+.35*measured
        self.samples.append(dict(pixels=pixels,change_deg=change,measured_gain=measured,gain=self.gain))
        self.samples=self.samples[-20:]
        return True


def adaptive_turn(requested,heading,move,guard,sleep,model,max_corrections=2):
    guard();initial=heading()
    desired=max(-7.5,min(7.5,requested/16))
    current=initial
    records=[]
    for attempt in range(max_corrections+1):
        residual=desired-angle_delta(current,initial)
        if abs(residual)<=2:break
        pixels=model.pixels(max(-7.5,min(7.5,residual)))
        if not pixels:break
        guard();move(pixels,0);sleep(.15);guard()
        after=heading()
        change=angle_delta(after,current)
        learned=model.observe(pixels,change)
        records.append(dict(kind='turn_feedback',before=current,after=after,pixels=pixels,
                            requested_pixels=requested,attempt=attempt+1,change_deg=change,
                            learned=learned,gain=model.gain))
        current=after
    return dict(status='corrected' if abs(desired-angle_delta(current,initial))<=2 else 'correction_pending',
                requested_pixels=requested,desired_delta=desired,actual_delta=angle_delta(current,initial),
                residual=desired-angle_delta(current,initial),gain=model.gain,observations=records)
