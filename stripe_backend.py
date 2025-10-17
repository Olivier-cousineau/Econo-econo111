"""Shared helpers for Stripe Checkout endpoints.

This module centralises the configuration used by both the local Flask
server (``server.py``) and the serverless entrypoints under ``/api``.
"""
from __future__ import annotations

import os
from typing import Any, Dict

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


class StripeConfigurationError(RuntimeError):
    """Raised when Stripe environment variables are missing."""


class StripePlanError(ValueError):
    """Raised when an unknown plan is requested."""


def ensure_publishable_key() -> str:
    """Return the publishable key or raise ``StripeConfigurationError``."""

    publishable_key = os.environ.get("STRIPE_PUBLISHABLE_KEY")
    if not publishable_key:
        raise StripeConfigurationError("Missing STRIPE_PUBLISHABLE_KEY environment variable.")
    return publishable_key


def ensure_stripe_secret() -> str:
    """Return the secret key or raise ``StripeConfigurationError``."""

    secret_key = os.environ.get("STRIPE_SECRET_KEY")
    if not secret_key:
        raise StripeConfigurationError(
            "STRIPE_SECRET_KEY is not configured. Export it before starting the server."
        )
    return secret_key


def _normalise_locale(value: Any) -> str:
    locale = str(value or "en").split("-")[0].lower()
    return locale if locale in SUPPORTED_LOCALES else "en"


def create_checkout_session(payload: Dict[str, Any]) -> Dict[str, str]:
    """Create the Stripe Checkout session for the provided payload."""

    plan_key = (payload or {}).get("plan")
    config = PLAN_CONFIG.get(plan_key or "")
    if not config:
        raise StripePlanError("Unknown pricing plan.")

    stripe_locale = _normalise_locale(payload.get("locale"))
    product_name = (payload.get("name") or config["default_name"]).strip()
    description = (payload.get("description") or config["default_description"]).strip()

    success_url = os.environ.get(
        "STRIPE_SUCCESS_URL",
        "http://localhost:5000/success?session_id={CHECKOUT_SESSION_ID}",
    )
    cancel_url = os.environ.get("STRIPE_CANCEL_URL", "http://localhost:5000/cancel")

    stripe.api_key = ensure_stripe_secret()
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

    session_id = session.get("id")
    if not session_id:
        raise RuntimeError("Stripe did not return a session identifier.")
    return {"sessionId": session_id}
