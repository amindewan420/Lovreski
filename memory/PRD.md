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
- 2026-02 · **Smart Cyclic Discovery + Filter Sync (Iter 45)** — Search section semantics rebuilt per spec: `_base_candidates` now takes an `exclude` swipe-type tuple — Discover excludes ONLY likes (skips cycle back), Home excludes ONLY passes (liked stay with ✓ flag). `discover_feed` now hard-filters distance when `distance_mode='limited'` (same rule as Home; no-geo profiles excluded). New endpoints: `GET /api/search/refresh` (pool refresh used by both auto + manual refresh) and `DELETE /api/like/<id>` (unlike — profile re-enters the pool). Frontend: DiscoverPage auto-cycles when deck runs low (skipped profiles return), manual refresh button (`btn-refresh-feed`) in header, and a filter-signature watcher (`lib/filterSync.js` — Settings stamps `lovreski_filters_sig` on every save; DiscoverPage re-fetches on mount/focus when it changed). Advisory fix: `/demo/seed` now admin-only (403 for regular users). Testing agent iter-37: **5/5 new backend + 8/8 regression + frontend cycle & refresh verified** (3 previously-passed users confirmed cycling back; liked users never reappear).
- 2026-02 · **Home Feed Like-Retention + Backend Filters (Iters 43-44)** — Change 1: liking from Home no longer removes the card. Backend `home_feed` now uses `_base_candidates(exclude_liked=False)` (only passes/blocked excluded) and flags each profile `liked: bool`; ProfileCard like button becomes disabled "✓ Лайкнуто" (slate-100/slate-400) when liked; HomePage `doLike` maps the card to `liked:true` instead of filtering it out. Duplicate likes impossible (idempotent upsert + disabled UI). Discover swipe deck unchanged (still excludes swiped). Change 2: Home feed hard-filters on the BACKEND by age range (`_base_candidates` age filter from iter 42) and distance (`distance_mode='limited'` + `distance_km` → profiles without geo or beyond range excluded from the query result entirely). Testing agent iter-35: backend 8/8 (liked flag, idempotent like, 20–25 age band, 10 km hard filter, real-time refilter, discover regression). Found + iter-36 verified fix for a pre-existing CRITICAL bug: ProfileCard name/distance overlay lacked `pointer-events-none` and covered the action buttons. Final: frontend 7/7.
- 2026-02 · **Dual-Handle Age Range Slider (Iter 42)** — Replaced the two number inputs in Settings → Поиск → Возраст with a Radix dual-thumb slider (18–85, step 1, `minStepsBetweenThumbs=1`). Live label "Возраст: min–max" above the slider updates while dragging; pink (#E6005C primary) highlighted track between thumbs, grey outside; auto-saves via `PUT /api/profile` on `onValueCommit` (drag release). Shared `ui/slider.jsx` upgraded to render one thumb per value (single-thumb callers unaffected). Backend: `_base_candidates` now hard-filters by `age_min`/`age_max` (was missing entirely) so Home + Discover feeds respect the range; `update_profile` clamps to 18–85 and 400s on min>max. Verified: drag → save toast → reload persists 27–60; cross-drag never inverts values; feed ages all within range; clamp 10/99 → 18/85; invalid 60/30 → 400.
- 2026-02 · **S3 URL Rewrite Fix (Iter 41)** — User-reported bug: after GridFS→S3 migration DB still held `/api/files/<id>` paths instead of direct S3 URLs. Fixed by: (1) idempotent script `/app/backend/scripts/rewrite_s3_urls.py` mapping `s3_files._id → public_url` and rewriting `users.photos[]`, `messages.media_url`, `receipt_submissions.receipt_data_url`, `refund_requests.receipt_data_url` (+ normalizes public_url host to `s3.twcstorage.ru` via S3_PUBLIC_BASE_URL); (2) `storage_put()` now returns `{"url": <direct S3 public URL>, "file_id"}` so all NEW uploads (photos, chat media, receipts, refunds, generic) store direct S3 URLs in DB — call sites in profile/chat/coins/admin/files updated; (3) nightly cleanup cron now recognizes direct S3 URLs (`lovreski/<key>` regex) as references so it never deletes live files. Testing agent iter-34: **8/8 backend + frontend verified — 0 /api/files refs remain, 90+ photos return 200 from s3.twcstorage.ru, new uploads produce direct S3 URLs, chat images render from S3, cleanup preserves referenced files. Bug RESOLVED.**
- 2026-02 · **Timeweb S3 Storage (replaces Cloudinary) — Iter 40 LIVE** — Stripped the Cloudinary SDK (uninstalled, all code paths removed) and swapped in Timeweb S3 via `boto3==1.43.56`. New `/app/backend/storage.py` uploads to Timeweb (`endpoint=https://s3.timeweb.cloud`, bucket `600faa0a-...-ea330`, region `ru-1`, path-style, sig v4), keys organized as `lovreski/<kind>/<uuid>.<ext>`. **Critical fix during integration**: Timeweb rejects `put_object` calls that include `ACL` and `Metadata` headers with `SignatureDoesNotMatch` — removed both (public bucket policy handles ACL anyway, DB holds metadata). Mongo collection `cloud_files` → `s3_files`; endpoint `/admin/migrate/cloudinary` → `/admin/migrate/s3`; AdminPage widget labels swap to "S3 (Timeweb)". `/api/files/<id>` now 302-redirects to the public Timeweb URL after passing the same HMAC-signed-URL / owner / admin / chat-participant access gate. **Migration complete**: 76 GridFS files moved to S3, 0 failed, 0 skipped; GridFS is now empty; S3 holds 77 files · 29.2 MB in the bucket. Verified live: profile photo upload → direct Timeweb URL (288 B JPEG); existing receipts still resolve via same `/api/files/<id>?exp&sig` URL (302 → S3 → 200 image); anon strip-query = 403; stranger chat media = 403. ⚠️ Public bucket = anyone with the direct S3 URL can access; UUID keys stay unguessable but if you need receipts/chat strictly private, switch to a private bucket and I'll flip to presigned S3 URLs.
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

## 2026-06 — Iteration 38: Admin-configured Push + Map Location Sharing
- Firebase config moved from .env to Admin Panel → tab "Push" (`PushConfigTab.jsx`): upload service-account JSON (encrypted in `settings{key:"firebase"}`, validated by real firebase_admin init before saving), Web config fields (Project ID auto-filled, API key, App ID, Sender ID, VAPID, auth domain) with Firebase Console hints, status pill, device count, admin announcement broadcast (in-app + background push).
- `push.py` now DB-backed (named firebase_admin app, re-inits on config change), data-only messages, per-user prefs (`notif_push`: messages/likes/matches/visits/announcements) checked before each send.
- Triggers: new like (`discover.py`), match, chat message (offline only), profile visit (`profile_visits`, 6h cooldown), announcements.
- Frontend: `lib/firebase.js` loads config from `GET /api/push/config`; `PushManager.jsx` (global) silently re-syncs FCM token on login, foreground toasts, SW tap-to-navigate via postMessage, one-time enable prompt. SW updated.
- Fixed: `notif_push` toggles were never saved (missing in ProfileUpdate) — now whitelisted & persisted.
- Chat location: `LocationShare.jsx` (Leaflet/OSM picker with draggable pin, place name, safety note), `kind:"location"` messages (1 coin), expire after 24h or immediately on block; expired pins stripped server-side in messages + chat list. Chat list preview also no longer leaks locked/deleted content.
- Tested: iteration_38 (backend 21/21, frontend all flows) + follow-up fixes verified via curl.

## Backlog
- P1: Voice hold-to-record button in chat
- P2: Admin panel mobile polish

## 2026-06 — Iteration 39/40: Separate secure Admin Login
- Admin panel credentials ONLY from env `ADMIN_EMAIL` / `ADMIN_PASSWORD` (+ `JWT_SECRET`, no code defaults).
- `POST /api/admin/login` (hmac compare, 1s delay on fail, lockout 5 fails/IP + 20 global → 15 min, IP = rightmost X-Forwarded-For hop), `GET /api/admin/verify-token`, `POST /api/admin/logout` (revokes `admin_sessions.jti`).
- Admin JWT: `type:"admin"`, no exp, bound to a fingerprint of the env creds (changing .env logs out all admin devices). `verify_admin` (= `require_admin`) guards all admin routes + `/demo/seed`; user tokens rejected.
- Normal `/api/auth/login` no longer has the special admin branch; added per-email lockout (10 fails → 15 min). The is_admin user account has no admin powers on user endpoints (chat delete, files, paywall).
- Frontend: `/admin/login` (AdminLogin.jsx), `/admin/dashboard` wrapped in `AdminProtectedRoute` (silent verify, auto-login), `lib/adminApi.js` (token key `lovreski_admin_token`, 401 → login), red "Выйти" logout button. Removed admin buttons from Settings & Profile; Landing never routes to /admin.
- Tested: iteration_39 + iteration_40 (backend 49/49, frontend 100%).

## Known / backlog
- Receipts in S3 are public-read URLs (pre-existing design) — consider private bucket + presigned URLs.
- /api/auth/login reveals whether an email is registered (404 vs 401) — product UX choice.

## 2026-06 — Iteration 41: Admin mobile polish + admin push + unread badges
- Mobile admin: `AdminNav.jsx` — bottom tab bar (Главная/Чеки/Возвраты/Жалобы/Ещё sheet) <768px, top pills on desktop; tab in URL `?tab=`; sticky compact header; payments as cards on mobile; users search (`GET /api/admin/users?q=`, newest first).
- Badges: refund_requests & reports get `is_read:false`; `GET /api/admin/refund-requests/unread-count`, `GET /api/admin/complaints/unread-count`, `POST .../mark-read`; `useAdminBadges` polls every 12s, marks read when tab open; Verification badge = pending receipts.
- Admin device push: tokens stored under `push_tokens.user_id="__admin_panel__"` (`POST/DELETE /api/admin/push/token`, `POST /api/admin/push/test-self`); alerts for new receipts, refunds, complaints, admin login success & lockout (tap opens the right tab).
- Direct push to one user (`POST /api/admin/push/user/{id}`, Push button on user cards) + in-app notification; push history log (`push_log`, `GET /api/admin/push/history`) for direct + announcements.
- Payment result notifications to users now in Russian (receipt approve/reject, refund decision).
- Tested: iteration_41 (backend 22/22, frontend 100%).

## 2026-06 — Iteration 42: PDF receipts in Admin Panel
- Root causes: viewer used `<img>` for PDFs; S3 uploads had `Content-Encoding: aws-chunked` (boto3 default checksums) — fixed via `request_checksum_calculation="when_required"` + `ContentDisposition=inline`.
- `ReceiptViewer.jsx`: full-screen in-panel viewer (react-pdf/pdf.js canvas for PDF, image preview), loading % indicator, 'File not found' / 'Unable to load receipt' errors, Open-in-new-tab + Download; `ReceiptThumb` with PDF tile + "Скачать" fallback; used in Verification (pending + history) and Refund Requests.
- `GET /api/admin/receipt-file?src=&download=` — admin-only same-origin streaming proxy for S3 receipts (404 File not found).
- Upload validation (client `lib/receiptFile.js` + server `validate_receipt_data_url`): JPG/PNG/WEBP/PDF, ≤10 MB, PDF magic bytes. Refund form now accepts PDF.
- Tested: iteration_42 (backend 20/20, frontend all flows incl. 9 MB PDF, mobile).

## 2026-06 — Iteration 43: Legal docs live on user side
- Root cause: Settings → Legal used hard-coded frontend texts, never the API.
- Built-ins moved to `backend/legal_defaults.py`: terms-of-service, privacy-policy, payment-rules, refund-policy, community-guidelines, security-tips (aliases terms/privacy/payment/refund/security/guidelines/community).
- `/api/legal` + `/api/legal/{slug}` merge admin docs over built-ins (no-store); admin PUT on built-in creates override, DELETE reverts; built-ins undeletable.
- Admin Правовые tab shows "Встроенный" / "Свой · заменяет встроенный" / "Свой" badges + revert. User side renders Markdown (`LegalDoc.jsx`, react-markdown); refund-policy page includes refund form.
- Tested: iteration_43 (backend 14/14, frontend 100%).

## 2026-06 — Iteration 44: Consistent in-app translation (chat + legal)
- Shared engine `backend/translation.py` (Emergent LLM gpt-4o-mini, JSON-array batches of 40, cache `content_translations` by (lang, sha(text)), fail-open to original, ISO language whitelist).
- `POST /api/translate/batch` (chat), `/api/translate` now uses the same engine. `GET /api/legal?lang=` and `/api/legal/{slug}?lang=` return translated titles/body (Markdown split by paragraphs) + originals; admin save pre-translates into all users' languages; startup prewarm.
- Frontend `useChatTranslation`: whole thread translated in one pass (chunked, applied together), live WS messages auto-translate, pending bubbles pulse + "Переводим…" pill, per-bubble "Показать оригинал" toggle, reply quotes + location place translated. Legal pages show translated doc with original toggle. i18n loader guarded against stale responses.
- Tested: iteration_44 (backend 11/11, frontend 100%).

## 2026-06 — Iteration 45: Chat media viewer & downloads
- `GET /api/chat/media-file/{message_id}` (participants only) streams S3/legacy attachments same-origin (inline / ?download=1).
- `ChatMediaViewer.jsx`: full-screen viewer — images with pinch/double-tap/zoom buttons (react-zoom-pan-pinch), PDFs rendered in-app (shared `PdfPages.jsx`), loading %, error state with retry, Download.
- Save: phones → Web Share sheet with the image file ("Save Image"/"Save to Photos"); otherwise browser download (toasts "сохранено в галерею"/"в «Загрузки»"). Native MediaStore/Photos APIs not available on web.
- File bubbles: PDF badge opens viewer; download icon on every file. Leaflet map isolated so it doesn't overlay viewers.
- Tested: iteration_45 (backend 9/9, frontend 100%).

## 2026-06 — Iteration 46: Delete for me (both users), bulk delete, copy
- Backend: `_delete_error`/`_apply_delete` helpers; any participant can delete any message for themselves (`hidden_for`); `POST /api/messages/delete-bulk {message_ids, scope}` all-or-nothing (everyone = own & ≤1h); chat list keeps chats whose messages are all hidden, preview = latest visible.
- Frontend `MessageActions.jsx`: long-press/right-click sheet [Copy (text only)] [Reply] [Select] + Delete for me / for everyone; selection mode (checkmarks, "Выбрано: N", Cancel, trash) → confirm dialog with Delete for me / for everyone (when all own & fresh); toasts "Сообщения удалены", "Сообщение скопировано" (clipboard API + execCommand fallback). Ghost-tap guard (sheet ignores taps 400ms, touchend preventDefault after long-press).
- Tested: iteration_46 (backend 13/13, frontend 95% → ghost-click + animation fixed afterwards, self-verified).
- Also: media viewer error state now has real "Повторить" retry; media proxy respects hidden_for.

## 2026-06 — Iteration 47: Location sharing with coins + 5-min links
- Location share costs 2 coins ALWAYS (atomic `$gte` deduction, 402 → toast + redirect /premium; client pre-check too).
- Message `location` = {lat,lng,place,live,token,updated_at}; `location_expires_at` = +5 min. `GET /api/loc/{token}` (public, 410 expired), `POST /api/location/{mid}/update` (live sender, WS `location_update`), `/stop`.
- Frontend: picker with cost/balance, "Транслировать моё местоположение (5 мин)" (watchPosition via `lib/liveLocation.js`, 8s throttle) or custom pin; bubble with LIVE badge, mm:ss countdown, stop button, copy link; tap → server-validated → Google Maps directions + distance toast; public `/l/:token` page. Free OSM map kept (no Google SDK).
- Tested: iteration_47 (backend 11/11, frontend 100%); place names now shown verbatim.
