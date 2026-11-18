"""Transport fragmentation and strict receipt boundary, without timing guesses."""
import socket
import struct
import time
import pytest
from protection.context import JsonChannel, ProtocolError
from protection.runner import _before_deadline


def test_strict_receipt_boundary():
    assert _before_deadline(99,100)
    assert not _before_deadline(100,100)
    assert not _before_deadline(101,100)


def test_fragment_every_byte_and_timestamp():
    a,b=socket.socketpair(); channel=JsonChannel(a,'run')
    body=b'{"run_id":"run","request_id":1,"type":"FINAL","payload":[]}'
    wire=struct.pack('!I',len(body))+body
    before=time.monotonic_ns()
    for byte in wire[:-1]:
        b.send(bytes([byte]))
        assert channel.step() is None
    b.send(wire[-1:])
    msg,received=channel.step()
    assert msg['payload']==[]
    assert before<=received<=time.monotonic_ns()
    a.close();b.close()


@pytest.mark.parametrize('body',[b'not json',b'{"run_id":"run","run_id":"run"}',
    b'{"run_id":"other","request_id":0,"type":"FINAL","payload":[]}',
    b'{"run_id":"run","request_id":true,"type":"FINAL","payload":[]}'])
def test_bad_envelopes(body):
    a,b=socket.socketpair();channel=JsonChannel(a,'run')
    b.sendall(struct.pack('!I',len(body))+body)
    assert channel.step() is None
    with pytest.raises(ProtocolError): channel.step()
    a.close();b.close()


def test_incomplete_eof():
    a,b=socket.socketpair();channel=JsonChannel(a,'run')
    b.send(b'\x00');b.close()
    assert channel.step() is None
    with pytest.raises(EOFError):channel.step()
    a.close()
