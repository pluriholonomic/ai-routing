"""Sniff the network traffic behind OpenRouter's client-rendered charts.

Loads a model page (Providers/Apps/Activity/Uptime tabs) plus the global
/rankings and /apps pages in headless Chromium and dumps every JSON-ish
response (url, status, body sample) so we can pin down the current internal
endpoints. Re-run whenever scrape_charts.py starts coming back empty —
these endpoints are unstable by nature.
"""

import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

SNIFF_TARGETS = [
    "https://openrouter.ai/z-ai/glm-4.6",
    "https://openrouter.ai/z-ai/glm-4.6/apps",
    "https://openrouter.ai/z-ai/glm-4.6/activity",
    "https://openrouter.ai/z-ai/glm-4.6/uptime",
    "https://openrouter.ai/rankings",
    "https://openrouter.ai/apps",
]

SKIP_HOST_FRAGMENTS = (
    "google",
    "gstatic",
    "clerk",
    "stripe",
    "sentry",
    "posthog",
    "intercom",
    "cloudflareinsights",
    "vercel-insights",
    "featurebase",
)


async def sniff(out_path: Path, headed: bool = False) -> list[dict]:
    captured: list[dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not headed)
        page = await browser.new_page()

        async def on_response(resp):
            url = resp.url
            if any(frag in url for frag in SKIP_HOST_FRAGMENTS):
                return
            ctype = resp.headers.get("content-type", "")
            if not ("json" in ctype or "text/x-component" in ctype or "/api/" in url):
                return
            try:
                body = await resp.text()
            except Exception:
                return
            captured.append(
                {
                    "page": page.url,
                    "url": url,
                    "status": resp.status,
                    "content_type": ctype,
                    "bytes": len(body),
                    "body_sample": body[:4000],
                }
            )

        page.on("response", on_response)

        for target in SNIFF_TARGETS:
            try:
                await page.goto(target, wait_until="domcontentloaded", timeout=60_000)
            except Exception as exc:
                print(f"goto failed for {target}: {exc}")
                continue
            # charts fetch after hydration; give them time to fire
            await page.wait_for_timeout(8_000)

        await browser.close()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(captured, indent=2))
    return captured


def main(out: str = "discovered_endpoints.json", headed: bool = False) -> None:
    captured = asyncio.run(sniff(Path(out), headed=headed))
    by_url: dict[str, int] = {}
    for c in captured:
        key = c["url"].split("?")[0]
        by_url[key] = by_url.get(key, 0) + 1
    print(f"captured {len(captured)} responses -> {out}")
    for url, n in sorted(by_url.items()):
        print(f"  {n:3d}x {url}")


if __name__ == "__main__":
    main()
