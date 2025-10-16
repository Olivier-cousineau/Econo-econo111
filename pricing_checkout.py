from __future__ import annotations

import os
from typing import Any, Dict, Mapping

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

SUPPORTED_LOCALES = {
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


def ensure_stripe_secret() -> str:
    """Return the configured Stripe secret key or raise a RuntimeError."""

    secret_key = os.environ.get("STRIPE_SECRET_KEY")
    if not secret_key:
        raise RuntimeError(
            "STRIPE_SECRET_KEY is not configured. Export it before starting the server."
        )
    return secret_key


def _normalize_locale(raw_locale: Any) -> str:
    locale = str(raw_locale or "en").split("-")[0].lower()
    return locale if locale in SUPPORTED_LOCALES else "en"


def _resolve_product_metadata(payload: Mapping[str, Any], config: Mapping[str, Any]) -> Dict[str, str]:
    product_name = (str(payload.get("name") or config["default_name"]).strip())
    description = (str(payload.get("description") or config["default_description"]).strip())
    return {"name": product_name, "description": description}


def build_checkout_parameters(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate the payload and produce arguments for Session.create."""

    plan_key = payload.get("plan")
    config = PLAN_CONFIG.get(str(plan_key))
    if not config:
        raise ValueError("Unknown pricing plan.")

    product_metadata = _resolve_product_metadata(payload, config)

    return {
        "config": config,
        "locale": _normalize_locale(payload.get("locale")),
        "product_data": product_metadata,
        "success_url": os.environ.get(
            "STRIPE_SUCCESS_URL",
            "http://localhost:5000/success?session_id={CHECKOUT_SESSION_ID}",
        ),
        "cancel_url": os.environ.get("STRIPE_CANCEL_URL", "http://localhost:5000/cancel"),
    }


def create_checkout_session(payload: Mapping[str, Any]) -> stripe.checkout.Session:
    """Create a Stripe Checkout session from a JSON payload."""

    stripe.api_key = ensure_stripe_secret()
    params = build_checkout_parameters(payload)
    config = params["config"]
    return stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=["card"],
        line_items=[
            {
                "quantity": 1,
                "price_data": {
                    "currency": "cad",
                    "unit_amount": config["amount"],
                    "product_data": params["product_data"],
                },
            }
        ],
        allow_promotion_codes=True,
        locale=params["locale"],
        success_url=params["success_url"],
        cancel_url=params["cancel_url"],
        automatic_tax={"enabled": False},
    )
