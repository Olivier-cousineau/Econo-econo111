"""Tests for the Amazon Canada daily fetch script.

The goal is to make it obvious how to validate the automation locally, even
without Amazon PA API credentials. The suite runs the CLI in `--no-api` mode and
verifies that the generated JSON matches the structure expected by the site.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import List

import unittest

from admin import amazon_paapi_daily


class DummyDealsTest(unittest.TestCase):
    def test_generate_dummy_deals_respects_limit(self) -> None:
        keywords: List[str] = ["ordinateur"]
        deals = amazon_paapi_daily.generate_dummy_deals(keywords, limit=3)
        self.assertEqual(len(deals), 3)
        for deal in deals:
            self.assertTrue(deal.title)
            self.assertIn("Amazon Canada", deal.store)


class MainExecutionTest(unittest.TestCase):
    def test_main_no_api_produces_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "amazon_ca_daily.json"
            exit_code = amazon_paapi_daily.main(
                ["--no-api", "--limit", "2", "--output", str(output)]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue(output.exists())

            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertGreater(len(payload), 0)
            first = payload[0]
            self.assertIn("title", first)
            self.assertIn("image", first)
            self.assertIn("price", first)
            self.assertIn("salePrice", first)
            self.assertIn("store", first)
            self.assertIn("city", first)
            self.assertIn("url", first)


if __name__ == "__main__":
    unittest.main()
