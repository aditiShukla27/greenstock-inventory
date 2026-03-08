# GreenStock — Design Documentation

## Problem & Solution

Small organizations (non-profits, cafes, university labs) waste resources through manual,
error-prone inventory tracking. They over-purchase perishables and lack visibility into
what's expiring or running low. **GreenStock** solves this with a lightweight, AI-assisted
web app that makes sustainable inventory management accessible without enterprise complexity.

---

## Architecture

```
greentech-inventory/
├── app.py                  # Flask application — routes, helpers, AI integration
├── templates/
│   ├── base.html           # Shared nav, styles, JS utilities
│   ├── index.html          # Dashboard — search, filter, item grid, insight modal
│   └── form.html           # Create / Edit item form
├── data/
│   └── sample_inventory.csv  # Synthetic dataset (15 items)
├── tests/
│   └── test_app.py         # 25 tests: happy paths, edge cases, unit tests
├── requirements.txt
├── .env.example
└── .gitignore
```

**Data layer**: In-memory Python list (loaded from CSV on startup). Designed to be a
drop-in replacement for SQLite/PostgreSQL in production by swapping `inventory` list
operations with DB queries.

---

## Tech Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Backend | Python 3.10+ / Flask 3.x | Lightweight, easy to extend, widely known |
| AI | Anthropic Claude (`claude-sonnet-4-20250514`) | Strong reasoning for sustainability advice |
| Frontend | Jinja2 + Vanilla JS | No build step required, fast dev cycle |
| Styling | Pure CSS with CSS variables | No framework dependency, custom aesthetic |
| Testing | pytest | Simple, powerful, zero config |
| Config | python-dotenv | Secure key management |

---

## AI Features

### 1. Contextual Inventory Insights (`/item/<id>/insights`)
- **What it does**: Given an item's quantity, daily usage, expiry date, supplier, and
  sustainability score, Claude generates a 2–3 sentence actionable insight covering
  urgency, waste reduction, and sustainable procurement.
- **Prompt strategy**: Structured prompt with explicit output constraints (≤60 words,
  no bullet points) to ensure consistent, scannable responses.
- **Fallback**: Rule-based logic checks expiry/stockout thresholds and sustainability
  score, producing templated warnings. Triggered when `ANTHROPIC_API_KEY` is absent
  or the API call fails.

### 2. AI Auto-Categorization (`/api/autocategorize`)
- **What it does**: Claude classifies an item name + notes into one of 9 predefined
  categories with a constrained prompt (reply with category name only).
- **Fallback**: Keyword matching across a dictionary of category → keywords. Returns
  `"Other"` for unrecognized items.

---

## Key Design Decisions

### Graceful AI Degradation
Every AI call is wrapped in try/except. If the API key is missing or the call fails,
the app transparently falls back to deterministic rule-based logic. The UI indicates
which mode was used ("✨ Powered by Claude AI" vs "⚙️ Rule-based fallback").

### In-Memory Store
Chosen for zero-setup portability. The trade-off is data loss on server restart, which
is acceptable for a prototype/demo. Production migration path: replace list operations
with SQLAlchemy ORM calls.

### Sustainability Score
A manual 1–10 field gives users agency. The live preview on the form (color-coded,
descriptive text) nudges toward higher scores. Future: auto-calculate from supplier
certifications or third-party ESG APIs.

### Status Indicators
Four-tier system (OK / WATCH / URGENT / EXPIRED) computed from both expiry date and
stockout projection. Dual-signal approach catches items that are fine by date but
critically low on stock, or vice versa.

---

## Data Safety

- All inventory data in `data/sample_inventory.csv` is **fully synthetic** — no real
  businesses, people, or PII.
- No web scraping. No external data sources at runtime except the Anthropic API.
- API key stored in `.env` (gitignored). `.env.example` documents required variables.

---

## Future Enhancements (Priority Order)

1. **Persistent storage**: SQLite via SQLAlchemy — one file, zero ops overhead.
2. **Reorder notifications**: Email/SMS via Twilio or SendGrid when stock < threshold.
3. **CSV import/export**: Bulk-upload existing spreadsheets, export reports.
4. **Visual asset scanning**: Integrate vision model to identify items from shelf photos.
5. **Sustainability dashboard**: Carbon-savings calculator, supplier comparison table.
6. **Multi-user / org support**: Simple auth with Flask-Login, per-org inventory spaces.
7. **Usage history**: Log quantity changes over time for better AI usage predictions.
8. **Waste report**: Monthly AI-generated summary of waste events and savings.

---

## Security Considerations

- API key never exposed client-side (server-side calls only)
- Input validation on all form fields (server-side in `_validate_item_form`)
- Delete confirmation via JS `confirm()` dialog prevents accidental data loss
- In production: add CSRF protection (Flask-WTF), rate limiting (Flask-Limiter),
  and HTTPS enforcement
