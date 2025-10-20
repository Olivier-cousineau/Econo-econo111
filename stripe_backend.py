"""Shared backend helpers for Stripe checkout endpoints.

This module centralises the logic that is used both by the local Flask
development server (``server.py``) and the Vercel serverless functions
located in ``api/``.  Having a single source of truth avoids subtle
drifts between the two execution environments which previously caused the
frontend to fail when the serverless routes were not returning the same
payloads as the Flask routes.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Dict, Iterable

import stripe


PLAN_CONFIG: Dict[str, Dict[str, object]] = {
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

SUPPORTED_LOCALES: Iterable[str] = {
    "da",
    "de",
    "en",
    "es",
    "fi",
    "fr",
    "it",
    "ja",
    "nb",
    "nl",
    "pl",
    "pt",
    "sv",
}


class ConfigurationError(RuntimeError):
    """Raised when a required environment variable is missing."""


class InvalidPlanError(RuntimeError):
    """Raised when an unknown pricing plan is requested."""


def _ensure_publishable_key() -> str:
    publishable_key = os.environ.get("STRIPE_PUBLISHABLE_KEY")
    if not publishable_key:
        raise ConfigurationError("Missing STRIPE_PUBLISHABLE_KEY environment variable.")
    return publishable_key


def _ensure_secret_key() -> str:
    secret_key = os.environ.get("STRIPE_SECRET_KEY")
    if not secret_key:
        raise ConfigurationError("STRIPE_SECRET_KEY is not configured. Export it before starting the server.")
    return secret_key


def get_publishable_key_payload() -> Dict[str, str]:
    """Return the JSON payload expected by the frontend when initialising Stripe."""

    return {"publishableKey": _ensure_publishable_key()}


@dataclass
class CheckoutSessionRequest:
    plan: str
    locale: str
    name: str
    description: str

    @classmethod
    def from_payload(cls, payload: Dict[str, object]) -> "CheckoutSessionRequest":
        plan = str(payload.get("plan")) if payload.get("plan") else ""
        if not plan:
            raise InvalidPlanError("Unknown pricing plan.")

        locale = str(payload.get("locale") or "en").split("-")[0].lower()
        name = (str(payload.get("name")) if payload.get("name") else "").strip()
        description = (
            str(payload.get("description")) if payload.get("description") else ""
        ).strip()

        return cls(plan=plan, locale=locale, name=name, description=description)


def _normalise_locale(locale: str) -> str:
    return locale if locale in SUPPORTED_LOCALES else "en"


def create_checkout_session(payload: Dict[str, object]) -> stripe.checkout.Session:
    request = CheckoutSessionRequest.from_payload(payload)
    config = PLAN_CONFIG.get(request.plan)
    if not config:
        raise InvalidPlanError("Unknown pricing plan.")

    stripe.api_key = _ensure_secret_key()

    product_name = request.name or str(config["default_name"])
    description = request.description or str(config["default_description"])

    success_url = os.environ.get(
        "STRIPE_SUCCESS_URL",
        "http://localhost:5000/success?session_id={CHECKOUT_SESSION_ID}",
    )
    cancel_url = os.environ.get("STRIPE_CANCEL_URL", "http://localhost:5000/cancel")

    session = stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=["card"],
        line_items=[
            {
                "quantity": 1,
                "price_data": {
                    "currency": "cad",
                    "unit_amount": int(config["amount"]),
                    "product_data": {
                        "name": product_name,
                        "description": description,
                    },
                },
            }
        ],
        allow_promotion_codes=True,
        locale=_normalise_locale(request.locale),
        success_url=success_url,
        cancel_url=cancel_url,
        automatic_tax={"enabled": False},
    )
    return session


def dump_json(data: Dict[str, object]) -> bytes:
    return json.dumps(data).encode("utf-8")

