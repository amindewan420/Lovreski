"""Focused Playwright QA script for ProfilePage live completion percentage.

This is the same script body run through the browser automation tool. It uses a
fresh registered user, injects lovreski_token, edits About Me, then selects
three interests so the backend completion formula crosses the >=3 interests
threshold without reloading the page.
"""

script = r'''
try:
    await page.set_viewport_size({"width": 390, "height": 844})
    responses = []
    page.on("response", lambda r: responses.append({"url": r.url, "status": r.status, "method": r.request.method}) if "/api/profile" in r.url or "/api/auth" in r.url else None)

    await page.goto("https://lovreski-dating.preview.emergentagent.com/", wait_until="domcontentloaded")
    register_result = await page.evaluate("""async () => {
        const ts = Date.now();
        const email = `profiletest_ui_bugfix_${ts}@lovreski.ru`;
        const res = await fetch('/api/auth/register', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({email, password: 'password123', name: 'UI Bugfix QA', gender: 'female', dob: '1998-05-15'})
        });
        const data = await res.json();
        if (!res.ok) throw new Error(`register failed ${res.status}: ${JSON.stringify(data)}`);
        localStorage.setItem('lovreski_token', data.token);
        return {email, tokenLength: data.token.length};
    }""")
    print(f"Registered fresh UI user: {register_result}")

    await page.goto("https://lovreski-dating.preview.emergentagent.com/profile", wait_until="domcontentloaded")
    await page.locator('[data-testid="completion-pct"]').wait_for(state="visible", timeout=15000)
    await page.wait_for_timeout(500)
    before_text = await page.locator('[data-testid="completion-pct"]').inner_text()
    before = int(before_text.replace('%', '').strip())
    print(f"Initial completion-pct: {before}%")

    about = page.locator('[data-testid="input-about"]')
    await about.scroll_into_view_if_needed()
    await about.click()
    await about.fill(f"Автосохранение completion check {register_result['email']}")
    async with page.expect_response(lambda r: "/api/profile/me/stats" in r.url and r.status == 200, timeout=15000):
        await about.evaluate("el => el.blur()")
    await page.wait_for_function("""(prev) => {
        const el = document.querySelector('[data-testid="completion-pct"]');
        if (!el) return false;
        return parseInt(el.textContent.replace('%','').trim(), 10) > prev;
    }""", arg=before, timeout=15000)
    after_about_text = await page.locator('[data-testid="completion-pct"]').inner_text()
    after_about = int(after_about_text.replace('%', '').strip())
    print(f"After About blur completion-pct: {after_about}%")

    await page.locator('[data-testid="btn-open-interests"]').scroll_into_view_if_needed()
    await page.locator('[data-testid="btn-open-interests"]').click()
    await page.wait_for_timeout(200)
    await page.locator('[data-testid="sheet-interests"]').wait_for(state="visible", timeout=10000)
    for tid in ['interest-Kisses', 'interest-Hugs', 'interest-Flirt']:
        async with page.expect_response(lambda r: "/api/profile/me/stats" in r.url and r.status == 200, timeout=15000):
            await page.locator(f'[data-testid="{tid}"]').click(force=True)
        print(f"Selected {tid}; current pct={await page.locator('[data-testid="completion-pct"]').inner_text()}")
    await page.wait_for_function("""(prev) => {
        const el = document.querySelector('[data-testid="completion-pct"]');
        if (!el) return false;
        return parseInt(el.textContent.replace('%','').trim(), 10) > prev;
    }""", arg=after_about, timeout=15000)
    after_interests_text = await page.locator('[data-testid="completion-pct"]').inner_text()
    after_interests = int(after_interests_text.replace('%', '').strip())
    print(f"After selecting 3 interests completion-pct: {after_interests}%")

    stats_gets = [r for r in responses if "/api/profile/me/stats" in r["url"]]
    puts = [r for r in responses if r["url"].endswith('/api/profile') and r["method"] == 'PUT']
    print(f"Observed profile PUTs={len(puts)}, stats GETs={len(stats_gets)}")
    if not (after_about > before and after_interests > after_about and len(stats_gets) >= 4):
        raise AssertionError(f"Completion did not update live as expected: before={before}, after_about={after_about}, after_interests={after_interests}, stats_gets={len(stats_gets)}")

    error_text = await page.evaluate("""() => {
    const errorElements = Array.from(document.querySelectorAll('.error, [class*="error"], [id*="error"]'));
    return errorElements.map(el => el.textContent).join(", ");
    }""")
    if error_text:
        print(f"Found error message: {error_text}")
    else:
        print("No error messages found on the page")
    print("PASS frontend live completion update verified without reload")
except Exception as e:
    print(f"FAIL frontend live completion update test: {e}")
    raise
'''