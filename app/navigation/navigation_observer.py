"""Read-only position/heading stream. Invalid observations halt the session."""
import math


class NavigationObserver:
    def __init__(self, background):
        self.background = background
        self.previous_coordinate = None
        self.stopped = None
        self.samples = 0

    def observe(self, frame, coordinate):
        result = {'navigation_approved': False, 'coordinate': coordinate,
                  'direction_deg': None, 'sample': self.samples}
        if self.stopped:
            return dict(result, status=self.stopped)
        if (coordinate is None or len(coordinate) != 3
                or any(not isinstance(v, (int,float)) or not math.isfinite(v) for v in coordinate)):
            self.stopped = 'coordinate_unresolved'
            return dict(result, status=self.stopped)
        if self.previous_coordinate is not None:
            delta = [b-a for a,b in zip(self.previous_coordinate,coordinate)]
            result['coordinate_delta'] = delta
            if math.hypot(*delta[:2]) > 8 or abs(delta[2]) > 5:
                self.stopped = 'abnormal_coordinate_displacement'
                return dict(result, status=self.stopped)
        heading = self.background.observe(frame)
        result['heading'] = heading
        if heading['direction_deg'] is None:
            self.stopped = heading['status']
            return dict(result, status=self.stopped)
        self.previous_coordinate = list(coordinate)
        self.samples += 1
        return dict(result, status='observed_candidate', direction_deg=heading['direction_deg'])
