"""Class 1 reads: what the disposable fetch refuses before it ever connects."""
import pytest


async def test_a_nat64_mapped_public_address_is_public_and_a_mapped_private_one_is_not(monkeypatch):
    """An IPv6-only ISP resolves www.example.com to 64:ff9b::<its IPv4>."""
    from familyos.execution import disposable

    async def fake(host):
        v4 = {"public.example": "93.184.216.34", "inside.example": "10.0.0.5"}[host]
        packed = __import__("ipaddress").ip_address(v4).packed
        mapped = __import__("ipaddress").IPv6Address(b"\x00\x64\xff\x9b" + b"\x00" * 8 + packed)
        return [str(mapped)]

    monkeypatch.setattr(disposable, "_resolve", fake)
    await disposable._public_addresses("public.example")
    with pytest.raises(disposable.Refused):
        await disposable._public_addresses("inside.example")


# ---- DNS rebinding and the body cap -------------------------------------------------

def _recording_client(handler_body=None, status=200, headers=None):
    import httpx
    seen = []

    def handler(request):
        seen.append(request)
        if handler_body is None:
            return httpx.Response(status, headers=headers or {}, text="<title>ok</title>")
        return httpx.Response(status, headers=headers or {}, content=handler_body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)
    client.seen = seen
    return client


async def test_the_connection_goes_to_the_address_that_was_vetted_not_to_a_second_answer(monkeypatch):
    """DNS rebinding: the name answers with a public address when it is checked
    and with the metadata address when asked again. The fetch must resolve once
    and connect to what it vetted."""
    from familyos.execution import disposable
    answers = [["93.184.216.34"], ["169.254.169.254"], ["127.0.0.1"]]
    calls = []

    async def resolve(host):
        calls.append(host)
        return answers[min(len(calls) - 1, len(answers) - 1)]

    monkeypatch.setattr(disposable, "_resolve", resolve)
    client = _recording_client()
    page = await disposable.read("https://example.com/x", frozenset({"example.com"}), client=client)
    await client.aclose()
    assert page.title == "ok" and page.url == "https://example.com/x"
    assert len(calls) == 1
    assert [r.url.host for r in client.seen] == ["93.184.216.34"]
    assert client.seen[0].headers["host"] == "example.com"
    assert client.seen[0].extensions["sni_hostname"] == "example.com"


async def test_a_name_with_any_inside_address_is_refused_before_connecting(monkeypatch):
    from familyos.execution import disposable

    async def resolve(host):
        return ["93.184.216.34", "127.0.0.1"]

    monkeypatch.setattr(disposable, "_resolve", resolve)
    client = _recording_client()
    with pytest.raises(disposable.Refused):
        await disposable.read("https://example.com/x", frozenset({"example.com"}), client=client)
    await client.aclose()
    assert client.seen == []


async def test_every_redirect_hop_is_resolved_and_vetted_again(monkeypatch):
    from familyos.execution import disposable
    table = {"example.com": ["93.184.216.34"], "www.example.com": ["10.0.0.7"]}

    async def resolve(host):
        return table[host]

    monkeypatch.setattr(disposable, "_resolve", resolve)
    client = _recording_client(status=302, headers={"location": "https://www.example.com/in"})
    with pytest.raises(disposable.Refused):
        await disposable.read("https://example.com/x", frozenset({"example.com", "www.example.com"}), client=client)
    await client.aclose()
    assert [r.url.host for r in client.seen] == ["93.184.216.34"]


async def test_an_endless_body_is_cut_at_the_cap_without_being_buffered(monkeypatch):
    import httpx

    from familyos.execution import disposable

    async def resolve(host):
        return ["93.184.216.34"]

    monkeypatch.setattr(disposable, "_resolve", resolve)
    sent = 0
    chunk = b"a" * 65536

    class Endless(httpx.AsyncByteStream):
        async def __aiter__(self):
            nonlocal sent
            while sent < 10 * 1024 * 1024 * 1024:   # would be 10 GiB if it were ever read to the end
                sent += len(chunk)
                yield chunk

    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, stream=Endless())))
    page = await disposable.read("https://example.com/x", frozenset({"example.com"}), client=client)
    await client.aclose()
    assert page.bytes == disposable.MAX_BYTES and page.truncated
    assert sent <= disposable.MAX_BYTES + 2 * len(chunk)
