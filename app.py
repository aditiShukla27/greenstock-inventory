import os
import json
import csv
import io
import base64
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for
from dotenv import load_dotenv
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

load_dotenv()

app = Flask(__name__)

# ── In-memory store (swap for SQLite/Postgres in prod) ──────────────────────
inventory = []
next_id = 1

def load_sample_data():
    """Load synthetic sample data from CSV on startup."""
    global inventory, next_id
    sample_path = os.path.join(os.path.dirname(__file__), "data", "sample_inventory.csv")
    if not os.path.exists(sample_path):
        return
    with open(sample_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            item = {
                "id": next_id,
                "name": row["name"],
                "category": row["category"],
                "quantity": int(row["quantity"]),
                "unit": row["unit"],
                "expiry_date": row.get("expiry_date", ""),
                "daily_usage": float(row.get("daily_usage", 0)),
                "supplier": row.get("supplier", ""),
                "notes": row.get("notes", ""),
                "added_at": row.get("added_at", datetime.now().isoformat()),
                "sustainability_score": int(row.get("sustainability_score", 5)),
            }
            inventory.append(item)
            next_id += 1

# ── Helpers ──────────────────────────────────────────────────────────────────

def days_until_expiry(expiry_str):
    if not expiry_str:
        return None
    try:
        exp = datetime.strptime(expiry_str, "%Y-%m-%d")
        return (exp - datetime.now()).days
    except ValueError:
        return None

def days_until_stockout(quantity, daily_usage):
    if daily_usage and daily_usage > 0:
        return round(quantity / daily_usage)
    return None

def rule_based_insights(item):
    """Fallback insights when AI is unavailable."""
    insights = []
    days_exp = days_until_expiry(item.get("expiry_date", ""))
    days_out = days_until_stockout(item["quantity"], item.get("daily_usage", 0))

    if days_exp is not None:
        if days_exp < 0:
            insights.append(f"⚠️ EXPIRED {abs(days_exp)} days ago — remove immediately.")
        elif days_exp <= 7:
            insights.append(f"🔴 Expires in {days_exp} days — use or donate soon.")
        elif days_exp <= 30:
            insights.append(f"🟡 Expires in {days_exp} days — monitor closely.")

    if days_out is not None:
        if days_out <= 3:
            insights.append(f"🔴 Stock runs out in ~{days_out} days — reorder urgently.")
        elif days_out <= 10:
            insights.append(f"🟡 Stock runs out in ~{days_out} days — plan reorder.")
        else:
            insights.append(f"🟢 ~{days_out} days of stock remaining.")

    if item.get("sustainability_score", 5) <= 3:
        insights.append("🌿 Consider switching to a more sustainable supplier.")

    if not insights:
        insights.append("✅ Item looks healthy — no immediate action needed.")

    return " ".join(insights)

def ai_insights(item):
    """AI-powered structured insights via Anthropic Claude."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or not ANTHROPIC_AVAILABLE:
        return rule_based_insights(item)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        days_exp = days_until_expiry(item.get("expiry_date", ""))
        days_out = days_until_stockout(item["quantity"], item.get("daily_usage", 0))

        prompt = f"""You are a sustainability-focused inventory assistant for a small business or non-profit.

Item details:
- Name: {item['name']}
- Brand: {item.get('brand', 'unknown')}
- Category: {item['category']}
- Quantity: {item['quantity']} {item.get('unit', '')}
- Unit of measurement: {item.get('unit', 'units')}
- Daily usage rate: {item.get('daily_usage', 'unknown')} {item.get('unit', 'units')} per day
- Days until expiry: {days_exp if days_exp is not None else 'no expiry date set'}
- Days until stockout: {days_out if days_out is not None else 'unknown'}
- Current supplier: {item.get('supplier', 'unknown')}
- Sustainability score (1-10): {item.get('sustainability_score', 'unknown')}
- Notes: {item.get('notes', 'none')}

Reply with ONLY a JSON object, no markdown, no extra text:
{{
  "urgency": "<one sentence: is action needed now? mention specific days and quantity with correct unit>",
  "storage": "<one sentence: how to store this specific item properly>",
  "spoilage_signs": "<one sentence: how to tell if this specific item has gone bad>",
  "waste_tip": "<one sentence: practical way to use it up, mention quantity and unit>",
  "eco_swap": "<one sentence: specific sustainable alternative or supplier type>"
}}"""

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = message.content[0].text.strip().replace("```json","").replace("```","").strip()
        parsed = json.loads(raw)
        parsed["structured"] = True
        return parsed
    except Exception:
        return rule_based_insights(item)

def ai_categorize(name, notes=""):
    """Use AI to auto-categorize an item, with rule-based fallback."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or not ANTHROPIC_AVAILABLE:
        return rule_based_categorize(name)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        prompt = f"""You are an inventory categorization assistant. Categorize the item below into EXACTLY ONE of these categories:
- Food & Beverage (any food, drink, ingredient, dairy, produce, condiment, beverage)
- Office Supplies (paper, pens, stationery, binders, tape)
- Cleaning & Sanitation (soap, bleach, sanitizer, mops, wipes)
- Lab Equipment (beakers, pipettes, microscopes, lab tools)
- Electronics (cables, batteries, computers, chargers)
- Furniture (chairs, desks, shelves, cabinets)
- Chemicals (solvents, acids, reagents, ethanol)
- Medical Supplies (gloves, bandages, medication)
- Other (anything that doesn't fit above)

Item name: {name}
Notes: {notes or 'none'}

Reply with ONLY the category name exactly as written above, nothing else."""

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=20,
            messages=[{"role": "user", "content": prompt}]
        )
        result = message.content[0].text.strip()
        valid = ["Food & Beverage", "Office Supplies", "Cleaning & Sanitation",
                 "Lab Equipment", "Electronics", "Furniture", "Chemicals",
                 "Medical Supplies", "Other"]
        return result if result in valid else rule_based_categorize(name)
    except Exception:
        return rule_based_categorize(name)

def rule_based_categorize(name):
    name_lower = name.lower()
    rules = {
        "Food & Beverage": ["coffee", "tea", "sugar", "milk", "food", "snack", "water", "juice", "bread", "grain", "cheese", "butter", "egg", "flour", "rice", "pasta", "oat", "fruit", "vegetable", "meat", "chicken", "beef", "fish", "sauce", "oil", "salt", "pepper", "honey", "yogurt", "cream", "chocolate", "bean", "soup", "drink", "beverage", "dairy"],
        "Office Supplies": ["paper", "pen", "pencil", "staple", "folder", "binder", "tape", "marker", "notebook"],
        "Cleaning & Sanitation": ["soap", "cleaner", "bleach", "mop", "sponge", "sanitizer", "disinfect", "wipe"],
        "Lab Equipment": ["beaker", "flask", "pipette", "microscope", "centrifuge", "reagent", "chemical", "lab"],
        "Electronics": ["cable", "charger", "battery", "laptop", "monitor", "keyboard", "mouse", "usb", "power"],
        "Furniture": ["chair", "desk", "table", "shelf", "cabinet", "drawer", "rack"],
        "Chemicals": ["acid", "solvent", "ethanol", "acetone", "reagent", "buffer"],
    }
    for category, keywords in rules.items():
        if any(kw in name_lower for kw in keywords):
            return category
    return "Other"

# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    search = request.args.get("q", "").lower()
    category_filter = request.args.get("category", "")
    status_filter = request.args.get("status", "")

    filtered = inventory[:]

    if search:
        filtered = [i for i in filtered if search in i["name"].lower() or search in i.get("notes","").lower()]

    if category_filter:
        filtered = [i for i in filtered if i["category"] == category_filter]

    if status_filter == "expiring_soon":
        filtered = [i for i in filtered if (days_until_expiry(i.get("expiry_date","")) or 999) <= 30
                    and (days_until_expiry(i.get("expiry_date","")) or -1) >= 0]
    elif status_filter == "low_stock":
        filtered = [i for i in filtered if (days_until_stockout(i["quantity"], i.get("daily_usage",0)) or 999) <= 10]
    elif status_filter == "expired":
        filtered = [i for i in filtered if (days_until_expiry(i.get("expiry_date","")) or 1) < 0]

    # Enrich with computed fields
    for item in filtered:
        item["days_until_expiry"] = days_until_expiry(item.get("expiry_date",""))
        item["days_until_stockout"] = days_until_stockout(item["quantity"], item.get("daily_usage",0))

    categories = sorted(set(i["category"] for i in inventory))

    # Summary stats
    total_items = len(inventory)
    expiring_soon = sum(1 for i in inventory if 0 <= (days_until_expiry(i.get("expiry_date","")) or 999) <= 7)
    low_stock = sum(1 for i in inventory if 0 < (days_until_stockout(i["quantity"], i.get("daily_usage",0)) or 999) <= 3)
    expired = sum(1 for i in inventory if (days_until_expiry(i.get("expiry_date","")) or 1) < 0)
    avg_sustainability = round(sum(i.get("sustainability_score",5) for i in inventory) / max(len(inventory),1), 1)

    stats = {
        "total": total_items,
        "expiring_soon": expiring_soon,
        "low_stock": low_stock,
        "expired": expired,
        "avg_sustainability": avg_sustainability,
    }

    return render_template("index.html",
                           items=filtered,
                           categories=categories,
                           stats=stats,
                           search=search,
                           category_filter=category_filter,
                           status_filter=status_filter)

@app.route("/item/new", methods=["GET", "POST"])
def new_item():
    if request.method == "POST":
        return _create_item(request.form)
    return render_template("form.html", item=None, action="Create", categories=_all_categories())

@app.route("/item/<int:item_id>/edit", methods=["GET", "POST"])
def edit_item(item_id):
    item = _find_item(item_id)
    if not item:
        return "Item not found", 404
    if request.method == "POST":
        return _update_item(item, request.form)
    return render_template("form.html", item=item, action="Update", categories=_all_categories())

@app.route("/item/<int:item_id>/delete", methods=["POST"])
def delete_item(item_id):
    global inventory
    inventory = [i for i in inventory if i["id"] != item_id]
    return redirect(url_for("index"))

@app.route("/item/<int:item_id>/insights")
def item_insights(item_id):
    item = _find_item(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404
    use_ai = bool(os.getenv("ANTHROPIC_API_KEY", "")) and ANTHROPIC_AVAILABLE
    insight = ai_insights(item)
    if isinstance(insight, dict):
        insight["ai_powered"] = use_ai
        return jsonify(insight)
    return jsonify({"insight": insight, "ai_powered": use_ai, "structured": False})

@app.route("/scan-receipt")
def scan_receipt_page():
    return render_template("scan_receipt.html")

@app.route("/api/autocategorize", methods=["POST"])
def autocategorize():
    data = request.get_json()
    name = data.get("name", "")
    notes = data.get("notes", "")
    if not name:
        return jsonify({"error": "Name is required"}), 400
    category = ai_categorize(name, notes)
    return jsonify({"category": category})

@app.route("/api/items", methods=["GET"])
def api_items():
    return jsonify(inventory)

@app.route("/api/predict-shelf-life", methods=["POST"])
def predict_shelf_life():
    """Use AI to generate a full smart item profile."""
    data = request.get_json()
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Name is required"}), 400

    use_ai = bool(os.getenv("ANTHROPIC_API_KEY", "")) and ANTHROPIC_AVAILABLE
    if use_ai:
        try:
            client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            prompt = f"""You are a food safety, sustainability, and inventory expert.

For the inventory item: "{name}"

Reply with ONLY a JSON object, no markdown, no extra text:
{{
  "shelf_life_days": <integer: how many days this lasts if stored properly, or null if not perishable>,
  "daily_usage_estimate": <float: typical daily usage for a small cafe/office/lab>,
  "unit": "<best unit from: units, count, lbs, oz, kg, g, litres, ml, gallons, fl oz, boxes, cases, bags, bottles, cans, cartons, loaves, rolls, sheets, reams, pairs>",
  "storage_tip": "<one specific sentence on best storage practice>",
  "spoilage_signs": "<one sentence describing visible/smell signs it has gone bad>",
  "waste_reduction_tip": "<one sentence on how to reduce waste with this item>",
  "sustainable_alternative": "<one sentence suggesting a more eco-friendly version or supplier type>",
  "reorder_lead_days": <integer: how many days before running out should you reorder, e.g. 3>,
  "category": "<one of: Food & Beverage, Office Supplies, Cleaning & Sanitation, Lab Equipment, Electronics, Furniture, Chemicals, Medical Supplies, Other>",
  "confidence": "<high, medium, or low>"
}}"""

            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = message.content[0].text.strip().replace("```json","").replace("```","").strip()
            parsed = json.loads(raw)
            if parsed.get("shelf_life_days"):
                parsed["expiry_date"] = (datetime.now() + timedelta(days=int(parsed["shelf_life_days"]))).strftime("%Y-%m-%d")
            parsed["ai_powered"] = True
            # Ask Claude for eco score too
            try:
                eco_msg = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=10,
                    messages=[{"role": "user", "content": f'Rate the sustainability of "{name}" on a scale of 1-10 where 10 is most sustainable/eco-friendly. Reply with ONLY a single integer.'}]
                )
                eco_score = int(eco_msg.content[0].text.strip())
                if 1 <= eco_score <= 10:
                    parsed["eco_score"] = eco_score
            except Exception:
                pass
            return jsonify(parsed)
        except Exception:
            pass

    # Rule-based fallback
    name_lower = name.lower()
    shelf_lives = {
        "milk":   (7,   0.5,  "litres", "Keep refrigerated at 4°C.", "Sour smell, curdled texture.", "Buy local farm milk to cut transport emissions.", 2),
        "cheese": (21,  0.1,  "kg",     "Wrap tightly and refrigerate.", "Mold (other than natural rind), slimy texture, off smell.", "Choose locally sourced or organic cheese.", 5),
        "bread":  (5,   0.3,  "loaves", "Store in a cool dry place or freeze.", "Visible mold, stale smell.", "Buy from local bakeries to reduce packaging waste.", 1),
        "egg":    (28,  0.5,  "units",  "Refrigerate away from strong odours.", "Float in water test; bad smell when cracked.", "Choose free-range or locally farmed eggs.", 7),
        "butter": (30,  0.05, "kg",     "Keep refrigerated; freeze for longer.", "Rancid or sour smell, discolouration.", "Choose organic grass-fed butter.", 7),
        "yogurt": (14,  0.2,  "kg",     "Keep refrigerated, consume by use-by date.", "Mold on surface, watery separation, sour smell.", "Choose glass-jar yogurt to reduce plastic.", 3),
        "coffee": (180, 0.05, "kg",     "Store in airtight container away from light.", "Stale flat smell, no aroma.", "Choose fair-trade, locally roasted beans.", 14),
        "tea":    (365, 0.02, "kg",     "Store in dry airtight container.", "Loss of aroma, flat taste.", "Choose loose-leaf over individually wrapped bags.", 30),
        "flour":  (180, 0.1,  "kg",     "Airtight container in cool dry place.", "Musty smell, visible bugs or clumps.", "Choose locally milled or whole grain flour.", 14),
        "rice":   (365, 0.1,  "kg",     "Airtight container away from moisture.", "Off smell, visible pests or moisture.", "Buy in bulk to reduce packaging.", 30),
        "pasta":  (730, 0.1,  "kg",     "Store dry in sealed container.", "Discolouration, off smell when cooked.", "Choose whole wheat or legume-based pasta.", 30),
        "oil":    (365, 0.05, "litres", "Cool dark place away from heat.", "Rancid or paint-like smell.", "Choose cold-pressed, locally produced oils.", 30),
        "cream":  (7,   0.2,  "litres", "Refrigerate and use quickly once opened.", "Sour smell, separation that won't remix.", "Use oat or soy cream as a sustainable swap.", 2),
        "juice":  (7,   0.3,  "litres", "Refrigerate after opening.", "Fermented smell, fizzing, mold.", "Choose whole fruit over packaged juice.", 2),
    }
    for keyword, (days, usage, unit, tip, spoilage, eco, reorder) in shelf_lives.items():
        if keyword in name_lower:
            return jsonify({
                "shelf_life_days": days, "daily_usage_estimate": usage, "unit": unit,
                "storage_tip": tip, "spoilage_signs": spoilage,
                "waste_reduction_tip": f"Track daily usage to avoid over-ordering {name}.",
                "sustainable_alternative": eco, "reorder_lead_days": reorder,
                "category": "Food & Beverage",
                "expiry_date": (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d"),
                "confidence": "medium", "ai_powered": False
            })

    return jsonify({
        "shelf_life_days": None, "daily_usage_estimate": None, "unit": "units",
        "storage_tip": "Check packaging for storage instructions.",
        "spoilage_signs": "Check for visible damage, unusual smell, or discolouration.",
        "waste_reduction_tip": "Track usage carefully to avoid over-purchasing.",
        "sustainable_alternative": "Look for suppliers with eco-certifications.",
        "reorder_lead_days": 3, "category": "Other",
        "expiry_date": None, "confidence": "low", "ai_powered": False
    })


@app.route("/item/<int:item_id>/mark-out-of-stock", methods=["POST"])
def mark_out_of_stock(item_id):
    """Mark item as out of stock and trigger substitution suggestions."""
    item = _find_item(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404
    item["quantity"] = 0
    item["out_of_stock"] = True
    return jsonify({"success": True})

@app.route("/api/substitutions/<int:item_id>", methods=["GET"])
def get_substitutions(item_id):
    """AI suggests substitutes from current inventory for an out-of-stock item."""
    item = _find_item(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    in_stock = [i for i in inventory if i["quantity"] > 0 and i["id"] != item_id]
    stock_list = [f"{i['name']} ({i['quantity']} {i['unit']})" for i in in_stock]

    use_ai = bool(os.getenv("ANTHROPIC_API_KEY", "")) and ANTHROPIC_AVAILABLE
    if use_ai:
        try:
            client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            prompt = f"""You are a resourceful sustainability-focused inventory assistant helping reduce unnecessary purchases.

The item that just ran out: {item['name']} (category: {item['category']}, unit: {item.get('unit','units')})

Items currently in stock:
{chr(10).join(f'- {s}' for s in stock_list) if stock_list else 'No items currently in stock.'}

Suggest up to 3 creative substitutes using ONLY items from the in-stock list above.
For each substitute, explain exactly how it can replace the out-of-stock item.
If nothing in stock can substitute, say so honestly and suggest the most sustainable way to restock.

Format exactly like this for each suggestion:
🔄 [In-Stock Item Name]
How to use: [specific, practical substitution tip — one sentence]

End with one sentence on whether a store trip is truly necessary."""

            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}]
            )
            return jsonify({
                "item_name": item["name"],
                "suggestions": message.content[0].text.strip(),
                "ai_powered": True
            })
        except Exception:
            pass

    # Rule-based fallback
    same_cat = [i for i in in_stock if i["category"] == item["category"]]
    if same_cat:
        suggestions = f"🔄 {same_cat[0]['name']}\nHow to use: This is in the same category as {item['name']} and may work as a substitute.\n\nConsider whether a store trip is necessary before purchasing more."
    else:
        suggestions = f"No direct substitutes found in stock for {item['name']}.\n\nConsider whether you truly need this item urgently before making a store trip."
    return jsonify({"item_name": item["name"], "suggestions": suggestions, "ai_powered": False})

@app.route("/api/scan-receipt", methods=["POST"])
def scan_receipt():
    """Parse a receipt image with AI and return items to add to inventory."""
    use_ai = bool(os.getenv("ANTHROPIC_API_KEY", "")) and ANTHROPIC_AVAILABLE
    if not use_ai:
        return jsonify({"error": "AI required for receipt scanning. Please add your API key."}), 400

    data = request.get_json()
    image_data = data.get("image")  # base64 encoded image
    if not image_data:
        return jsonify({"error": "No image provided"}), 400

    # Strip data URL prefix if present
    if "," in image_data:
        image_data = image_data.split(",")[1]
    media_type = "image/jpeg"
    if data.get("media_type"):
        media_type = data["media_type"]

    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        prompt = """You are an inventory management assistant. Look at this receipt image and extract every purchased item.

CRITICAL: Your entire response must be ONLY a valid JSON array. No intro text, no explanation, no markdown, no code fences. Start your response with [ and end with ].

Use this exact format for each item:
[{"name":"Apple","brand":"","quantity":2,"unit":"count","category":"Food & Beverage","shelf_life_days":7,"storage_tip":"Store at room temperature or refrigerate.","sustainability_score":8,"daily_usage_estimate":0.5},{"name":"Milk","brand":"","quantity":1,"unit":"litres","category":"Food & Beverage","shelf_life_days":7,"storage_tip":"Keep refrigerated.","sustainability_score":6,"daily_usage_estimate":0.3}]

Rules:
- quantity = the number shown on the receipt before the item name
- shelf_life_days = your best estimate based on the product type
- sustainability_score = 1-10 based on how eco-friendly the product typically is
- unit must be one of: units, count, lbs, oz, kg, g, litres, ml, gallons, fl oz, boxes, cases, bags, bottles, cans, cartons, loaves, rolls, sheets, reams, pairs
- category must be one of: Food & Beverage, Office Supplies, Cleaning & Sanitation, Lab Equipment, Electronics, Furniture, Chemicals, Medical Supplies, Other
- Do NOT include TOTAL, CASH, CHANGE, TAX or any non-product lines
- If you cannot read the receipt, return []"""

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data
                        }
                    },
                    {"type": "text", "text": prompt}
                ]
            }]
        )
        raw = message.content[0].text.strip()
        # Strip markdown fences
        raw = raw.replace("```json","").replace("```","").strip()
        # Find the JSON array even if there's extra text around it
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start == -1 or end == 0:
            return jsonify({"items": [], "count": 0, "ai_powered": True, "warning": "No items found on receipt."})
        raw = raw[start:end]
        items = json.loads(raw)

        # Calculate expiry dates
        for item in items:
            if item.get("shelf_life_days"):
                item["expiry_date"] = (datetime.now() + timedelta(days=int(item["shelf_life_days"]))).strftime("%Y-%m-%d")
            else:
                item["expiry_date"] = ""

        return jsonify({"items": items, "count": len(items), "ai_powered": True})
    except Exception as e:
        return jsonify({"error": f"Failed to scan receipt: {str(e)}"}), 500

@app.route("/api/confirm-receipt-items", methods=["POST"])
def confirm_receipt_items():
    """Add AI-scanned receipt items to inventory."""
    global next_id
    data = request.get_json()
    items_to_add = data.get("items", [])
    added = []
    for i in items_to_add:
        item = {
            "id": next_id,
            "name": i.get("name", "Unknown"),
            "brand": i.get("brand", ""),
            "category": i.get("category", "Other"),
            "quantity": int(i.get("quantity", 1)),
            "unit": i.get("unit", "units"),
            "expiry_date": i.get("expiry_date", ""),
            "daily_usage": float(i.get("daily_usage_estimate") or 0),
            "supplier": "",
            "notes": i.get("storage_tip", ""),
            "added_at": datetime.now().isoformat(),
            "sustainability_score": int(i.get("sustainability_score") or 5),
        }
        inventory.append(item)
        next_id += 1
        added.append(item)
    return jsonify({"added": len(added), "items": added})

# ── Internal helpers ──────────────────────────────────────────────────────────

def _find_item(item_id):
    return next((i for i in inventory if i["id"] == item_id), None)

def _all_categories():
    return ["Food & Beverage", "Office Supplies", "Cleaning & Sanitation",
            "Lab Equipment", "Electronics", "Furniture", "Chemicals",
            "Medical Supplies", "Other"]

def _validate_item_form(form):
    errors = []
    if not form.get("name", "").strip():
        errors.append("Item name is required.")
    try:
        qty = int(form.get("quantity", ""))
        if qty < 0:
            errors.append("Quantity cannot be negative.")
    except ValueError:
        errors.append("Quantity must be a whole number.")
    daily = form.get("daily_usage", "")
    if daily:
        try:
            d = float(daily)
            if d < 0:
                errors.append("Daily usage cannot be negative.")
        except ValueError:
            errors.append("Daily usage must be a number.")
    expiry = form.get("expiry_date", "")
    if expiry:
        try:
            datetime.strptime(expiry, "%Y-%m-%d")
        except ValueError:
            errors.append("Expiry date must be in YYYY-MM-DD format.")
    score = form.get("sustainability_score", "5")
    try:
        s = int(score)
        if not (1 <= s <= 10):
            errors.append("Sustainability score must be between 1 and 10.")
    except ValueError:
        errors.append("Sustainability score must be a number.")
    return errors

def _create_item(form):
    global next_id
    errors = _validate_item_form(form)
    if errors:
        return render_template("form.html", item=None, action="Create",
                               categories=_all_categories(), errors=errors, form=form)
    item = {
        "id": next_id,
        "name": form["name"].strip(),
        "brand": form.get("brand", "").strip(),
        "category": form.get("category", "Other"),
        "quantity": int(form["quantity"]),
        "unit": form.get("unit", "units").strip(),
        "expiry_date": form.get("expiry_date", ""),
        "daily_usage": float(form.get("daily_usage") or 0),
        "supplier": form.get("supplier", "").strip(),
        "notes": form.get("notes", "").strip(),
        "added_at": datetime.now().isoformat(),
        "sustainability_score": int(form.get("sustainability_score", 5)),
    }
    inventory.append(item)
    next_id += 1
    return redirect(url_for("index"))

def _update_item(item, form):
    errors = _validate_item_form(form)
    if errors:
        return render_template("form.html", item=item, action="Update",
                               categories=_all_categories(), errors=errors, form=form)
    item["name"] = form["name"].strip()
    item["brand"] = form.get("brand", item.get("brand", "")).strip()
    item["category"] = form.get("category", item["category"])
    item["quantity"] = int(form["quantity"])
    item["unit"] = form.get("unit", item["unit"]).strip()
    item["expiry_date"] = form.get("expiry_date", item["expiry_date"])
    item["daily_usage"] = float(form.get("daily_usage") or 0)
    item["supplier"] = form.get("supplier", item["supplier"]).strip()
    item["notes"] = form.get("notes", item["notes"]).strip()
    item["sustainability_score"] = int(form.get("sustainability_score", item["sustainability_score"]))
    return redirect(url_for("index"))

# ── Startup ───────────────────────────────────────────────────────────────────

load_sample_data()

if __name__ == "__main__":
    app.run(debug=True, port=5000)

@app.route("/api/recipes", methods=["GET"])
def recipe_suggestions():
    """Return AI recipe suggestions using Food & Beverage items expiring within 30 days."""
    expiring_food = [
        i for i in inventory
        if i["category"] == "Food & Beverage"
        and i.get("expiry_date")
        and 0 <= (days_until_expiry(i["expiry_date"]) or 999) <= 30
    ]
    if not expiring_food:
        expiring_food = [i for i in inventory if i["category"] == "Food & Beverage"]

    if not expiring_food:
        return jsonify({"recipes": None, "message": "No food items found in inventory.", "ai_powered": False})

    ingredient_list = []
    for i in expiring_food:
        days_exp = days_until_expiry(i["expiry_date"]) if i.get("expiry_date") else None
        label = f"{i['name']} ({i['quantity']} {i['unit']}"
        if days_exp is not None:
            label += f", expires in {days_exp} days"
        label += ")"
        ingredient_list.append(label)

    use_ai = bool(os.getenv("ANTHROPIC_API_KEY", "")) and ANTHROPIC_AVAILABLE
    if use_ai:
        try:
            client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            prompt = f"""You are a creative, sustainability-focused chef assistant helping a small organization reduce food waste.

These food ingredients are in inventory and should be used soon:

{chr(10).join(f'- {ing}' for ing in ingredient_list)}

Suggest 3 practical recipes that use as many of these ingredients as possible to prevent waste.
For each recipe provide exactly this format:

🍽️ [Recipe Name]
Uses: [comma-separated ingredients from the list]
[2-3 sentence description of the dish and why it's great for reducing waste]

Be creative, practical, and prioritize the ingredients expiring soonest."""

            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=700,
                messages=[{"role": "user", "content": prompt}]
            )
            return jsonify({"recipes": message.content[0].text.strip(), "ingredients": ingredient_list, "ai_powered": True})
        except Exception:
            pass

    # Rule-based fallback
    names = [i["name"] for i in expiring_food]
    fallback = (
        f"🍽️ Use-It-All Stir Fry\n"
        f"Uses: {', '.join(names[:3])}\n"
        f"Combine your ingredients in a hot pan with olive oil. Season with salt and pepper for a quick, zero-waste meal.\n\n"
        f"🍽️ Everything Smoothie\n"
        f"Uses: {', '.join(names[:2])}\n"
        f"Blend together with ice for a nutritious drink that uses up perishables fast.\n\n"
        f"🍽️ Pantry Soup\n"
        f"Uses: {', '.join(names)}\n"
        f"Simmer everything in vegetable broth for 20 minutes. A classic waste-reduction meal."
    )
    return jsonify({"recipes": fallback, "ingredients": ingredient_list, "ai_powered": False})
