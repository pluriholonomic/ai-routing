import asyncio

import httpx

from orcap.http import Fetcher


def test_post_json_records_redacted_url_label_without_changing_request_target():
    seen = []

    async def run():
        async def handler(request):
            seen.append(str(request.url))
            return httpx.Response(200, json={"result": "ok"})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            fetcher = Fetcher(client)
            body = await fetcher.post_json(
                "https://rpc.example/secret-key",
                {"method": "eth_blockNumber"},
                record_url="configured:ORCAP_ETHEREUM_RPC_URL",
            )
        return body, fetcher.records

    body, records = asyncio.run(run())
    assert body == {"result": "ok"}
    assert seen == ["https://rpc.example/secret-key"]
    assert records[0]["url"] == "configured:ORCAP_ETHEREUM_RPC_URL"
