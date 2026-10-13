"""Shared time, step and height budgets for a bounded multi-point experiment."""
from dataclasses import replace
import time
from app.navigation.single_point_test import run_single,StopTest,Limits


def run_short_route(points,read,down,up,turn,guard,limits=Limits(),clock=time.monotonic,sleep=time.sleep,first_point=2):
    if len(points)<2:raise ValueError('短路线需要至少两个点')
    began=clock();segments=[];steps=0;height=None
    def checked_read():
        nonlocal height
        point=read()
        if point is not None:
            if height is None:height=point[2]
            elif abs(point[2]-height)>limits.max_height_change:raise StopTest('height_changed')
        return point
    status='arrived'
    for index,(start,target) in enumerate(zip(points,points[1:]),first_point):
        remaining=limits.max_seconds-(clock()-began)
        if remaining<=0:status='time_limit';break
        if steps>=limits.max_steps:status='step_limit';break
        segment=run_single(start,target,checked_read,down,up,turn,guard,
                           replace(limits,max_seconds=remaining,max_steps=limits.max_steps-steps),
                           clock,sleep,correct_sign=False)
        segment['point']=index
        segments.append(segment);steps+=segment['steps']
        if segment['status']!='arrived':status=segment['status'];break
    return dict(status=status,steps=steps,elapsed=clock()-began,segments=segments,
                completed_points=[r['point'] for r in segments if r['status']=='arrived'],
                navigation_approved=False)
