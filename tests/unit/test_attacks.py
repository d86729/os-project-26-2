import importlib
from dataclasses import replace
import math
import pytest
from protection.models import Node, Edge, Demand, Scenario


def module(): return importlib.import_module('protection.attacks')


def test_segment_interior_zero_length_and_boundary():
    a=module()
    assert a.segment_distance((.5,.1),(0.,0.),(1.,0.))==pytest.approx(.1)
    assert a.segment_distance((.5,.5),(.5,.5),(.5,.5))==0
    assert a.segment_distance((1.,1.),(0.,0.),(0.,0.))==pytest.approx(2**.5)
    boundary=.15+1e-9
    assert a.is_hit((.5,boundary),(0.,0.),(1.,0.))
    assert not a.is_hit((.5,math.nextafter(boundary,math.inf)),(0.,0.),(1.,0.))
    assert a.segment_distance((2.,0.),(0.,0.),(1.,0.))==1


def test_grid_midpoint_rounding_and_protection(path_scenario):
    a=module(); p=a.prepare_attacks(path_scenario)
    xy=[(c.x,c.y) for c in p.candidates]
    assert xy==sorted(set(xy))
    assert {(i/5,j/5) for i in range(6) for j in range(6)}<=set(xy)
    c=next(c for c in p.candidates if (c.x,c.y)==(.3,.1))
    assert c.damaged_edge_ids==(0,)
    assert a.surviving_ids(path_scenario,c,())==(1,)
    assert a.surviving_ids(path_scenario,c,(0,))==(0,1)
    assert len(path_scenario.nodes)==3  # attacks never delete nodes
    assert p.policy_version=='evaluation-v2' and p.preparation_seconds>=0
    units=a.unique_coordinates([(0.0000000005,0.),(0.,0.),(0.0000000015,0.)])
    assert units==((0.,0.),(.000000002,0.))


def test_crossing_is_not_a_node():
    s=Scenario(tuple(Node(i,*p) for i,p in enumerate(((.1,.1),(.9,.9),(.1,.9),(.9,.1)))),
               (Edge(0,0,1,10,1),Edge(1,0,2,10,1),Edge(2,2,3,10,1)),
               tuple(Demand(i,*p,5) for i,p in enumerate(((0,1),(1,0),(2,3),(3,2)))),0)
    p=module().prepare_attacks(s)
    c=next(c for c in p.candidates if (c.x,c.y)==(.5,.5))
    assert c.damaged_edge_ids==(0,2)
    assert len(s.nodes)==4 and all((n.x,n.y)!=(.5,.5) for n in s.nodes)
