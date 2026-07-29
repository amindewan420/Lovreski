#!/usr/bin/env python3
"""Focused frontend diagnostic for Google OAuth callback under React.StrictMode.

MOCKED: /api/auth/session is intercepted to return a successful OAuth exchange,
because no real one-time Google/Emergent session_id is available in this test
environment. The mock is used to prove the frontend calls the exchange endpoint
exactly once for one callback URL.
"""

import asyncio
import json
import os
from pathlib import Path

from playwright.async_api import async_playwright


FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://lovreski-dating.preview.emergentagent.com").rstrip("/")
RESULT_PATH = Path("/app/test_reports/auth_callback_strictmode_retest_iteration3_results.json")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        calls = []
        console_logs = []
        page.on("console", lambda msg: console_logs.append({"type": msg.type, "text": msg.text}))

        async def handle_session(route, request):
            calls.append({"post_data": request.post_data, "url_at_request": page.url})
            # Keep the request pending briefly so the test can verify the hash
            # was cleared before the async exchange returns.
            await asyncio.sleep(0.8)
            if len(calls) == 1:
                await route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({
                        "token": "mock_session_token_iteration3",
                        "user": {
                            "user_id": "user_mock_oauth_iteration3",
                            "email": "mock.oauth.iteration3@lovreski.ru",
                            "name": "Mock OAuth Iteration3",
                            "gender": "female",
                            "dob": "1998-01-01",
                            "is_admin": False,
                        },
                    }),
                )
            else:
                await route.fulfill(
                    status=401,
                    content_type="application/json",
                    body=json.dumps({"detail": "OAuth session invalid on duplicate exchange"}),
                )

        await page.route("**/api/auth/session", handle_session)
        await page.context.clear_cookies()
        await page.goto(FRONTEND_URL + "/#session_id=fake_session_iteration3", wait_until="domcontentloaded")

        for _ in range(20):
            if calls:
                break
            await page.wait_for_timeout(50)

        hash_during_pending = await page.evaluate("window.location.hash")
        url_during_pending = page.url

        await page.wait_for_url("**/home", timeout=8000)
        await page.wait_for_timeout(1000)

        token = await page.evaluate("localStorage.getItem('lovreski_token')")
        error_text = await page.evaluate("""() => {
            const errorElements = Array.from(document.querySelectorAll('.error, [class*="error"], [id*="error"]'));
            return errorElements.map(el => el.textContent).join(', ');
        }""")
        body_text = await page.locator("body").inner_text(timeout=3000)
        google_error_visible = "Не удалось войти через Google" in body_text

        result = {
            "frontend_url": FRONTEND_URL,
            "mocked_api": "/api/auth/session",
            "session_exchange_call_count": len(calls),
            "calls": calls,
            "hash_during_pending_exchange": hash_during_pending,
            "url_during_pending_exchange": url_during_pending,
            "final_url": page.url,
            "stored_token": token,
            "google_error_visible": google_error_visible,
            "error_text": error_text,
            "console_errors": [log for log in console_logs if log["type"] == "error"],
        }

        await page.goto(FRONTEND_URL + "/", wait_until="domcontentloaded")
        await page.wait_for_timeout(500)
        h1_texts = [t.strip() for t in await page.locator("h1").all_inner_texts()]
        result["landing_h1_texts"] = h1_texts
        result["landing_h1_exact_lovreski_only"] = h1_texts == ["Lovreski"]

        RESULT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(result, indent=2, ensure_ascii=False))

        await browser.close()

        assert len(calls) == 1, f"Expected exactly 1 /api/auth/session call, got {len(calls)}"
        assert hash_during_pending == "", f"Expected hash to be cleared while exchange was pending, got {hash_during_pending!r}"
        assert token == "mock_session_token_iteration3", f"Expected mocked token in localStorage, got {token!r}"
        assert result["final_url"].rstrip("/").endswith("/home"), f"Expected final URL /home, got {result['final_url']}"
        assert not google_error_visible, "Unexpected Google failure toast/text after successful exchange"
        assert h1_texts == ["Lovreski"], f"Expected only one H1 with Lovreski, got {h1_texts}"


if __name__ == "__main__":
    asyncio.run(main())