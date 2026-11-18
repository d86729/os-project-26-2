import importlib
import numpy as np
import pytest
from protection.errors import InvalidScenarioError


def module():
    return importlib.import_module('protection.generation')


def oracle(n,seed):
    # Independent literal D-001 replay, not copied solver/generator output.
    r=np.random.default_rng(seed); xy=r.random((n,2)); edges={(0,1),(0,2),(1,2)}
    degree=[2,2,2]+[0]*(n-3)
    for v in range(3,n):
        available=list(range(v))
        for _ in range(2):
            weights=np.array([degree[u]/max(float(np.linalg.norm(xy[u]-xy[v])),1e-9)**3 for u in available])
            chosen=int(r.choice(available,p=weights/weights.sum()))
            edges.add((chosen,v)); degree[chosen]+=1; degree[v]+=1; available.remove(chosen)
    edges=sorted(edges); cap=r.integers(10,31,size=len(edges)); cost=r.integers(1,11,size=len(edges))
    pairs=[(u,v) for u in range(n) for v in range(n) if u!=v]
    selected=r.choice(n*(n-1),size=n,replace=False); amount=r.integers(5,21,size=n)
    return xy,edges,cap,cost,[pairs[i] for i in selected],amount


@pytest.mark.parametrize('n,seed',[(3,0),(6,0),(8,17)])
def test_reproducibility_and_rng_sequence(n,seed):
    g=module(); s=g.generate_scenario(n,seed); assert s==g.generate_scenario(n,seed)
    xy,edges,cap,cost,pairs,amount=oracle(n,seed)
    assert [(v.x,v.y) for v in s.nodes]==list(map(tuple,xy))
    assert [(e.u,e.v) for e in s.edges]==edges
    assert [e.capacity_mbps for e in s.edges]==list(cap)
    assert [e.cost for e in s.edges]==list(cost)
    assert [(d.source,d.target) for d in s.demands]==pairs
    assert [d.amount_mbps for d in s.demands]==list(amount)
    assert {(0,1),(0,2),(1,2)}<=set(edges)
    for v in range(3,n): assert len({u for u,w in edges if w==v})==2
    assert len(set(pairs))==n
    assert dict(s.environment)['numpy']==np.__version__
    assert dict(s.environment)['bit_generator']=='PCG64'


def test_current_degrees_and_distance_floor():
    g=module(); xy=np.array([[0.,0.],[0.,0.],[.5,0.],[0.,0.]])
    p=g.connection_probabilities(xy,[3,2,2,1],3,[0,1,2])
    assert np.isfinite(p).all() and p.sum()==pytest.approx(1)
    assert p[0]/p[1]==pytest.approx(1.5)
    assert p[0]>p[2]
    with pytest.raises(InvalidScenarioError):
        g.connection_probabilities(np.full((4,2),np.nan),[2]*4,3,[0,1,2])


@pytest.mark.parametrize('n,seed',[(2,0),(True,0),(6,True),(6,-1)])
def test_bad_generation_inputs(n,seed):
    with pytest.raises(InvalidScenarioError): module().generate_scenario(n,seed)
