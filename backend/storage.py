"""Timeweb S3 storage backend for Lovreski.

Fail-safe design: when S3_* env vars are missing or S3 is unreachable, every
upload gracefully falls back to GridFS so the app never breaks.

Timeweb S3 config:
  S3_ENDPOINT=https://s3.timeweb.cloud
  S3_BUCKET=<bucket-id>
  S3_REGION=ru-1
  S3_ACCESS_KEY_ID=<access-key>
  S3_SECRET_ACCESS_KEY=<secret-key>
  S3_PUBLIC_BASE_URL=<optional override; auto = <endpoint>/<bucket>>

Keys inside the bucket are organized by kind:
  lovreski/<kind>/<uuid>.<ext>
"""
from __future__ import annotations
import asyncio
import logging
import os
import uuid
from typing import Optional

logger = logging.getLogger("lovreski.storage")

PUBLIC_KINDS = {"profile_photo"}


def is_configured() -> bool:
    return bool(
        os.environ.get("S3_ENDPOINT")
        and os.environ.get("S3_BUCKET")
        and os.environ.get("S3_ACCESS_KEY_ID")
        and os.environ.get("S3_SECRET_ACCESS_KEY")
    )


def _bucket() -> str:
    return os.environ["S3_BUCKET"]


def _endpoint() -> str:
    ep = os.environ["S3_ENDPOINT"].rstrip("/")
    if not ep.startswith("http"):
        ep = "https://" + ep
    return ep


def _public_base() -> str:
    override = (os.environ.get("S3_PUBLIC_BASE_URL") or "").rstrip("/")
    if override:
        return override
    return f"{_endpoint()}/{_bucket()}"


def _client():
    """Build a boto3 S3 client pointed at Timeweb (or any S3-compatible endpoint)."""
    import boto3
    from botocore.config import Config
    return boto3.client(
        "s3",
        endpoint_url=_endpoint(),
        region_name=os.environ.get("S3_REGION", "ru-1"),
        aws_access_key_id=os.environ["S3_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"],
        # Timeweb uses path-style URLs (bucket as a path segment, not vhost)
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def _ext_from_ct(content_type: str) -> str:
    ct = (content_type or "").lower()
    return {
        "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png",
        "image/webp": ".webp", "image/gif": ".gif",
        "video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov",
        "audio/webm": ".webm", "audio/mpeg": ".mp3", "audio/wav": ".wav",
        "audio/ogg": ".ogg", "audio/mp4": ".m4a",
        "application/pdf": ".pdf",
    }.get(ct, "")


async def upload_bytes(content: bytes, filename: str, content_type: str,
                       owner_id: Optional[str], kind: str) -> dict:
    """Upload bytes to Timeweb S3. Returns {public_id, public_url, bytes, content_type}.
    Raises on failure — callers fall back to GridFS."""
    client = _client()
    key = f"lovreski/{kind}/{uuid.uuid4().hex}{_ext_from_ct(content_type)}"

    def _do_upload():
        # Keep put_object minimal — some S3-compatible services (Timeweb) can
        # produce SignatureDoesNotMatch when ACL / Metadata headers are present.
        # The bucket is public, so public access is granted by bucket policy.
        client.put_object(
            Bucket=_bucket(),
            Key=key,
            Body=content,
            ContentType=content_type or "application/octet-stream",
        )

    await asyncio.to_thread(_do_upload)
    return {
        "public_id": key,
        "public_url": f"{_public_base()}/{key}",
        "bytes": len(content),
        "content_type": content_type or "application/octet-stream",
        "orig_filename": filename,
    }


def delivery_url(public_id: str) -> str:
    """Build the public URL for an S3-stored object."""
    return f"{_public_base()}/{public_id}"


async def destroy(public_id: str) -> bool:
    """Delete an object from S3. Returns True on success/not-found."""
    try:
        client = _client()

        def _do():
            client.delete_object(Bucket=_bucket(), Key=public_id)

        await asyncio.to_thread(_do)
        return True
    except Exception as e:
        logger.warning(f"[storage] s3 delete failed for {public_id}: {e}")
        return False
