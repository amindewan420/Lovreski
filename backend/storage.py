"""Cloudinary storage backend for Lovreski.

Fail-safe design: when CLOUDINARY_* env vars are missing, everything falls
back to GridFS (the existing behavior) — the app keeps working unchanged.

Layout in Cloudinary:
  folder:  lovreski/<kind>/           (profile_photo, chat_image, ..., support_receipt)
  type:    "upload" (public)          → profile_photo
           "authenticated" (private)  → chat_* media, receipts, everything else
  resource_type: image | video (audio counts as video in Cloudinary) | raw

Delivery:
  Our /api/files/<id> endpoint keeps enforcing access (owner / admin /
  chat participant / HMAC-signed URL) and then 302-redirects to the
  Cloudinary URL — public for profile photos, Cloudinary-signed
  authenticated delivery URL for private kinds.
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
        os.environ.get("CLOUDINARY_CLOUD_NAME")
        and os.environ.get("CLOUDINARY_API_KEY")
        and os.environ.get("CLOUDINARY_API_SECRET")
    )


def _client():
    import cloudinary
    cloudinary.config(
        cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"],
        api_key=os.environ["CLOUDINARY_API_KEY"],
        api_secret=os.environ["CLOUDINARY_API_SECRET"],
        secure=True,
    )
    return cloudinary


def resource_type_for(content_type: str) -> str:
    ct = (content_type or "").lower()
    if ct.startswith("image/"):
        return "image"
    if ct.startswith("video/") or ct.startswith("audio/"):
        return "video"  # Cloudinary stores audio under the 'video' resource type
    return "raw"


def access_type_for(kind: str) -> str:
    return "upload" if kind in PUBLIC_KINDS else "authenticated"


async def upload_bytes(content: bytes, filename: str, content_type: str,
                       owner_id: Optional[str], kind: str) -> dict:
    """Upload bytes to Cloudinary. Returns a dict with public_id, resource_type,
    type, bytes, format. Raises on failure — callers fall back to GridFS."""
    cloudinary = _client()
    rt = resource_type_for(content_type)
    at = access_type_for(kind)
    public_id = f"lovreski/{kind}/{uuid.uuid4().hex[:16]}"

    def _do_upload():
        return cloudinary.uploader.upload(
            content,
            public_id=public_id,
            resource_type=rt,
            type=at,
            overwrite=False,
        )

    res = await asyncio.to_thread(_do_upload)
    if not res.get("public_id"):
        raise RuntimeError("Cloudinary upload returned no public_id")
    return {
        "public_id": res["public_id"],
        "resource_type": rt,
        "type": at,
        "bytes": int(res.get("bytes") or len(content)),
        "format": res.get("format") or "",
        "orig_filename": filename,
    }


def delivery_url(public_id: str, resource_type: str, access_type: str,
                 fmt: str = "", content_type: str = "") -> str:
    """Build the Cloudinary delivery URL.
    Public kinds → plain secure URL. Authenticated kinds → signed delivery URL
    (regenerated per request; our /api/files gate decides who gets it)."""
    cloudinary = _client()
    kwargs = {"resource_type": resource_type, "type": access_type, "secure": True}
    if access_type == "authenticated":
        kwargs["sign_url"] = True
    if fmt:
        kwargs["format"] = fmt
    url, _ = cloudinary.utils.cloudinary_url(public_id, **kwargs)
    return url


async def destroy(public_id: str, resource_type: str, access_type: str) -> bool:
    """Delete an asset from Cloudinary. Returns True on success/ok-not-found."""
    try:
        cloudinary = _client()

        def _do():
            return cloudinary.uploader.destroy(
                public_id, resource_type=resource_type, type=access_type, invalidate=True
            )

        res = await asyncio.to_thread(_do)
        return res.get("result") in ("ok", "not found")
    except Exception as e:
        logger.warning(f"[storage] cloudinary destroy failed for {public_id}: {e}")
        return False
