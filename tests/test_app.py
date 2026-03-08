"""
Tests for GreenStock Inventory Assistant

Run with pytest (recommended):
    pytest tests/test_app.py -v

Or with built-in unittest (no install needed):
    python -m unittest tests.test_app -v
"""
import sys, os, json, unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["ANTHROPIC_API_KEY"] = ""

import app as app_module
from app import app, rule_based_insights, rule_based_categorize, days_until_expiry, days_until_stockout

def get_client():
    app.config["TESTING"] = True
    return app.test_client()

def reset_inventory():
    app_module.inventory.clear()
    app_module.next_id = 1
    app_module.load_sample_data()

class TestHappyPaths(unittest.TestCase):
    def setUp(self):
        reset_inventory()
        self.client = get_client()

    def test_homepage_loads(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"GreenStock", res.data)

    def test_homepage_shows_sample_items(self):
        res = self.client.get("/")
        self.assertTrue(b"Coffee" in res.data or b"coffee" in res.data.lower())

    def test_create_item_happy_path(self):
        res = self.client.post("/item/new", data={
            "name": "Recycled Notebooks", "category": "Office Supplies",
            "quantity": "10", "unit": "units", "expiry_date": "",
            "daily_usage": "0.5", "supplier": "EcoOffice Ltd",
            "notes": "100% recycled", "sustainability_score": "9",
        })
        self.assertEqual(res.status_code, 302)
        self.assertTrue(any(i["name"] == "Recycled Notebooks" for i in app_module.inventory))

    def test_create_then_view_item(self):
        self.client.post("/item/new", data={
            "name": "Bamboo Cups", "category": "Food & Beverage",
            "quantity": "25", "unit": "units", "sustainability_score": "10",
        })
        res = self.client.get("/")
        self.assertIn(b"Bamboo Cups", res.data)

    def test_edit_item_happy_path(self):
        item = app_module.inventory[0]
        item_id, orig_qty = item["id"], item["quantity"]
        res = self.client.post(f"/item/{item_id}/edit", data={
            "name": item["name"], "category": item["category"],
            "quantity": str(orig_qty + 5), "unit": item["unit"],
            "sustainability_score": "7",
        })
        self.assertEqual(res.status_code, 302)
        updated = next(i for i in app_module.inventory if i["id"] == item_id)
        self.assertEqual(updated["quantity"], orig_qty + 5)

    def test_delete_item(self):
        item_id = app_module.inventory[0]["id"]
        res = self.client.post(f"/item/{item_id}/delete")
        self.assertEqual(res.status_code, 302)
        self.assertFalse(any(i["id"] == item_id for i in app_module.inventory))

    def test_search_filter(self):
        res = self.client.get("/?q=coffee")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Coffee", res.data)

    def test_category_filter(self):
        res = self.client.get("/?category=Office+Supplies")
        self.assertEqual(res.status_code, 200)

    def test_api_items_returns_json_list(self):
        res = self.client.get("/api/items")
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)

    def test_insights_endpoint_returns_text(self):
        item_id = app_module.inventory[0]["id"]
        res = self.client.get(f"/item/{item_id}/insights")
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertIn("insight", data)
        self.assertGreater(len(data["insight"]), 0)

    def test_autocategorize_returns_valid_category(self):
        valid = ["Food & Beverage","Office Supplies","Cleaning & Sanitation",
                 "Lab Equipment","Electronics","Furniture","Chemicals","Medical Supplies","Other"]
        res = self.client.post("/api/autocategorize",
            data=json.dumps({"name": "Coffee Beans"}),
            content_type="application/json")
        self.assertEqual(res.status_code, 200)
        self.assertIn(json.loads(res.data)["category"], valid)


class TestEdgeCases(unittest.TestCase):
    def setUp(self):
        reset_inventory()
        self.client = get_client()

    def test_create_empty_name_rejected(self):
        res = self.client.post("/item/new", data={
            "name": "", "category": "Other", "quantity": "5", "sustainability_score": "5"})
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"required", res.data.lower())

    def test_create_negative_quantity_rejected(self):
        res = self.client.post("/item/new", data={
            "name": "Test", "category": "Other", "quantity": "-3", "sustainability_score": "5"})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(b"negative" in res.data.lower() or b"cannot" in res.data.lower())

    def test_create_nonnumeric_quantity_rejected(self):
        res = self.client.post("/item/new", data={
            "name": "Test", "category": "Other", "quantity": "abc", "sustainability_score": "5"})
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"number", res.data.lower())

    def test_create_invalid_expiry_format_rejected(self):
        res = self.client.post("/item/new", data={
            "name": "Test", "category": "Other", "quantity": "5",
            "expiry_date": "not-a-date", "sustainability_score": "5"})
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"date", res.data.lower())

    def test_create_out_of_range_eco_score_rejected(self):
        res = self.client.post("/item/new", data={
            "name": "Test", "category": "Other", "quantity": "5", "sustainability_score": "15"})
        self.assertEqual(res.status_code, 200)

    def test_insights_nonexistent_item_404(self):
        res = self.client.get("/item/99999/insights")
        self.assertEqual(res.status_code, 404)

    def test_edit_nonexistent_item_404(self):
        res = self.client.get("/item/99999/edit")
        self.assertEqual(res.status_code, 404)

    def test_search_no_results_empty_state(self):
        res = self.client.get("/?q=xyznonexistentitem999")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"No items found", res.data)

    def test_autocategorize_empty_name_400(self):
        res = self.client.post("/api/autocategorize",
            data=json.dumps({"name": ""}), content_type="application/json")
        self.assertEqual(res.status_code, 400)

    def test_create_zero_quantity_valid(self):
        res = self.client.post("/item/new", data={
            "name": "Empty Bin", "category": "Other",
            "quantity": "0", "sustainability_score": "5"})
        self.assertEqual(res.status_code, 302)
        item = next((i for i in app_module.inventory if i["name"] == "Empty Bin"), None)
        self.assertIsNotNone(item)
        self.assertEqual(item["quantity"], 0)


class TestHelpers(unittest.TestCase):
    def test_days_until_expiry_future(self):
        future = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")
        self.assertIn(days_until_expiry(future), [9, 10])

    def test_days_until_expiry_past(self):
        past = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        self.assertLess(days_until_expiry(past), 0)

    def test_days_until_expiry_empty(self):
        self.assertIsNone(days_until_expiry(""))

    def test_days_until_expiry_invalid(self):
        self.assertIsNone(days_until_expiry("not-a-date"))

    def test_days_until_stockout_normal(self):
        self.assertEqual(days_until_stockout(10, 2.0), 5)

    def test_days_until_stockout_zero_usage(self):
        self.assertIsNone(days_until_stockout(10, 0))

    def test_days_until_stockout_none(self):
        self.assertIsNone(days_until_stockout(10, None))

    def test_insights_expired_item(self):
        past = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        item = {"name":"X","category":"Other","quantity":5,
                "expiry_date":past,"daily_usage":1,"sustainability_score":5}
        self.assertTrue("expired" in rule_based_insights(item).lower())

    def test_insights_low_stock(self):
        item = {"name":"X","category":"Other","quantity":2,
                "expiry_date":"","daily_usage":1.5,"sustainability_score":5}
        result = rule_based_insights(item)
        self.assertTrue("stock" in result.lower() or "reorder" in result.lower())

    def test_insights_healthy(self):
        future = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")
        item = {"name":"X","category":"Other","quantity":100,
                "expiry_date":future,"daily_usage":0.5,"sustainability_score":8}
        result = rule_based_insights(item)
        self.assertTrue("✅" in result or "days" in result.lower())

    def test_categorize_food(self):
        self.assertEqual(rule_based_categorize("coffee beans"), "Food & Beverage")

    def test_categorize_office(self):
        self.assertEqual(rule_based_categorize("staple remover"), "Office Supplies")

    def test_categorize_unknown(self):
        self.assertEqual(rule_based_categorize("xzq unknown gizmo 999"), "Other")

    def test_insights_low_eco_score(self):
        item = {"name":"X","category":"Other","quantity":50,
                "expiry_date":"","daily_usage":1,"sustainability_score":2}
        self.assertIn("sustainable", rule_based_insights(item).lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
