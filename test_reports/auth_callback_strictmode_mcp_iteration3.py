"""MCP Browser-compatible AuthCallback StrictMode retest.

MOCKED: /api/auth/session is intercepted to return a successful OAuth exchange,
because no real one-time Google/Emergent session_id is available in this test
environment. Intended to be run by the browser automation harness with a `page`.
"""


async def run(page):
    import asyncio
    import json

    await page.set_viewport_size({"width": 1920, "height": 1080})
    calls = []

    async def handle_session(route, request):
        calls.append({"post_data": request.post_data, "url_at_request": page.url})
        await asyncio.sleep(0.8)
        if len(calls) == 1:
            await route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({
                    "token": "mock_session_token_iteration3_mcp",
                    "user": {
                        "user_id": "user_mock_oauth_iteration3_mcp",
                        "email": "mock.oauth.iteration3.mcp@lovreski.ru",
                        "name": "Mock OAuth Iteration3 MCP",
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
    await page.evaluate("localStorage.clear()")
    base_url = page.url.rstrip("/")
    await page.goto(base_url + "/#session_id=fake_session_iteration3_mcp", wait_until="domcontentloaded")
    for _ in range(20):
        if calls:
            break
        await page.wait_for_timeout(50)

    hash_during_pending = await page.evaluate("window.location.hash")
    url_during_pending = page.url
    await page.wait_for_url("**/home", timeout=8000)
    home_url = page.url
    await page.wait_for_timeout(1000)
    token = await page.evaluate("localStorage.getItem('lovreski_token')")
    body_text = await page.locator("body").inner_text(timeout=3000)
    google_error_visible = "Не удалось войти через Google" in body_text

    await page.goto(base_url + "/", wait_until="domcontentloaded")
    await page.wait_for_timeout(500)
    h1_texts = [t.strip() for t in await page.locator("h1").all_inner_texts()]

    result = {
        "session_exchange_call_count": len(calls),
        "calls": calls,
        "hash_during_pending_exchange": hash_during_pending,
        "url_during_pending_exchange": url_during_pending,
        "home_url_observed": home_url,
        "stored_token": token,
        "google_error_visible": google_error_visible,
        "landing_h1_texts": h1_texts,
    }
    print("RESULT_JSON=" + json.dumps(result, ensure_ascii=False))

    assert len(calls) == 1, f"Expected exactly 1 /api/auth/session call, got {len(calls)}"
    assert hash_during_pending == "", f"Expected hash cleared before exchange completed, got {hash_during_pending!r}"
    assert token == "mock_session_token_iteration3_mcp", f"Expected mocked token in localStorage, got {token!r}"
    assert not google_error_visible, "Unexpected Google failure toast/text after successful exchange"
    assert h1_texts == ["Lovreski"], f"Expected only H1 'Lovreski', got {h1_texts}"