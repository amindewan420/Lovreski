# Lovreski PRD

## Original Problem Statement
Build a complete, production-ready dating web app called "Lovreski" — mobile-first PWA, Russian language, 12 steps covering auth, profiles, home grid, discover swipe, likes with 3 tabs, chat with virtual gifts/reply/translation, premium & coin (SBP + admin approval), settings, admin panel with analytics, demo profiles, bottom nav, security & performance.

## Adapted Stack (Emergent platform)
- Frontend: React 19 + Tailwind + shadcn/ui + Framer Motion + Sonner + Recharts (PWA-enabled)
- Backend: FastAPI + Motor (MongoDB)
- Auth: JWT (email/password) + Emergent Google OAuth (session cookies)
- LLM Translation: emergentintegrations (GPT-4o-mini) via Emergent Universal Key
- Payment: SBP mock flow with admin approval (as specified)

## User Personas
1. **Guest** — visits landing, signs up
2. **Standard user** — free tier, 2 free msgs per chat, browses feed
3. **Premium user** — Premium status via admin-approved SBP payment; unlimited chat
4. **Admin** — approves payments, moderates reports, deactivates users, sees analytics

## Core Requirements (implemented in MVP v1 · 2026-02)
- ✅ Step 1 Auth (email/password + Google OAuth via Emergent)
- ✅ Step 2 Profile: photo header, editable fields, popularity meter, coin card, height slider, dropdowns (goal/relationship/kids/smoking/alcohol), interests picker (10 max) with categories, location auto-detect
- ✅ Step 3 Home: 6-profile grid, opposite-gender filter, like/pass buttons, PWA install banner, priority ordering
- ✅ Step 4 Discover: swipe cards (Framer Motion), full profile view with photo gallery, like/pass/star buttons
- ✅ Step 5 Likes: 3 tabs (received/sent/matches) with counts
- ✅ Step 6 Chat: text/emoji/gift messages, reply preview, emoji picker, virtual gifts picker (8 gifts), locked-message paywall, in-line AI translation
- ✅ Step 7 Premium: 4 coin packages, SBP form, admin approval flow, transaction history
- ✅ Step 8 Settings: personal info, discovery (show me / age / distance), notifications toggles, auto-translate, legal (4 docs), PWA install
- ✅ Step 9 Admin Panel: dashboard stats, analytics charts (daily/monthly/yearly · revenue/count toggle), payments table with approve/reject, reports aggregation, user management, deactivate
- ✅ Step 10 Demo profiles: 16 Russian demo users seeded automatically
- ✅ Step 11 Bottom nav 5 tabs
- ✅ Step 12 Security: JWT, CORS, MongoDB indexes, custom user_id UUID, cookie httpOnly for OAuth

## Deferred (backlog)
- P1: Real SBP webhook integration (requires Sberbank business account)
- P1: Photo verification via face-detection
- P1: Cloudinary uploads (photos/voice/video are Base64 in Mongo now)
- P1: Spam / Report flow with admin warn/ban actions
- P2: Push notifications via FCM (requires Firebase setup)
- P2: End-to-end message encryption (currently server-stored plaintext, JWT-protected)
- P2: Rate limiting via Redis
- P2: Native mobile apps (Flutter as originally requested)
- P2: Refactor server.py (1789 lines) into modular routers
- P2: PWA install prompt on Settings & Home
- P2: Email/SMS notifications via Resend/Twilio for refund status & matches

## Changelog
- 2026-02 · **Cloudinary Storage Backend (Iter 39)** — New `/app/backend/storage.py`: uploads via `cloudinary` SDK 1.46.3 in `asyncio.to_thread`, folder `lovreski/<kind>/`, `resource_type` auto (image / video [audio counts as video] / raw), access type **public for profile_photo, authenticated for chat media + receipts**. Unified `storage_put()` in server.py routes ALL uploads (profile photo, chat media, receipts, refunds, generic /files/upload) to Cloudinary when `CLOUDINARY_*` env vars are set — **falls back to GridFS on any failure or missing creds, so the app never breaks**. `cloud_files` Mongo collection maps our 24-hex file id → Cloudinary public_id; `/api/files/<id>` resolves cloud_files first (same access gate — owner/admin/participant/HMAC sig — then 302-redirects to a per-request Cloudinary-signed delivery URL), else streams from GridFS. One-time migration `POST /api/admin/migrate/cloudinary` uploads every GridFS file to Cloudinary keyed by the SAME id (zero reference rewriting, old URLs keep working), then removes the GridFS copy. Storage widget shows per-store breakdown (GridFS vs Cloudinary) + migrate button (visible only when configured). Cleanup cron now also destroys orphaned Cloudinary assets. **Verified in fallback mode**: all upload paths, access matrix (403 anon/stranger, 200 participant/admin/signed), 503 migration guard, widget row. ⚠️ Awaiting real credentials — user pasted placeholders.
- 2026-02 · **Signed-URL Silent Refresh (Iter 38)** — Chat media no longer breaks after the 10-min signature TTL. New `useSignedMediaUrl(url)` hook in ChatRoomPage: extracts the file id, proactively re-mints via `GET /api/files/<id>/signed` every 8 min, and retries once on media `onError` (expired 403). Rendering extracted into a `MediaBubble` component (image/audio/video/file) so hooks are legal inside the message map. Verified live: tampered a signature in the DOM → bubble re-minted and recovered automatically (`naturalWidth` restored, fresh sig in src). New data-testids: `media-img|audio|video|file-<message_id>`.
- 2026-02 · **Match Celebration Banner (Iter 37)** — New shared component `/src/components/lovreski/MatchCelebration.jsx`: full-screen dark overlay with brand-pink radial glow, "ЭТО МЭТЧ! / Взаимная симпатия" staggered entrance, overlapping photos animating in from both sides with a spring-pulsing heart, "Написать сообщение" (→ `/chats/<id>`) + "Продолжить поиск" + X close. Wired into all 3 like call sites (DiscoverPage swipe, HomePage grid, OtherProfilePage) via `data.match` → `setMatchUser(data.target)`. Also fixed pre-existing broken `/u/<id>` navigations → `/profile/<id>` in ChatRoomPage header, AdminPage report view, and the FCM match-push URL in push.py.
- 2026-02 · **Signed File URLs (Iter 36)** — `/api/files/{id}` no longer serves sensitive files anonymously. Access model: `profile_photo` public; everything else requires a valid short-lived HMAC signature (`?exp&sig`, 10 min TTL via `FILE_URL_TTL_SECONDS`, secret `FILE_SIGN_SECRET` falling back to JWT_SECRET) OR an authorized session (owner / admin / chat participant via message lookup). Helpers `sign_file_url`/`verify_file_sig` live in server.py. Signing happens at serialization: `get_messages`, `_do_send_message` (WS broadcast + send response), `_decorate_msg` all emit signed `media_url` while DB stores plain URLs. New `GET /api/files/{id}/signed` mints URLs (owner/admin/participant rules). Admin endpoints `/admin/support/pending`, `/admin/support/history`, `/admin/refunds` pre-sign `receipt_data_url` so the admin panel needed zero frontend changes. Verified matrix: anon receipt 403, stranger JWT 403, tampered/expired sig 403, participant/admin/signed 200, profile photos still public.
- 2026-02 · **Storage Cleanup Job (Iter 35)** — Orphaned GridFS purge. New `routers/cron.py` with: `run_storage_cleanup()` (scans users.photos / messages.media_url / receipt_submissions / refund_requests for `/api/files/<id>` references, deletes `fs.files`+`fs.chunks` docs older than `STORAGE_RETENTION_DAYS=7` days that aren't referenced, writes a report to `storage_cleanup_runs`); `POST /api/cron/storage-cleanup` (Bearer `WEBHOOK_CRON_SECRET`, constant-time compare, idempotent via `cron_runs.run_id`, acks 200 immediately and runs in `asyncio.create_task`); `POST /api/admin/storage/cleanup` (admin manual sync trigger) + `GET /api/admin/storage/cleanup-log`. `.emergent/crons.yml` schedules nightly purge at 03:00 UTC. Widget gained "Очистить сейчас" button + last-run line. Verified live: first run deleted 10 orphaned files, manual re-run idempotent (0 deleted), storage 79→69 files.
- 2026-02 · **Admin GridFS Storage Widget (Iter 34)** — New `GET /api/admin/storage` endpoint aggregates `fs.files` by `metadata.kind` (profile_photo / chat_image / chat_voice / chat_video / chat_file / support_receipt / refund_receipt / other), falls back to content-type prefix when kind absent. Returns `{total_files, total_bytes, by_kind[], by_content_type[]}` sorted by bytes desc. Dashboard now shows a card with: stacked color-coded bar, total size+count header, and per-kind table with Russian labels ("Чат — видео", "Фото профиля", "Чеки оплаты", etc). Human-readable bytes via `fmtBytes` (Б/КБ/МБ/ГБ). New data-testids: `admin-storage-widget`, `admin-storage-total`, `storage-row-<kind>`. Refreshes with existing 10s admin polling.
- 2026-02 · **Server.py Modular Router Refactor (Iter 33)** —
  Split the 2668-line monolith `/app/backend/server.py` into **13 route modules under `/app/backend/routers/`** (`auth.py`, `profile.py`, `discover.py`, `chat.py`, `files.py`, `coins.py`, `notifications.py`, `reports.py`, `admin.py`, `i18n.py`, `demo.py`, `misc.py`, `__init__.py`). Pattern used: `server.py` defines all shared primitives (db, api APIRouter, Pydantic models, constants, security helpers, WSManager, GridFS, user_public, _push_notification, _do_send_message, _try_auto_confirm, I18N_BASE_RU) in the top ~830 lines, then imports all routers at line 847 — this triggers their `@api.X` decorators to register routes on the shared `api` router (no behaviour change).
  **Result:** `server.py` 2668 → 935 lines. Largest router: `admin.py` (541 lines). Zero route changes, zero API surface changes.
  **Testing agent iter-33** caught 4 real refactor regressions during pytest (missing imports in router files: `datetime` in auth.py, `timedelta` in demo.py, `uuid/base64/_compress_image_data_url` in files.py, shadowing redef in profile.py) and fixed them automatically. Final: **backend 36/36 pytest green, frontend 100%, WhatsApp reply + Push Settings sections unchanged**.
- 2026-02 · **Push Notifications (FCM Web Push) — Iter 32** —
  **New `/app/backend/push.py` module** implementing FCM sending via `firebase-admin==7.5.0` with fail-safe design: if `FIREBASE_PROJECT_ID` + service-account credential are missing, every `send_*` call is a no-op. Presence-aware: `should_push()` returns `False` when the user's WebSocket is currently connected via `ws_manager.is_online(uid)` OR their `last_active` is within 60 s.
  **4 event triggers wired**:
  1. `_do_send_message` → `notify_chat_message` (recipient only, if idle) — snippet respects message kind ("🖼 Фото", "🎁 Подарок", etc.).
  2. `like_user` (when match created) → `notify_match(both users)`.
  3. `_push_notification` (existing helper for payment/warn/refund) now also fires an FCM.
  4. `submit_receipt` + `report_user` → `notify_admin_new_submission("receipt"|"report")` broadcasts to all admins.
  **New endpoints** (all `/api/push/*`): `GET /status` (returns `{configured, vapid_public_key, token_count}`), `POST /token`, `DELETE /token`, `POST /test`.
  **DB**: new `push_tokens` collection with unique index on `token` (upserted per browser/device, stale tokens auto-purged on `UnregisteredError`).
  **Frontend**: added `firebase@12.18.0`, `/src/lib/firebase.js`, `/src/hooks/usePushNotifications.js`, `/public/firebase-messaging-sw.js` (config passed via `?firebaseConfig=<base64>` query param since CRA doesn't process env vars in `/public/`). Foreground `onMessage` → sonner toast with Open-in-place action.
  **Settings page**: new "PUSH-УВЕДОМЛЕНИЯ" section with 3 UI states — pending-admin (shows explanation if server not configured), unsupported (browser), and configured (shows Enable / Test / Disable buttons).
  **New i18n keys**: `chat.you`, `settings.section.push`, `settings.push_enable`, `settings.push_disable`, `settings.push_on`, `settings.push_test`, `settings.push_pending`, `settings.push_unsupported`, plus 4 more.
  **Env vars to fill later** (`/app/backend/.env`): `FIREBASE_PROJECT_ID`, `FIREBASE_VAPID_PUBLIC_KEY`, `FIREBASE_SERVICE_ACCOUNT_JSON`. And `/app/frontend/.env`: `REACT_APP_FIREBASE_*` (7 vars).
  Testing agent iter-32: backend 9/9, frontend 100%. Zero regressions.
- 2026-02 · **WhatsApp-style Reply to Message (Iter 31)** — 
  **1) Swipe-right gesture**: new touch handlers on each message row (`onMsgTouchStart/Move/End`) with axis-lock (pan-y wins <6px, then x locks). Swiping past 55 px sets that message as the reply target (with `navigator.vibrate(15)` haptic). A small `.swipe-reply-hint` pill with the Reply icon fades in on the leading edge proportional to `dx`. Bubbles translate with `transform: translateX(dx)` and snap back via `.chat-msg-row transition`.
  **2) Enhanced reply preview above composer**: WhatsApp-style card — 4-px vertical accent bar (sky when replying to own message, emerald when replying to peer), sender name (`chat.you` = "Вы", else peer name), 2-line clamp snippet (with media-kind fallback like "🖼 Галерея"), X-close button. `chatReplyBarIn` slide-up animation.
  **3) Quoted box inside reply bubbles**: now a `<button>` tappable — calls `scrollToMessage(originalId)` which `scrollIntoView({block:'center'})` and applies a `.chat-msg-flash` (sky-tinted background pulse) to the target for 1.2 s. Deleted-original still gracefully shows `chat.original_deleted`.
  **4) Action sheet (formerly delete-only)**: long-press / right-click now opens a proper **action-sheet** with three actions: **Reply** (primary, primary/10 bg), Delete for me, Delete for everyone (when eligible). `chatSheetIn` animation reused. State renamed `deleteTarget → actionTarget`.
  **New i18n key**: `chat.you = "Вы"`.
  **CSS additions**: `@keyframes chatReplyBarIn`, `@keyframes chatMsgFlash`, `.chat-msg-flash`, `.swipe-reply-hint`, `.chat-msg-row`.
  Testing agent iter-31: 11/12 flows green, only swipe unverifiable via Playwright touch dispatch (code path reviewed and correct).
- 2026-02 · **WhatsApp-style Chat Enhancements (Iter 29-30)** — 
  **1) Attachment tray now a slide-up modal**: previously an always-visible inline row, now hidden by default. Tapping `+` mounts a full-screen modal with backdrop, drag-handle, X-close, and a 4-column grid of 7 items. Backdrop tap or X closes with a smooth `chatSheetIn` keyframe. 
  **2) Location option added**: new `tray-location` button uses `navigator.geolocation.getCurrentPosition` (with permission-denied handling in Russian) and sends the result as a text message containing an OpenStreetMap link (`https://www.openstreetmap.org/?mlat=...&mlon=...`). 
  **3) Scroll-to-bottom FAB**: floating circular chevron-down button appears when the user scrolls up more than 120 px from the latest message; tap smooth-scrolls back to bottom; FAB disappears once bottom is reached. 
  **Layout fix (iter 30)**: wrapper `minHeight:'100vh'` → `height:'100dvh'` so the message list actually overflows internally (was scrolling the body instead — the FAB never fired). `100dvh` chosen for iOS dynamic-viewport safety. 
  All 13 iter-29 features green after iter-30 retest, zero bugs.
- 2026-02 · **Amvera Deploy Bundle Hardening (Iter 27-28)** — added `meta.toolchain: docker` in amvera.yaml; made `yarn.lock` optional via wildcard COPY so the build works whether the lockfile is committed or not. Testing agent 11/11 (iter 27) + 8/8 (iter 28) pass.
- 2026-02 · **File & Media Storage (GridFS) — Iter 26** — All uploads persist to MongoDB GridFS. Backend 22/22 + frontend 100 %.
- 2026-02 · Iter 20-25 chat/i18n/admin features (see prior entries).

## Deploy
Currently on Emergent (React + FastAPI + MongoDB). For amvera.cloud deployment, see `/app/backend/requirements.txt` + `/app/frontend/package.json`.
