import base64, time


async def run(page):
    try:
        await page.set_viewport_size({"width": 1920, "height": 1080})
        base_url = "https://lovreski-dating.preview.emergentagent.com"
        receipt_path = "/app/test_reports/ui_receipt_iter13.png"
        with open(receipt_path, "wb") as f:
            f.write(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/lxL0RQAAAABJRU5ErkJggg=="))

        checkout_requests = []
        page.on("request", lambda request: checkout_requests.append(request.url) if "/api/coins/checkout" in request.url else None)

        await page.goto(base_url, wait_until="domcontentloaded")
        ts = int(time.time())
        user_payload = await page.evaluate("""async (ts) => {
            const r = await fetch('/api/auth/register', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email: `ui_recp_${ts}@lovreski.ru`, password: 'password123', name: 'UI Receipt Tester', gender: 'male', dob: '1998-05-15'})
            });
            return await r.json();
        }""", ts)
        user_token = user_payload["token"]
        initial_coins = user_payload["user"]["coins"]
        print(f"PASS: registered UI user {user_payload['user']['email']} with initial coins {initial_coins}")

        await page.evaluate("(token) => localStorage.setItem('lovreski_token', token)", user_token)
        await page.goto(base_url + "/premium", wait_until="networkidle")
        await page.locator('[data-testid="pkg-p200"]').wait_for(timeout=15000)
        print("PASS: Premium page loaded")

        await page.locator('[data-testid="pkg-p200"]').click(force=True)
        await page.wait_for_timeout(800)
        selected_class = await page.locator('[data-testid="pkg-p200"]').get_attribute("class")
        checkout_count = len(checkout_requests)
        check_svg_count = await page.locator('[data-testid="pkg-p200"] svg').count()
        assert "border-primary" in (selected_class or "") and check_svg_count >= 1, "package click did not visibly select p200"
        assert checkout_count == 0, f"package click unexpectedly called checkout API: {checkout_requests}"
        print("PASS: pkg-p200 click only visually selects; no checkout API call")

        phone = (await page.locator('[data-testid="sbp-phone"]').inner_text()).strip()
        recipient = (await page.locator('[data-testid="sbp-recipient"]').inner_text()).strip()
        note = (await page.locator('[data-testid="any-bank-note"]').inner_text()).lower()
        assert await page.locator('[data-testid="sbp-info-card"]').is_visible(), "SBP info card not visible"
        assert phone == "+79783069381", f"wrong SBP phone: {phone}"
        assert recipient == "Al Amin Dewan", f"wrong recipient: {recipient}"
        assert "any bank" in note, f"any bank note missing: {note}"
        assert await page.locator('[data-testid="btn-copy-phone"]').is_visible(), "copy phone button missing"
        bank_selector_count = await page.locator('[data-testid="bank-selector"], select[name*=bank], [id*=bank-selector]').count()
        assert bank_selector_count == 0, "bank selector still exists"
        print("PASS: SBP info card fields are correct and bank selector is absent")

        rule_texts = []
        for i in range(1, 7):
            locator = page.locator(f'[data-testid="rule-{i}"]')
            assert await locator.is_visible(), f"rule-{i} missing"
            rule_texts.append(await locator.inner_text())
        assert len(rule_texts) == 6, "not exactly 6 rule testids"
        print("PASS: rules-box displays rule-1 through rule-6 in order")

        await page.locator('[data-testid="btn-open-support"]').click(force=True)
        await page.locator('[data-testid="support-panel"]').wait_for(timeout=5000)
        assert await page.locator('[data-testid="btn-submit-receipt"]').is_disabled(), "submit should be disabled before file upload"
        await page.locator('[data-testid="receipt-file-input"]').set_input_files(receipt_path)
        await page.wait_for_timeout(800)
        assert await page.locator('[data-testid="btn-submit-receipt"]').is_enabled(), "submit should enable after file upload"
        await page.locator('[data-testid="receipt-message"]').fill("UI receipt upload test")
        await page.locator('[data-testid="btn-submit-receipt"]').click(force=True)
        await page.wait_for_timeout(1500)
        await page.locator('[data-testid="support-panel"]').wait_for(state="detached", timeout=10000)
        sub = await page.evaluate("""async () => {
            const r = await fetch('/api/support/my', {headers: {Authorization: 'Bearer ' + localStorage.getItem('lovreski_token')}});
            const data = await r.json();
            return data[0];
        }""")
        sub_id = sub["submission_id"]
        assert sub["status"] == "pending" and "receipt_data_url" not in sub, f"bad user submission state: {sub}"
        print(f"PASS: support panel uploaded receipt and created pending submission {sub_id}")

        admin_payload = await page.evaluate("""async () => {
            const r = await fetch('/api/auth/login', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email: 'admin@lovreski.ru', password: 'LovreskiAdmin2026!'})
            });
            return await r.json();
        }""")
        admin_token = admin_payload["token"]
        await page.evaluate("(token) => localStorage.setItem('lovreski_token', token)", admin_token)
        await page.goto(base_url + "/admin", wait_until="networkidle")
        await page.locator('[data-testid="admin-tab-support"]').wait_for(timeout=15000)
        badge_text = await page.locator('[data-testid="pending-badge"]').first.inner_text()
        assert int(badge_text) >= 1, f"pending badge missing/zero: {badge_text}"
        print(f"PASS: Verification tab visible with red pending badge count {badge_text}")

        await page.locator('[data-testid="admin-tab-support"]').click(force=True)
        await page.locator(f'[data-testid="pending-{sub_id}"]').wait_for(timeout=10000)
        assert await page.locator(f'[data-testid="receipt-img-{sub_id}"]').is_visible(), "receipt image not visible in pending card"
        pending_text = await page.locator(f'[data-testid="pending-{sub_id}"]').inner_text()
        assert "UI Receipt Tester" in pending_text and "ui_recp_" in pending_text and "UI receipt upload test" in pending_text, "pending card missing user/message details"
        await page.locator(f'[data-testid="btn-approve-{sub_id}"]').click(force=True)
        await page.locator('[data-testid="admin-modal"]').wait_for(timeout=5000)
        assert await page.locator('[data-testid="modal-coin-amount"]').is_visible(), "coin amount input missing"
        assert await page.locator('[data-testid="modal-reason"]').is_visible(), "reason input missing"
        await page.locator('[data-testid="modal-coin-amount"]').fill("33")
        await page.locator('[data-testid="modal-reason"]').fill("Payment verified via UI")
        preview_text = await page.locator('[data-testid="modal-preview"]').inner_text()
        assert "33" in preview_text and "Premium" in preview_text, f"bad live preview: {preview_text}"
        page.once("dialog", lambda dialog: dialog.accept())
        await page.locator('[data-testid="modal-confirm-approve"]').click(force=True)
        await page.locator('[data-testid="admin-modal"]').wait_for(state="detached", timeout=10000)
        print("PASS: admin Custom Coin Add modal credited coins and closed")

        await page.evaluate("(token) => localStorage.setItem('lovreski_token', token)", user_token)
        await page.goto(base_url + "/premium", wait_until="networkidle")
        await page.locator('[data-testid="coin-balance"]').wait_for(timeout=15000)
        balance_text = await page.locator('[data-testid="coin-balance"]').inner_text()
        assert str(initial_coins + 33) in balance_text, f"user balance did not update after approval: {balance_text}"
        print(f"PASS: user coin-balance updates after admin approve: {balance_text}")

        await page.evaluate("(token) => localStorage.setItem('lovreski_token', token)", admin_token)
        await page.goto(base_url + "/admin", wait_until="networkidle")
        await page.locator('[data-testid="admin-tab-settings"]').click(force=True)
        await page.locator('[data-testid="admin-sbp-current"]').wait_for(timeout=5000)
        assert await page.locator('[data-testid="admin-save-sbp"]').is_visible(), "settings Save SBP button missing"
        print("PASS: admin settings tab still renders masked SBP field and Save button")

        # Get error messages using specific selectors
        error_text = await page.evaluate("""() => {
        const errorElements = Array.from(document.querySelectorAll('.error, [class*="error"], [id*="error"]'));
        return errorElements.map(el => el.textContent).join(", ");
        }""")
        if error_text:
            print(f"Found error message: {error_text}")
        else:
            print("No error messages found on the page")

    except Exception as e:
        print(f"FAIL: frontend premium/admin flow failed: {e}")
        await page.screenshot(path="/app/test_reports/frontend_premium_flow_iter13_failure.jpg", quality=40, full_page=False)
        raise
