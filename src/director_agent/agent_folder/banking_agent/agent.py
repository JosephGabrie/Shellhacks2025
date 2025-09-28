from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import json, statistics, os

# Optional env
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ADK
from google.adk.agents import Agent
from google.adk.tools.function_tool import FunctionTool
try:
    from google.adk.a2a import A2AServer
    _HAS_A2A = True
except Exception:
    _HAS_A2A = False


if not os.getenv("GOOGLE_API_KEY"):
    print("WARNING: GOOGLE_API_KEY not set; Agent will fail without it.")


# ---------- helpers ----------
def _parse_iso(ts: str) -> Optional[datetime]:
    try:
        if ts.endswith("Z"):
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        dt = datetime.fromisoformat(ts)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None

def _in_window(dt: Optional[datetime], since: Optional[datetime], until: Optional[datetime]) -> bool:
    if dt is None: return False
    if since and dt < since: return False
    if until and dt > until: return False
    return True

def _flatten_txns(bank: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for acct in bank.get("user", {}).get("accounts", []):
        for t in acct.get("transactions", []) or []:
            t2 = dict(t)
            t2["_account"] = acct.get("nickname") or acct.get("account_type")
            out.append(t2)
    return out

def _recurring(bank: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for acct in bank.get("user", {}).get("accounts", []):
        for r in acct.get("recurring_payments", []) or []:
            out.append({
                "account": acct.get("nickname") or acct.get("account_type"),
                "name": r.get("name"),
                "amount": r.get("amount"),
                "frequency": r.get("frequency"),
                "next_charge": r.get("next_charge"),
            })
    return out

# ---------- main function ----------
def bank_window_summary(
    inline_json: Optional[Dict[str, Any]] = None,
    window: Optional[Dict[str, str]] = None,
    currency: str = "USD",
    templateParams: Optional[Dict[str, Any]] = None,
    traceId: Optional[str] = None,
) -> Dict[str, Any]:
    # fallback to built-in BANK_JSON
    bank = inline_json if inline_json is not None else BANK_JSON

    since = _parse_iso((window or {}).get("since") or "")
    until = _parse_iso((window or {}).get("until") or "")
    currency = (currency or "USD").upper()

    txns = _flatten_txns(bank)
    debits: List[float] = []
    debit_txns: List[Dict[str, Any]] = []
    by_merchant: Dict[str, Dict[str, Any]] = {}
    by_category: Dict[str, Dict[str, Any]] = {}

    for t in txns:
        dt = _parse_iso(t.get("posted_at") or t.get("created_at") or "")
        if not _in_window(dt, since, until):
            continue
        if (t.get("type") or "").lower() != "debit":
            continue

        amt = abs(float(t.get("amount", 0.0)))
        debits.append(amt)
        debit_txns.append(t)

        merch = (t.get("merchant") or {}).get("name") or (t.get("description") or "unknown").strip()
        cat = (t.get("category") or (t.get("merchant") or {}).get("category") or "uncategorized").strip()

        bm = by_merchant.setdefault(merch, {"merchant": merch, "spend": 0.0, "count": 0})
        bm["spend"] += amt
        bm["count"] += 1

        bc = by_category.setdefault(cat, {"category": cat, "spend": 0.0, "count": 0})
        bc["spend"] += amt
        bc["count"] += 1

    totals = {"spend": round(sum(debits), 2), "count": len(debits)}

    anomalies: List[Dict[str, Any]] = []
    if debits:
        mean = statistics.mean(debits)
        std = statistics.pstdev(debits) if len(debits) > 1 else 0.0
        thresh = max(mean + 2 * std, 500.0)
        for t in sorted(debit_txns, key=lambda x: abs(float(x.get("amount", 0))), reverse=True)[:10]:
            amt = abs(float(t.get("amount", 0.0)))
            if amt >= thresh:
                anomalies.append({
                    "amount": round(amt, 2),
                    "description": t.get("description"),
                    "merchant": (t.get("merchant") or {}).get("name"),
                    "posted_at": t.get("posted_at") or t.get("created_at"),
                    "account": t.get("_account"),
                })

    findings = {
        "totals": totals,
        "byMerchant": sorted(
            [{"merchant": k, "spend": round(v["spend"], 2), "count": v["count"]}
             for k, v in by_merchant.items()],
            key=lambda x: x["spend"], reverse=True
        ),
        "byCategory": sorted(
            [{"category": k, "spend": round(v["spend"], 2), "count": v["count"]}
             for k, v in by_category.items()],
            key=lambda x: x["spend"], reverse=True
        ),
        "recurring": _recurring(bank),
        "anomalies": anomalies,
    }

    if since and until:
        days = (until - since).days or 1
        window_caption = f"last {days} days"
    else:
        window_caption = "selected window"

    summary = f"In the {window_caption} you spent {currency} {findings['totals']['spend']:,.2f} across {findings['totals']['count']} transactions."
    if anomalies:
        summary += f" Flagged {len(anomalies)} potential anomalies."
    sms = f"{window_caption.capitalize()} spend {currency} {findings['totals']['spend']:,.2f}; {findings['totals']['count']} txns."

    return {"status": "ok", "data": {"findings": findings}, "summary": summary, "sms": sms, "error": None, "traceId": traceId}


# ---------- wrap as a FunctionTool ----------
BankSummaryTool = FunctionTool(bank_window_summary)

# ---------- Agent ----------
banking_agent = Agent(
    name="banking_agent",
    model="gemini-2.0-flash",
    description="Banking agent: summarizes spending from a JSON dataset.",
    tools=[BankSummaryTool],
    instruction=(
        "Your name is Banky, a very productive and helpful banking agent. Your personality is friendly and you are excited to help customers. When you respond, make sure it is in complete sentences as you were talking. When invoked, call tool `bank_window_summary` with fields from payload "
        "(inline_json, window, currency, templateParams, traceId). "
        "Return ONLY the tool result JSON. When asked any banking related question, use the tool `bank_window_summary` to get the data and respond."
    ),
)


# ---------- built-in JSON data at the bottom ----------
BANK_JSON = {
  "meta": {
    "generated_at": "2025-09-27T12:00:00",
    "schema_version": "1.0",
    "institution": {
      "name": "Acme Community Bank (Simulated)",
      "institution_id": "acme-sim-001",
      "support_email": "support@acme-sim.example",
      "api": {
        "base_url": "https://api.acme-sim.example/v1",
        "endpoints": [
          "/accounts",
          "/transactions",
          "/contacts",
          "/cards",
          "/transfers",
          "/statements"
        ],
        "auth": "oauth2 - token simulated"
      }
    }
  },
  "user": {
    "user_id": "92e365ca-c1f3-4c0c-b5cb-3f7d2db512dc",
    "full_name": "Daniel Batista",
    "email": "daniel.batista+sim@example.com",
    "phone": "+1-305-555-0199",
    "primary_city": "Miami, FL",
    "accounts": [
      {
        "account_id": "f3328d22-9db8-417c-b78c-4cb2ce5aaa5c",
        "account_type": "checking",
        "nickname": "Everyday Checking",
        "account_number": "133387262473",
        "routing_number": "178108013",
        "currency": "USD",
        "balance": 6436.19,
        "available_balance": 6386.19,
        "hold_amount": 50.0,
        "opened_at": "2023-09-18T12:00:00",
        "interest_rate_apr": 0.0,
        "transactions": [
          {
            "transaction_id": "e0b61a95-3ec8-438c-8408-a58f3cb8a195",
            "created_at": "2025-07-13T22:58:00",
            "posted_at": "2025-07-15T09:58:00",
            "amount": 811.85,
            "currency": "USD",
            "type": "credit",
            "status": "posted",
            "description": "ACH Credit - Whole Foods Market",
            "merchant": {
              "name": "Whole Foods Market",
              "mcc": "5411",
              "category": "Groceries",
              "city": "Miami",
              "state": "FL"
            },
            "category": "Groceries",
            "mcc": "5411",
            "running_balance": 3808.07
          },
          {
            "transaction_id": "597c979f-976b-4a8c-b868-88b042c5ba0a",
            "created_at": "2025-07-16T05:15:00",
            "posted_at": "2025-07-16T10:15:00",
            "amount": 801.38,
            "currency": "USD",
            "type": "credit",
            "status": "posted",
            "description": "ACH Credit - Starbucks",
            "merchant": {
              "name": "Starbucks",
              "mcc": "5814",
              "category": "Coffee Shop",
              "city": "Coral Gables",
              "state": "FL"
            },
            "category": "Coffee Shop",
            "mcc": "5814",
            "running_balance": 5234.77
          },
          {
            "transaction_id": "c9b09059-3580-4481-91c5-fd6c3850303e",
            "created_at": "2025-07-21T07:52:00",
            "posted_at": "2025-07-22T21:52:00",
            "amount": -42.53,
            "currency": "USD",
            "type": "debit",
            "status": "posted",
            "description": "Purchase - Target",
            "merchant": {
              "name": "Target",
              "mcc": "5311",
              "category": "Retail",
              "city": "Miami",
              "state": "FL"
            },
            "category": "Retail",
            "mcc": "5311",
            "running_balance": 6436.19
          },
          {
            "transaction_id": "ab096b70-9f07-475b-8dbc-0d9acd12c7f4",
            "created_at": "2025-07-24T16:48:00",
            "posted_at": "2025-07-26T01:48:00",
            "amount": -41.64,
            "currency": "USD",
            "type": "debit",
            "status": "posted",
            "description": "Purchase - Spotify",
            "merchant": {
              "name": "Spotify",
              "mcc": "4899",
              "category": "Digital Subscription",
              "city": "New York",
              "state": "NY"
            },
            "category": "Digital Subscription",
            "mcc": "4899",
            "running_balance": 4157.48
          },
          {
            "transaction_id": "07d25e72-58c9-4ec8-bbd0-954c5310b9e2",
            "created_at": "2025-07-29T23:43:00",
            "posted_at": "2025-07-30T02:43:00",
            "amount": -82.08,
            "currency": "USD",
            "type": "debit",
            "status": "posted",
            "description": "Purchase - Lyft",
            "merchant": {
              "name": "Lyft",
              "mcc": "4121",
              "category": "Ride Share",
              "city": "Miami",
              "state": "FL"
            },
            "category": "Ride Share",
            "mcc": "4121",
            "running_balance": 4899.88
          },
          {
            "transaction_id": "c83f90fb-4318-491e-a2d1-c5f50548b67a",
            "created_at": "2025-07-30T18:53:00",
            "posted_at": "2025-07-31T17:53:00",
            "amount": 944.99,
            "currency": "USD",
            "type": "credit",
            "status": "posted",
            "description": "ACH Credit - Netflix",
            "merchant": {
              "name": "Netflix",
              "mcc": "4899",
              "category": "Digital Subscription",
              "city": "Los Gatos",
              "state": "CA"
            },
            "category": "Digital Subscription",
            "mcc": "4899",
            "running_balance": 4433.39
          },
          {
            "transaction_id": "e5cf291b-09e4-4531-b720-df8b02fdabda",
            "created_at": "2025-08-07T00:46:00",
            "posted_at": "2025-08-08T16:46:00",
            "amount": -398.68,
            "currency": "USD",
            "type": "debit",
            "status": "posted",
            "description": "Purchase - Spotify",
            "merchant": {
              "name": "Spotify",
              "mcc": "4899",
              "category": "Digital Subscription",
              "city": "New York",
              "state": "NY"
            },
            "category": "Digital Subscription",
            "mcc": "4899",
            "running_balance": 4067.35
          },
          {
            "transaction_id": "e6366738-9df0-44af-9013-92e7c46b3a62",
            "created_at": "2025-08-18T05:19:00",
            "posted_at": "2025-08-18T21:19:00",
            "amount": -228.77,
            "currency": "USD",
            "type": "debit",
            "status": "posted",
            "description": "Purchase - Target",
            "merchant": {
              "name": "Target",
              "mcc": "5311",
              "category": "Retail",
              "city": "Miami",
              "state": "FL"
            },
            "category": "Retail",
            "mcc": "5311",
            "running_balance": 4653.16
          },
          {
            "transaction_id": "1a6099bb-a7b6-44da-9eb5-1c2f6c3bfdac",
            "created_at": "2025-08-23T04:46:00",
            "posted_at": "2025-08-23T09:46:00",
            "amount": -169.66,
            "currency": "USD",
            "type": "debit",
            "status": "posted",
            "description": "Purchase - Spotify",
            "merchant": {
              "name": "Spotify",
              "mcc": "4899",
              "category": "Digital Subscription",
              "city": "New York",
              "state": "NY"
            },
            "category": "Digital Subscription",
            "mcc": "4899",
            "running_balance": 2996.22
          },
          {
            "transaction_id": "d45d95a8-cc85-40f7-a179-3d2e0179c945",
            "created_at": "2025-08-23T15:39:00",
            "posted_at": "2025-08-25T13:39:00",
            "amount": -949.88,
            "currency": "USD",
            "type": "debit",
            "status": "posted",
            "description": "Purchase - Starbucks",
            "merchant": {
              "name": "Starbucks",
              "mcc": "5814",
              "category": "Coffee Shop",
              "city": "Coral Gables",
              "state": "FL"
            },
            "category": "Coffee Shop",
            "mcc": "5814",
            "running_balance": 4227.06
          },
          {
            "transaction_id": "13e0a1bb-ee51-49d5-904f-b4b17d27ab8f",
            "created_at": "2025-08-24T19:12:00",
            "posted_at": "2025-08-26T11:12:00",
            "amount": -27.94,
            "currency": "USD",
            "type": "debit",
            "status": "posted",
            "description": "Purchase - Spotify",
            "merchant": {
              "name": "Spotify",
              "mcc": "4899",
              "category": "Digital Subscription",
              "city": "New York",
              "state": "NY"
            },
            "category": "Digital Subscription",
            "mcc": "4899",
            "running_balance": 4199.12
          },
          {
            "transaction_id": "2606996c-65c1-42ff-b7a7-0b6770120062",
            "created_at": "2025-08-25T18:05:00",
            "posted_at": "2025-08-27T18:05:00",
            "amount": -29.97,
            "currency": "USD",
            "type": "debit",
            "status": "posted",
            "description": "Purchase - Whole Foods Market",
            "merchant": {
              "name": "Whole Foods Market",
              "mcc": "5411",
              "category": "Groceries",
              "city": "Miami",
              "state": "FL"
            },
            "category": "Groceries",
            "mcc": "5411",
            "running_balance": 5176.94
          },
          {
            "transaction_id": "76772ca5-82b2-420f-878f-800d70d6dd97",
            "created_at": "2025-08-28T10:45:00",
            "posted_at": "2025-08-28T14:45:00",
            "amount": -22.78,
            "currency": "USD",
            "type": "debit",
            "status": "posted",
            "description": "Purchase - Apple",
            "merchant": {
              "name": "Apple",
              "mcc": "5734",
              "category": "Electronics",
              "city": "Cupertino",
              "state": "CA"
            },
            "category": "Electronics",
            "mcc": "5734",
            "running_balance": 6478.72
          },
          {
            "transaction_id": "ebcf1204-3604-4a28-9a23-37ad2e7a7c81",
            "created_at": "2025-08-29T08:36:00",
            "posted_at": "2025-08-30T06:36:00",
            "amount": -208.78,
            "currency": "USD",
            "type": "debit",
            "status": "posted",
            "description": "Purchase - Amazon",
            "merchant": {
              "name": "Amazon",
              "mcc": "5969",
              "category": "Online Retail",
              "city": "Seattle",
              "state": "WA"
            },
            "category": "Online Retail",
            "mcc": "5969",
            "running_balance": 5025.99
          },
          {
            "transaction_id": "7ee4fc76-2aa0-45f2-9ccc-adc79cccea55",
            "created_at": "2025-08-29T10:09:00",
            "posted_at": "2025-08-30T22:09:00",
            "amount": -17.95,
            "currency": "USD",
            "type": "debit",
            "status": "posted",
            "description": "Purchase - RentPay LLC",
            "merchant": {
              "name": "RentPay LLC",
              "mcc": "6513",
              "category": "Rent",
              "city": "Miami",
              "state": "FL"
            },
            "category": "Rent",
            "mcc": "6513",
            "running_balance": 4881.93
          },
          {
            "transaction_id": "c3b693f1-166a-4a35-b9fa-5d3b4ea746d5",
            "created_at": "2025-08-31T14:43:00",
            "posted_at": "2025-09-01T00:43:00",
            "amount": -44.03,
            "currency": "USD",
            "type": "debit",
            "status": "posted",
            "description": "Purchase - Starbucks",
            "merchant": {
              "name": "Starbucks",
              "mcc": "5814",
              "category": "Coffee Shop",
              "city": "Coral Gables",
              "state": "FL"
            },
            "category": "Coffee Shop",
            "mcc": "5814",
            "running_balance": 4981.96
          },
          {
            "transaction_id": "79912f9c-9084-4882-85cd-deb32b14f445",
            "created_at": "2025-09-01T13:19:00",
            "posted_at": "2025-09-01T13:19:00",
            "amount": -113.13,
            "currency": "USD",
            "type": "debit",
            "status": "posted",
            "description": "Purchase - Lyft",
            "merchant": {
              "name": "Lyft",
              "mcc": "4121",
              "category": "Ride Share",
              "city": "Miami",
              "state": "FL"
            },
            "category": "Ride Share",
            "mcc": "4121",
            "running_balance": 3694.94
          },
          {
            "transaction_id": "b7d12b40-bc18-49fa-817c-0699cf39b82f",
            "created_at": "2025-09-06T13:33:00",
            "posted_at": "2025-09-06T19:33:00",
            "amount": -55.01,
            "currency": "USD",
            "type": "debit",
            "status": "posted",
            "description": "Purchase - RentPay LLC",
            "merchant": {
              "name": "RentPay LLC",
              "mcc": "6513",
              "category": "Rent",
              "city": "Miami",
              "state": "FL"
            },
            "category": "Rent",
            "mcc": "6513",
            "running_balance": 3639.93
          },
          {
            "transaction_id": "68a92c07-bb7d-4ae3-a9fb-f4c29a4b3e74",
            "created_at": "2025-09-06T14:33:00",
            "posted_at": "2025-09-07T23:33:00",
            "amount": 1139.56,
            "currency": "USD",
            "type": "credit",
            "status": "posted",
            "description": "ACH Credit - Apple",
            "merchant": {
              "name": "Apple",
              "mcc": "5734",
              "category": "Electronics",
              "city": "Cupertino",
              "state": "CA"
            },
            "category": "Electronics",
            "mcc": "5734",
            "running_balance": 5206.91
          },
          {
            "transaction_id": "d992998d-5f4d-468b-833b-946d8263ff5e",
            "created_at": "2025-09-10T04:13:00",
            "posted_at": "2025-09-11T17:13:00",
            "amount": -187.13,
            "currency": "USD",
            "type": "debit",
            "status": "posted",
            "description": "Purchase - Lyft",
            "merchant": {
              "name": "Lyft",
              "mcc": "4121",
              "category": "Ride Share",
              "city": "Miami",
              "state": "FL"
            },
            "category": "Ride Share",
            "mcc": "4121",
            "running_balance": 4466.03
          },
          {
            "transaction_id": "114ec46f-d413-4516-9b62-28572f21da2d",
            "created_at": "2025-09-15T23:54:00",
            "posted_at": "2025-09-17T21:54:00",
            "amount": -151.53,
            "currency": "USD",
            "type": "debit",
            "status": "posted",
            "description": "Purchase - RentPay LLC",
            "merchant": {
              "name": "RentPay LLC",
              "mcc": "6513",
              "category": "Rent",
              "city": "Miami",
              "state": "FL"
            },
            "category": "Rent",
            "mcc": "6513",
            "running_balance": 3488.4
          },
          {
            "transaction_id": "cd0d2546-fd6e-47c6-8840-bf71fc3eb974",
            "created_at": "2025-09-26T16:40:00",
            "posted_at": "2025-09-27T11:40:00",
            "amount": 2344.02,
            "currency": "USD",
            "type": "credit",
            "status": "posted",
            "description": "ACH Credit - Target",
            "merchant": {
              "name": "Target",
              "mcc": "5311",
              "category": "Retail",
              "city": "Miami",
              "state": "FL"
            },
            "category": "Retail",
            "mcc": "5311",
            "running_balance": 6501.5
          }
        ],
        "pending_transactions": [
          {
            "transaction_id": "1197a18f-cc3a-4ff8-a288-6d52b307f26b",
            "created_at": "2025-09-26T09:00:00",
            "amount": -45.0,
            "currency": "USD",
            "type": "debit",
            "status": "pending",
            "description": "Pending Authorization - Shell Oil",
            "merchant": {
              "name": "Shell Oil",
              "mcc": "5541",
              "category": "Gas",
              "city": "Miami",
              "state": "FL"
            }
          }
        ],
        "cards": [
          {
            "card_id": "91a5594b-a4ca-4b95-b123-53b009db0816",
            "network": "VISA",
            "card_type": "debit",
            "last4": "6658",
            "exp_month": 8,
            "exp_year": 2029,
            "status": "active",
            "linked_account": "checking"
          }
        ],
        "recurring_payments": [
          {
            "name": "Spotify",
            "amount": -9.99,
            "frequency": "monthly",
            "next_charge": "2025-10-01T12:00:00"
          },
          {
            "name": "Netflix",
            "amount": -15.49,
            "frequency": "monthly",
            "next_charge": "2025-10-09T12:00:00"
          }
        ],
        "overdraft_protection": {
          "enabled": True,
          "limit": 500.0
        }
      },
      {
        "account_id": "c9b70841-2426-4365-aef3-f8bda44841d2",
        "account_type": "savings",
        "nickname": "Rainy Day Savings",
        "account_number": "236026064746",
        "routing_number": "872343098",
        "currency": "USD",
        "balance": 3137.82,
        "available_balance": 3137.82,
        "opened_at": "2022-11-13T12:00:00",
        "interest_rate_apr": 0.0399,
        "transactions": [
          {
            "transaction_id": "1f0bb1e9-60ea-4b5c-ae05-e8b0912460c5",
            "created_at": "2025-07-01T15:37:00",
            "posted_at": "2025-07-01T19:37:00",
            "amount": -113.69,
            "currency": "USD",
            "type": "debit",
            "status": "posted",
            "description": "Purchase - Target",
            "merchant": {
              "name": "Target",
              "mcc": "5311",
              "category": "Retail",
              "city": "Miami",
              "state": "FL"
            },
            "category": "Retail",
            "mcc": "5311",
            "running_balance": 283.54
          },
          {
            "transaction_id": "4211d8fe-6d47-4db9-a354-4d9df1a25d21",
            "created_at": "2025-07-25T05:26:00",
            "posted_at": "2025-07-25T20:26:00",
            "amount": -220.77,
            "currency": "USD",
            "type": "debit",
            "status": "posted",
            "description": "Purchase - Spotify",
            "merchant": {
              "name": "Spotify",
              "mcc": "4899",
              "category": "Digital Subscription",
              "city": "New York",
              "state": "NY"
            },
            "category": "Digital Subscription",
            "mcc": "4899",
            "running_balance": -12.56
          },
          {
            "transaction_id": "d6a48c30-fa52-4086-8827-63168694aaae",
            "created_at": "2025-07-26T22:48:00",
            "posted_at": "2025-07-28T03:48:00",
            "amount": 1248.31,
            "currency": "USD",
            "type": "credit",
            "status": "posted",
            "description": "ACH Credit - Starbucks",
            "merchant": {
              "name": "Starbucks",
              "mcc": "5814",
              "category": "Coffee Shop",
              "city": "Coral Gables",
              "state": "FL"
            },
            "category": "Coffee Shop",
            "mcc": "5814",
            "running_balance": 1235.75
          },
          {
            "transaction_id": "34015156-263a-4b60-aeb9-1d884c4a0558",
            "created_at": "2025-08-02T05:01:00",
            "posted_at": "2025-08-03T06:01:00",
            "amount": -172.93,
            "currency": "USD",
            "type": "debit",
            "status": "posted",
            "description": "Purchase - Lyft",
            "merchant": {
              "name": "Lyft",
              "mcc": "4121",
              "category": "Ride Share",
              "city": "Miami",
              "state": "FL"
            },
            "category": "Ride Share",
            "mcc": "4121",
            "running_balance": 397.23
          },
          {
            "transaction_id": "c5dc09f0-5077-4012-b4b0-38b83af032dd",
            "created_at": "2025-08-13T11:23:00",
            "posted_at": "2025-08-15T03:23:00",
            "amount": -56.22,
            "currency": "USD",
            "type": "debit",
            "status": "posted",
            "description": "Purchase - Lyft",
            "merchant": {
              "name": "Lyft",
              "mcc": "4121",
              "category": "Ride Share",
              "city": "Miami",
              "state": "FL"
            },
            "category": "Ride Share",
            "mcc": "4121",
            "running_balance": 227.32
          },
          {
            "transaction_id": "9090f54f-5326-483a-a171-de98e588d9e5",
            "created_at": "2025-09-18T14:19:00",
            "posted_at": "2025-09-18T20:19:00",
            "amount": 1902.07,
            "currency": "USD",
            "type": "credit",
            "status": "posted",
            "description": "ACH Credit - Starbucks",
            "merchant": {
              "name": "Starbucks",
              "mcc": "5814",
              "category": "Coffee Shop",
              "city": "Coral Gables",
              "state": "FL"
            },
            "category": "Coffee Shop",
            "mcc": "5814",
            "running_balance": 3137.82
          },
          {
            "transaction_id": "d4e75583-d5cb-42aa-89ca-42227cb16a27",
            "created_at": "2025-09-18T04:56:00",
            "posted_at": "2025-09-19T22:56:00",
            "amount": -19.11,
            "currency": "USD",
            "type": "debit",
            "status": "posted",
            "description": "Purchase - Whole Foods Market",
            "merchant": {
              "name": "Whole Foods Market",
              "mcc": "5411",
              "category": "Groceries",
              "city": "Miami",
              "state": "FL"
            },
            "category": "Groceries",
            "mcc": "5411",
            "running_balance": 208.21
          }
        ],
        "auto_transfer": {
          "enabled": True,
          "rule": "$25 weekly on Fridays"
        }
      }
    ],
    "contacts": [
      {
        "name": "Olivia Ramirez",
        "type": "person",
        "zelle_id": "olivia.r@bankmail.com",
        "phone": "+1-305-555-0111",
        "email": "olivia.r@bankmail.com",
        "notes": "roommate - rent split"
      },
      {
        "name": "Marcus Lee",
        "type": "person",
        "zelle_id": "(305)555-0172",
        "phone": "+1-305-555-0172",
        "email": "",
        "notes": "bandmate - gear reimbursements"
      },
      {
        "name": "University Bursar",
        "type": "organization",
        "zelle_id": "bursar@fiu.edu",
        "phone": "",
        "email": "bursar@fiu.edu",
        "notes": "tuition payments"
      }
    ],
    "direct_deposits": [
      {
        "employer": "Acme Tech LLC",
        "amount": 1245.73,
        "frequency": "biweekly",
        "last_deposit": "2025-09-13T12:00:00"
      }
    ],
    "last_login": "2025-09-17T21:00:00",
    "preferences": {
      "currency": "USD",
      "language": "en-US",
      "notifications": [
        "email",
        "push"
      ]
    }
  },
  "payees": [
    {
      "payee_id": "722eb7eb-0d1e-409d-833f-a2a254a71852",
      "name": "RentPay LLC",
      "account": "***1234",
      "category": "rent",
      "preferred_method": "ACH"
    },
    {
      "payee_id": "828025a0-589e-4e28-8b80-5969c8e30910",
      "name": "Utilities Co.",
      "account": "***9876",
      "category": "utilities",
      "preferred_method": "ACH"
    }
  ],
  "notes": "Synthetic dataset for a single customer. Safe for dev/testing."
}
   
