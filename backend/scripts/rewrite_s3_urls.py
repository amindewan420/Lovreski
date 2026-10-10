#!/usr/bin/env python3
"""One-time DB reference rewrite: /api/files/<id> → direct Timeweb S3 URLs.

Usage:
    python3 scripts/rewrite_s3_urls.py           # dry-run (shows what WOULD change)
    python3 scripts/rewrite_s3_urls.py --apply   # actually rewrite

Mapping source: the `s3_files` collection (created during GridFS→S3 migration),
keyed by the same 24-hex id that appears in /api/files/<id> URLs.

Also normalizes s3_files.public_url to the S3_PUBLIC_BASE_URL host
(s3.twcstorage.ru) for consistency.

Collections rewritten:
    users.photos[]                    — array of photo URLs
    messages.media_url                — chat media
    receipt_submissions.receipt_data_url
    refund_requests.receipt_data_url

Idempotent: URLs that don't match /api/files/<hex24> are left untouched.
"""
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

FILE_ID_RE = re.compile(r"^/api/files/([0-9a-f]{24})$")
APPLY = "--apply" in sys.argv


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    bucket = os.environ["S3_BUCKET"]
    base = os.environ.get("S3_PUBLIC_BASE_URL") or f"https://s3.twcstorage.ru/{bucket}"

    # Build id → public_url map; normalize stored public_url to the required host
    mapping = {}
    async for doc in db.s3_files.find({}, {"_id": 1, "s3_key": 1, "public_url": 1}):
        final_url = f"{base}/{doc['s3_key']}"
        mapping[doc["_id"]] = final_url
        if APPLY and doc.get("public_url") != final_url:
            await db.s3_files.update_one({"_id": doc["_id"]}, {"$set": {"public_url": final_url}})
    print(f"[map] {len(mapping)} s3_files docs (public_url host: {base})")

    def rewrite(url):
        if not isinstance(url, str):
            return url, False
        m = FILE_ID_RE.match(url)
        if not m:
            return url, False
        new = mapping.get(m.group(1))
        if not new:
            print(f"[warn] no s3 mapping for {url}")
            return url, False
        return new, True

    stats = {}

    # users.photos[]
    n = 0
    async for u in db.users.find({"photos.0": {"$exists": True}}, {"photos": 1}):
        photos, changed = [], False
        for p in u.get("photos") or []:
            np, c = rewrite(p)
            photos.append(np)
            changed = changed or c
        if changed:
            n += 1
            if APPLY:
                await db.users.update_one({"_id": u["_id"]}, {"$set": {"photos": photos}})
    stats["users"] = n

    # messages.media_url / receipts / refunds
    for coll, field in [("messages", "media_url"),
                        ("receipt_submissions", "receipt_data_url"),
                        ("refund_requests", "receipt_data_url")]:
        n = 0
        async for d in db[coll].find({field: {"$regex": "^/api/files/"}}, {field: 1}):
            new, changed = rewrite(d[field])
            if changed:
                n += 1
                if APPLY:
                    await db[coll].update_one({"_id": d["_id"]}, {"$set": {field: new}})
        stats[coll] = n

    mode = "APPLIED" if APPLY else "DRY-RUN"
    print(f"[{mode}] rewritten docs: {stats}")
    # Post-check: any /api/files refs left?
    left = 0
    for coll, field in [("messages", "media_url"), ("receipt_submissions", "receipt_data_url"), ("refund_requests", "receipt_data_url")]:
        left += await db[coll].count_documents({field: {"$regex": "^/api/files/"}})
    left += await db.users.count_documents({"photos": {"$elemMatch": {"$regex": "^/api/files/"}}})
    print(f"[post-check] /api/files references remaining: {left}")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
