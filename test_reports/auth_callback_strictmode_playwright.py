"""Diagnostic frontend test for Emergent OAuth callback under React StrictMode.

MOCKED: The /api/auth/session response is intercepted because a real Google
OAuth session_id is not available to the testing agent. This is used only to
count frontend callback exchange attempts.
"""

async def run(page):
    import json

    calls = []

    async def handle_session(route, request):
        calls.append(request.post_data or "")
        if len(calls) == 1:
            await route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({
                    "token": "mock_session_token",
                    "user": {
                        "user_id": "user_mock_oauth",
                        "email": "mock.oauth@lovreski.ru",
                        "name": "Mock OAuth",
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
                body=json.dumps({"detail": "OAuth session invalid"}),
            )

    await page.set_viewport_size({"width": 1920, "height": 1080})
    base_url = page.url.rstrip("/")
    await page.route("**/api/auth/session", handle_session)
    await page.context.clear_cookies()
    await page.goto(base_url + "/#session_id=fake_session_id", wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)
    token = await page.evaluate("localStorage.getItem('lovreski_token')")
    print(json.dumps({"session_exchange_calls": len(calls), "final_url": page.url, "stored_token": token}, ensure_ascii=False))
    if len(calls) != 1:
        raise AssertionError(f"AuthCallback exchanged the same OAuth session_id {len(calls)} times; expected exactly 1")