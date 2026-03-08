# 🌿 GreenStock — Sustainable Inventory Assistant

> A lightweight, AI-powered inventory tool for non-profits, small cafes, and university labs.
> Track assets, prevent waste, and make greener procurement choices — powered by Claude AI.

---

## Quick Start

### Prerequisites
- Python 3.10+
- An Anthropic API key ([get one at console.anthropic.com](https://console.anthropic.com/))

### Run Commands

```bash
# 1. Enter the project folder
cd greentech-inventory

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
cp .env.example .env
# Edit .env and paste your ANTHROPIC_API_KEY

# 5. Run the app
python3 app.py
# → Open http://localhost:5000
```

> **No API key?** The app works fully without one — all AI features fall back to rule-based logic automatically.

### Test Commands

```bash
python -m unittest tests.test_app -v
```

---

## Candidate Name: Aditi Shukla

**Scenario Chosen:** 🌿 Green-Tech Inventory Assistant

**Estimated Time Spent:** 6 hours

---

## Features

| Feature | Description |
|---------|-------------|
| **Dashboard** | Stats overview, item grid, search & filter by category/status |
| **Create / Edit / Delete** | Full CRUD for inventory items with input validation |
| **🧠 Smart Item Profile** | Type an item name → Claude predicts shelf life, expiry date, storage tips, spoilage signs, eco score, and daily usage — all auto-filled |
| **🤖 Structured AI Insights** | Per-item analysis with 5 color-coded cards: Urgency, Storage, Spoilage Signs, Waste Reduction, Eco Swap |
| **🏷️ Auto-Categorize** | Claude classifies items into the right category from just the name |
| **🍳 Recipe Ideas** | Claude suggests recipes using expiring Food & Beverage items to prevent waste |
| **🔄 Substitution Bot** | Mark item as out of stock → Claude finds creative substitutes from current inventory |
| **📸 Receipt Scanner** | Upload any receipt photo → Claude reads it and auto-adds all items with predicted expiry dates |
| **Rule-Based Fallback** | Every AI feature degrades gracefully when API is unavailable |

---
## FallBacks
🧠 Smart Item Profile
If Claude is unavailable, the app uses a keyword dictionary with 16 common items pre-loaded. For example, typing "milk" automatically returns 7 days shelf life, litres as the unit, and Food & Beverage as the category. Any item not in the dictionary returns a sensible default profile.
🤖 Structured Insights
If Claude is unavailable, the app runs threshold-based rules against the item's data. It checks days until expiry (flags anything under 7 days as urgent), days until stockout based on daily usage rate, and sustainability score (flags anything under 3 as low eco). Results are returned in the same format as the AI response.
🏷️ Auto-Categorize
If Claude is unavailable, the app matches the item name against a keyword dictionary covering all 9 categories. For example "coffee", "cheese", and "milk" map to Food & Beverage, "paper" and "pen" map to Office Supplies, "bleach" and "soap" map to Cleaning & Sanitation, and so on. Anything unrecognized defaults to "Other".
🍳 Recipe Ideas
If Claude is unavailable, the app returns 3 hardcoded template recipes — a stir fry, a smoothie, and a soup — populated with whatever Food & Beverage items are currently in stock.
🔄 Substitution Bot
If Claude is unavailable, the app finds other items in the same category as the out-of-stock item and suggests the first match as a substitute. For example if you're out of milk it finds other Food & Beverage items in your inventory.
📸 Receipt Scanner
If Claude is unavailable, the app returns a clear error message letting the user know AI is required for receipt scanning, rather than crashing. This is the one feature with no rule-based fallback since reading an image requires vision AI.

## AI Disclosure

**Did you use an AI assistant?** Yes — Claude (Anthropic) via claude.ai for code generation, design, and iteration.

**How did you verify the suggestions?**
- Ran all 35 tests after every change to confirm correctness
- Manually tested every route, form, and AI feature end-to-end in the browser
- Reviewed all generated code line-by-line before including it
- Deliberately tested edge cases: no API key, expired items, zero quantity, invalid dates

**Examples of suggestions I rejected or changed:**

1. **Database suggestion rejected** — Claude initially suggested SQLite with Flask-SQLAlchemy for persistence. I kept it as an in-memory list loaded from CSV instead, eliminating setup friction for the demo. The migration path is documented in DESIGN.md.

2. **Verbose insight format changed** — Claude originally generated insights as a single prose paragraph. I changed it to a structured JSON response with 5 distinct fields (urgency, storage, spoilage_signs, waste_tip, eco_swap) so the UI could render them as color-coded cards — much faster to scan.

3. **Receipt scanner prompt redesigned** — The first approach just asked Claude for JSON and got inconsistent output. I improved it by embedding a concrete JSON example directly in the prompt and explicitly telling Claude what NOT to include (TOTAL, CASH, CHANGE lines), making output reliable and parseable every time.

---

## Tradeoffs & Prioritization

**What I cut to stay within the 6 hour limit:**
- Persistent storage (SQLite) — in-memory resets on restart; migration path documented
- User authentication — single-user assumed for demo
- Push/email reorder alerts — documented as next feature
- Carbon savings calculator dashboard

**What I would build next:**
1. SQLite persistence via SQLAlchemy — drop-in swap, ~1 hour
2. Email/SMS reorder alerts when stock drops below threshold (Twilio)
3. CSV bulk import for migrating existing spreadsheets
4. Shelf photo scanning — point camera at shelf, AI identifies and counts items
5. Monthly waste report — AI-generated PDF summary of waste events and savings

**Known limitations:**
- Data resets on server restart (in-memory store)
- No authentication — single user assumed
- Receipt scanner works best with clear, well-lit photos
- AI insights are stateless — no memory across sessions
- Stockout estimates assume constant daily usage rate

---

## Project Structure

```
greentech-inventory/
├── app.py                    # Flask app — all routes, helpers, AI integration
├── templates/
│   ├── base.html             # Shared layout, nav, global styles
│   ├── index.html            # Dashboard — stats, search, filter, item grid
│   ├── form.html             # Create/edit form with AI smart profile
│   └── scan_receipt.html     # Receipt scanner page
├── data/
│   └── sample_inventory.csv  # 15 synthetic items (no real data)
├── tests/
│   └── test_app.py           # 35 tests: happy paths, edge cases, unit tests
├── DESIGN.md                 # Architecture, decisions, future enhancements
├── requirements.txt
├── .env.example              # Required environment variables (no secrets)
└── .gitignore                # Excludes .env, venv, pycache
```

---

## Security Notes
- API key stored in `.env` (gitignored) — never committed to repo
- All AI calls made server-side — key never exposed to browser
- Input validation on all form fields server-side
- Synthetic data only — no real personal information anywhere

---

## Video
(https://youtu.be/SVyBR5259cU)
