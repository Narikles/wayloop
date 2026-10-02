"""Webhook entrant : paiement (Stripe)."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    from ..services import billing

    s = get_settings()
    payload = await request.body()
    if not s.stripe_webhook_secret or not billing.verify_signature(payload, request.headers.get("stripe-signature", ""),
                                                                   s.stripe_webhook_secret):
        raise HTTPException(400, "Signature invalide")
    result = billing.handle_event(db, json.loads(payload))
    db.commit()
    return {"received": True, "result": result}
