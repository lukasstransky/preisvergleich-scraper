"""One-off diagnostic: load a SPAR category page with the configured browser,
wait, then report what the page actually contains. Run on the Pi:

    source venv/bin/activate
    export PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium
    python debug_spar.py
"""
import asyncio
from playwright.async_api import async_playwright
from scrapers.browser import launch_kwargs

URL = "https://www.spar.at/produktwelt/obst-gemuese"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(**launch_kwargs())
        context = await browser.new_context(user_agent=USER_AGENT)
        page = await context.new_page()
        print(f"Loading {URL} ...")
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)

        # Try to accept cookies if present
        for sel in ['button:has-text("Akzeptieren")', 'button:has-text("Alle akzeptieren")']:
            try:
                await page.click(sel, timeout=3000)
                print(f"Clicked cookie button: {sel}")
                break
            except Exception:
                pass

        await page.wait_for_timeout(8000)  # generous settle time for the slow Pi

        grid = await page.query_selector("div.spar-plp__grid")
        tiles = await page.query_selector_all("article.product-tile")
        print(f"grid present: {grid is not None}")
        print(f"product tiles: {len(tiles)}")
        print(f"page title: {await page.title()}")

        body = (await page.inner_text("body"))[:800]
        print("---- visible body text (first 800 chars) ----")
        print(body)
        print("---------------------------------------------")

        await page.screenshot(path="debug_spar.png", full_page=True)
        print("Saved screenshot to debug_spar.png")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
