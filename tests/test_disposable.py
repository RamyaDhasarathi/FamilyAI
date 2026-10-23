"""Class 1 reads: what the disposable fetch refuses before it ever connects."""
import pytest


def test_a_nat64_mapped_public_address_is_public_and_a_mapped_private_one_is_not(monkeypatch):
    """An IPv6-only ISP resolves www.example.com to 64:ff9b::<its IPv4>."""
    import socket

    from familyos.execution import disposable

    def fake(host, port):
        v4 = {"public.example": "93.184.216.34", "inside.example": "10.0.0.5"}[host]
        packed = __import__("ipaddress").ip_address(v4).packed
        mapped = __import__("ipaddress").IPv6Address(b"\x00\x64\xff\x9b" + b"\x00" * 8 + packed)
        return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", (str(mapped), 0, 0, 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake)
    disposable._host_is_public("public.example")
    with pytest.raises(disposable.Refused):
        disposable._host_is_public("inside.example")
