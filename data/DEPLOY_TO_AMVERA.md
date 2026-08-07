# Lovreski — Deploying to Amvera Cloud (with DB migration)

Your app on Emergent runs against a **managed MongoDB** that lives inside the
preview environment. When you deploy to Amvera Cloud you need **your own**
MongoDB, and then move this DB over. Here's the full path.

## What's in your backup

`lovreski_db_backup.tar.gz` (9.3 MB compressed, 14.5 MB uncompressed) contains:

| Collection            | Docs | Notes                                    |
| --------------------- | ---: | ---------------------------------------- |
| users                 |  198 | Accounts, profiles, coin balances        |
| messages              |  153 | All chat history                         |
| transactions          |   83 | Coin purchases / SBP receipts audit      |
| likes                 |   67 | Swipes (like/pass/superlike)             |
| fs.files + fs.chunks  |   66 + 93 | **All uploaded media in GridFS**    |
| admin_audit           |   53 | Admin action log                         |
| i18n_dynamic          |  444 | Cached UI-string translations            |
| i18n_cache            |    7 | Cached base-dictionary translations      |
| notifications         |   32 | In-app notifications                     |
| receipt_submissions   |   25 | SBP payment receipts (Premium & Coins)   |
| refund_requests       |    9 | Refund tickets                           |
| password_reset_otps   |    8 | Password reset OTPs (auto-expire)        |
| sessions              |    1 | OAuth sessions                           |
| settings              |    1 | Encrypted SBP phone + coin packages      |
| matches               |    1 | Mutual likes                             |
| reports               |    1 | User-abuse reports                       |
| legal_docs            |    0 | Legal pages (Terms, Refund policy…)      |

## Step 1 — Provision MongoDB for production

You have three good options; pick one:

**A. Amvera's built-in MongoDB add-on** (easiest)
1. In Amvera dashboard → **Databases** → **Add MongoDB**.
2. Copy the connection URI (looks like `mongodb://user:pass@host:27017/db?authSource=admin`).
3. Paste it into your app's `MONGO_URL` secret.

**B. MongoDB Atlas free tier** (external, works from anywhere)
1. Create a free M0 cluster at https://www.mongodb.com/cloud/atlas.
2. Add `0.0.0.0/0` to Network Access (or Amvera's egress IPs if you can find them).
3. Create a DB user; copy the connection string.

**C. Self-hosted MongoDB on a VPS**  → your call.

## Step 2 — Restore your data

Once you have a production MongoDB URI:

```bash
# On any machine with mongodb-database-tools installed:
MONGO_URI="mongodb://user:pass@host:27017/?authSource=admin" \
DB_NAME="lovreski" \
./restore_db.sh lovreski_db_backup.tar.gz
```

The script:
- Extracts the tarball
- Runs `mongorestore` with `--drop` (replaces any existing data)
- Renames the source DB `test_database` → `lovreski` on the fly

You should see `✅ Restore complete.` in ~10-20 seconds.

## Step 3 — Configure Amvera secrets

In Amvera dashboard → **Secrets**, paste one entry per key from
`/app/backend/.env.example`. The critical ones:

| Key                  | Where to get it                                        |
| -------------------- | ------------------------------------------------------ |
| `MONGO_URL`          | Step 1 above                                           |
| `DB_NAME`            | `lovreski` (match `restore_db.sh --DB_NAME`)           |
| `JWT_SECRET`         | `openssl rand -hex 32`                                 |
| `SBP_ENCRYPT_KEY`    | `openssl rand -base64 32` — **NEW keys break stored encrypted phone**, run `PUT /api/admin/settings` after deploy to re-set the SBP phone |
| `SBP_PHONE`          | `+79780369381`                                         |
| `ADMIN_EMAIL`        | e.g. `admin@lovreski.ru`                               |
| `ADMIN_PASSWORD`     | a strong password                                      |
| `EMERGENT_LLM_KEY`   | Optional — powers /api/translate + i18n batches        |
| `CORS_ORIGINS`       | Your production front-end URL, comma-separated         |

## Step 4 — Push code & build on Amvera

1. If you haven't yet: **Save to GitHub** from the Emergent chat input.
2. In Amvera → **New Project** → connect the repo.
3. Amvera reads `/amvera.yaml` (already has `meta.toolchain: docker`) →
   builds `/Dockerfile` → runs `uvicorn main:app --port 8000`.
4. First deploy takes ~4-8 minutes (node build + Python deps).
5. Health probe hits `/health` — must return `{"status":"ok"}` before Amvera
   marks the service live.

## Step 5 — Post-deploy sanity check

```bash
# Replace with your Amvera-issued domain
BASE="https://your-app.amvera.io"

curl -s "$BASE/health"                          # → {"status":"ok"}
curl -s "$BASE/api/health"                      # → {"ok":true}
curl -s "$BASE/api/coins/packages" | head       # sbp_phone + packages
```

Log in with the admin credentials → visit `/admin` → confirm your users, chats
and transactions are all there.

## Regenerating the backup

If you want a fresh dump anytime (e.g. after more testing on Emergent):

```bash
cd /app/data
mongodump --uri="mongodb://localhost:27017" --db=test_database --out=./dump
tar -czf lovreski_db_backup.tar.gz dump && rm -rf dump
```

That's it. The file lives under `/app/data/` which is persistent.
