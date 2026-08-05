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
- 2026-02 · **File & Media Storage (GridFS) — Iter 26** — All file uploads (profile photos, chat media, support receipts, refund receipts) now persist bytes to MongoDB **GridFS** (`fs.files` + `fs.chunks`) instead of embedding base64 in documents. New helpers `gridfs_put()`, `gridfs_url()`, `store_data_url_in_gridfs()`. New endpoints: `GET /api/files/{id}` streams files with correct MIME + `Cache-Control: immutable`; `POST /api/files/upload` (multipart, JWT-auth) generic upload with image auto-compression to JPEG. All existing upload paths route through the same code so old base64 flow is gone. One-shot `POST /api/admin/migrate/gridfs` (admin, idempotent) walks every legacy base64 blob in users/messages/receipt_submissions/refund_requests, moves it to GridFS, and rewrites the doc's URL. First backfill migrated **49 blobs** in 400 ms with 0 errors; DB invariants: 0 base64 URLs remaining. Backend 22/22 pytest pass, frontend 100 %, zero bugs. Notes: `/api/files/{id}` is intentionally unauthenticated so `<img>`/`<audio>`/`<video>` tags work — IDs are 24-hex opaque tokens (unenumerable); a per-owner ACL layer is a backlog item if any file kind becomes truly sensitive.
- 2026-02 · **Admin Panel v2 (Iter 25)** — deduct-coins, payments tab filters/search, moderation (warn/ban7/deactivate-permanent), legal docs CRUD, admin audit log. Backend 23/23 + frontend 100 %.
- 2026-02 · **Priority Feeds + Install Banner + Auto-Session (Iter 24)** — Discover 4-tier + Home 5-tier sorts, mobile PWA install banner, persistent auto-session. Backend 6/6 + frontend 8/8.
- 2026-02 · **Delete Message v1 (Iter 23)** — DELETE for me / everyone with 1-h window, WS-broadcast tombstone. Backend 11/11 + frontend 100 %.
- 2026-02 · **Full-App Translation (Iter 22)** — DOM auto-translator + LLM-cached batch.
- 2026-02 · **Telegram Chat + i18n v1 (Iter 21)** — full chat redesign. Backend 18/18 + frontend 38/38.
- 2026-02 · **Complete Chat System v1 (Iter 20)** — text/emoji/image/gift/voice/video + WS. Backend 13/13.

## Deploy
Currently on Emergent (React + FastAPI + MongoDB). For amvera.cloud deployment, see `/app/backend/requirements.txt` + `/app/frontend/package.json`.
