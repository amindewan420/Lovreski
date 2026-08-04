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
- 2026-02 · **Telegram-Style Chat + Global i18n v1** — Complete redesign per spec: white background, right-aligned sent bubbles (#DCF2FF light-blue), left-aligned received (white + grey border), HH:MM timestamps, ✓/✓✓ read receipts, centered date separators (`Сегодня`/`Вчера`/`5 августа 2026`). Composer: single `+` button opens a 6-tile attachment tray (Эмодзи/Подарки/Галерея/Файл/Видео/Переводчик), mic↔send button swap, auto-grow textarea. New EmojiPanel with 6 tabs (Faces / Love / Gestures / Activities / Food / Travel). New GiftPanel: 18 gifts (`/api/gifts`), 3-col colorful gradient tiles, per-gift cost (5-30), confirm modal. New `file` message kind (5 coins). Updated cost matrix: text=1, emoji=2, image=5, file=5, voice=5, video=10. **Free-user hard-block**: first 2 messages (any kind) free per chat; message #3+ needs coins else `/api/chats/{id}/send` returns 402 with `{blocked: true}` and the input becomes readonly with a `block-popup` (buy coins / close) that navigates to /premium. **App-wide i18n**: new `/api/i18n/{lang}` endpoint LLM-translates the 82-key Russian dictionary (I18N_BASE_RU) via gpt-4o-mini, caches per-language in `db.i18n_cache` keyed by SHA-256 version hash. Front-end `I18nProvider` + `t()` + `LanguageSheet` (60+ languages grouped Global/Europe/Asia/Americas, search). Selected language persists on the user profile (`language_pref`) and in localStorage. i18n applied to Shell nav, Chats list, Chat room, Settings. Iteration 21 backend 18/18 + frontend 38/38 pass.
- 2026-02 · **Complete Chat System v1** — text/emoji/image/gift/voice/video message types with per-kind coin costs. Real-time WebSocket `/api/ws?token=<JWT>` (single-process pub/sub). Locked-message paywall for free users. `/api/chat/media` upload endpoint. AI Translate button in composer. Iteration 20 backend 13/13 pass.

## Deploy
Currently on Emergent (React + FastAPI + MongoDB). For amvera.cloud deployment, see `/app/backend/requirements.txt` + `/app/frontend/package.json`.
