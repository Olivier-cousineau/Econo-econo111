"""Shared Stripe helper utilities for both Flask and serverless handlers.

This module centralises the pricing configuration alongside the routines used
to expose the publishable key and create checkout sessions.  Having a single
source of truth prevents the local Flask server and the Vercel serverless
functions from drifting apart.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Tuple

import stripe

PLAN_CONFIG: Dict[str, Dict[str, Any]] = {
    "essential": {
        "amount": 999,
        "default_name": "Essential plan",
        "default_description": "Essential access to the clearance intelligence feed.",
    },
    "advanced": {
        "amount": 1999,
        "default_name": "Advanced plan",
        "default_description": "Unlimited catalog access with real-time alerts.",
    },
    "premium": {
        "amount": 2999,
        "default_name": "Premium plan",
        "default_description": "Full AI optimisation suite for scaling resellers.",
    },
}

SUPPORTED_LOCALES = {"da", "de", "en", "es", "fi", "fr", "it", "ja", "nb", "nl", "pl", "pt", "sv"}


def _ensure_stripe_secret() -> str:
    secret_key = os.environ.get("STRIPE_SECRET_KEY")
    if not secret_key:
        raise RuntimeError(
            "STRIPE_SECRET_KEY is not configured. Export it before starting the server."
        )
    return secret_key


def get_publishable_key_payload() -> Tuple[Dict[str, Any], int]:
    """Return a JSON-serialisable payload for the publishable key endpoint."""

    publishable_key = os.environ.get("STRIPE_PUBLISHABLE_KEY")
    if not publishable_key:
        return {"error": "Missing STRIPE_PUBLISHABLE_KEY environment variable."}, 500
    return {"publishableKey": publishable_key}, 200


def create_checkout_session_payload(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Create a Stripe checkout session based on the request payload."""

    try:
        stripe.api_key = _ensure_stripe_secret()
    except RuntimeError as exc:
        return {"error": str(exc)}, 500

    plan_key = (payload.get("plan") or "").strip().lower()
    config = PLAN_CONFIG.get(plan_key)
    if not config:
        return {"error": "Unknown pricing plan."}, 400

    locale = (payload.get("locale") or "en").split("-")[0].lower()
    stripe_locale = locale if locale in SUPPORTED_LOCALES else "en"

    product_name = (payload.get("name") or config["default_name"]).strip()
    description = (payload.get("description") or config["default_description"]).strip()

    success_url = os.environ.get(
        "STRIPE_SUCCESS_URL",
        "http://localhost:5000/success?session_id={CHECKOUT_SESSION_ID}",
    )
    cancel_url = os.environ.get("STRIPE_CANCEL_URL", "http://localhost:5000/cancel")

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[
                {
                    "quantity": 1,
                    "price_data": {
                        "currency": "cad",
                        "unit_amount": config["amount"],
                        "product_data": {
                            "name": product_name,
                            "description": description,
                        },
                    },
                }
            ],
            allow_promotion_codes=True,
            locale=stripe_locale,
            success_url=success_url,
            cancel_url=cancel_url,
            automatic_tax={"enabled": False},
        )
    except stripe.error.StripeError as exc:
        return {"error": exc.user_message or str(exc)}, 400
    except Exception as exc:  # pragma: no cover - unexpected error
        return {"error": str(exc)}, 500

    return {"sessionId": session.get("id")}, 200

