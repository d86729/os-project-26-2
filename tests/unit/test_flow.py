import importlib
from dataclasses import replace
from types import SimpleNamespace
import time
import pytest
from protection.models import Node, Edge, Demand, Scenario
from protection.errors import EvaluationError, DeadlineExceeded


def module(): return importlib.import_module('protection.flow')


def test_shared_direction_and_independent_reverse(path_scenario,hand_example):
    # Forward demands 0->2 and 0->1 share 10. Reverse 2->0 has its own 10.
    r=module().maximum_delivery(path_scenario,(0,1))
    assert r.delivered_mbps==pytest.approx(hand_example.expected_delivered)
    assert r.delivery_units==hand_example.expected_units
    assert r.diagnostics.certified_lower==r.diagnostics.certified_upper==20
    assert r.diagnostics.certificate_status=='certified'


def test_split_paths_and_demand_caps():
    # Diamond: 0->3 splits across two capacity-10 paths to deliver 20;
    # 1->0, 2->0, 3->1 each use independent reverse capacity and deliver 5.
    s=Scenario(tuple(Node(i,*xy) for i,xy in enumerate(((.1,.5),(.5,.1),(.5,.9),(.9,.5)))),
               tuple(Edge(i,*uv,10,1) for i,uv in enumerate(((0,1),(0,2),(1,3),(2,3)))),
               tuple(Demand(i,*d) for i,d in enumerate(((0,3,20),(1,0,5),(2,0,5),(3,1,5)))),0)
    r=module().maximum_delivery(s,(0,1,2,3))
    assert r.delivered_mbps==pytest.approx(35)
    assert r.delivery_units==1000000
    assert r.diagnostics.certified_lower==35


def test_disconnected_network_is_real_zero(path_scenario):
    r=module().maximum_delivery(path_scenario,())
    assert r.delivered_mbps==0 and r.delivery_units==0
    assert r.diagnostics.certified_lower==r.diagnostics.certified_upper==0


def test_lp_failure_is_not_zero(path_scenario,monkeypatch):
    f=module()
    monkeypatch.setattr(f,'linprog',lambda *a,**k: SimpleNamespace(success=False,status=4,message='injected solver failure'))
    with pytest.raises(EvaluationError,match='injected solver failure'): f.maximum_delivery(path_scenario,(0,1))


def test_expired_deadline(path_scenario):
    with pytest.raises(DeadlineExceeded): module().maximum_delivery(path_scenario,(0,1),deadline=time.monotonic()-1)


def test_nonfinite_and_residual_failure(path_scenario,monkeypatch):
    f=module(); real=f.linprog
    def corrupt(*a,**k):
        r=real(*a,**k); r.x[0]=float('nan'); return r
    monkeypatch.setattr(f,'linprog',corrupt)
    with pytest.raises(EvaluationError): f.maximum_delivery(path_scenario,(0,1))
    def violate(*a,**k):
        r=real(*a,**k); r.x[0]=100.; return r
    monkeypatch.setattr(f,'linprog',violate)
    with pytest.raises(EvaluationError): f.maximum_delivery(path_scenario,(0,1))
