"""Miscellaneous routes — /health, /chat/costs"""
from fastapi import Depends
from server import api, db, get_current_user, MSG_COST, FREE_MSGS, GIFT_CATALOG

@api.get("/health")
async def health():
    return {"ok": True}

@api.get("/chat/costs")
async def chat_costs(user: dict = Depends(get_current_user)):
    """Public pricing table for chat message kinds + free-msg window."""
    return {
        "costs": MSG_COST,
        "free_messages": FREE_MSGS,
        "is_premium": bool(user.get('is_premium')),
        "coins": int(user.get('coins') or 0),
    }

