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
- 2026-02 · **Priority Feeds + Install Banner + Auto-Session (Iter 24)** — 
  **F1 Discover/Search**: `/api/discover/feed` sorts candidates by `is_online DESC → distance ASC → last_seen DESC` with 4 tiers (Online+Nearby > Online > Offline+Nearby > Offline). 
  **F2 Home**: `/api/home/feed` HARD-filters by the viewer's `distance_km` when `distance_mode='limited'`, then ranks in 5 tiers (Online+Premium > Online+Nearby > Online (any, sub-sorted by `online_at DESC`) > Offline+Nearby > Offline). Prominent gradient PWA install banner on `/home` — mobile UA only, dismiss X persisted in `localStorage.lovreski_pwa_dismissed`. 
  **F3 Persistent auto-session**: new `LandingOrHome` wrapper; visiting `/` with a valid JWT auto-redirects to `/home`; logout clears the token and shows Landing again. 
  **Backend infra**: `is_online` derived from open WS + 60 s HTTP-active fallback; new stored fields `is_online` (bool), `online_at` (transition timestamp). New MongoDB indexes: `{is_online:-1, is_premium:-1}`, `last_active`, `online_at`, `{lat:1, lng:1}`. Iteration 24 backend 6/6 pytest pass + frontend 8/8 pass, zero bugs.
- 2026-02 · **Delete Message v1** — `DELETE /api/messages/{id}?scope=me|everyone`. `me` hides for viewer (idempotent `$addToSet` on `hidden_for`). `everyone` tombstones (sender-only, 1-h window, admins bypass), broadcasts `{type:"message_deleted"}` WS. Deleted bubbles render italic "Это сообщение было удалено"; reply preview shows "Исходное сообщение удалено". Iteration 23 backend 11/11 pass, frontend 100 %.
- 2026-02 · **Full-App Translation (DOM Auto-Translator)** — Iteration 22.
- 2026-02 · **Telegram-Style Chat + i18n v1** — Iteration 21.
- 2026-02 · **Complete Chat System v1** — Iteration 20.

## Deploy
Currently on Emergent (React + FastAPI + MongoDB). For amvera.cloud deployment, see `/app/backend/requirements.txt` + `/app/frontend/package.json`.
