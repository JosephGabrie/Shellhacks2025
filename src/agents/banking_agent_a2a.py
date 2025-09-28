from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from pathlib import Path
import json
import statistics

# pip install google-adk
from google.adk.agents import LlmAgent
from google.adk.tools.function_tool import FunctionTool
from google.adk.a2a import A2AServer

BANK_JSON_DEFAULT = "Shellhacks2025/docs/simulated_bank_data_single.json"

# --------- helpers ---------
def _parse_iso(ts: str) -> Optional[datetime]:
    try:
        if ts.endswith("Z"):
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None

def _in_window(dt: Optional[datetime], since: Optional[datetime], until: Optional[datetime]) -> bool:
    if dt is None:
        return False
    if since and dt < since:
        return False
    if until and dt > until:
        return False
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

# --------- tool function ---------
def bank_window_summary_tool(
    json_path: Optional[str] = None,
    inline_json: Optional[Dict[str, Any]] = None,
    window: Optional[Dict[str, str]] = None,
    currency: str = "USD",
    templateParams: Optional[Dict[str, Any]] = None,
    traceId: Optional[str] = None,
) -> Dict[str, Any]:
    bank = inline_json if inline_json is not None else json.loads(Path(json_path or BANK_JSON_DEFAULT).read_text(encoding="utf-8"))

    since_s = (window or {}).get("since")
    until_s = (window or {}).get("until")
    since = _parse_iso(since_s) if since_s else None
    until = _parse_iso(until_s) if until_s else None
    currency = (currency or "USD").upper()

    txns = _flatten_txns(bank)

    debits: List[float] = []
    debit_txns: List[Dict[str, Any]] = []
    by_merchant: Dict[str, Dict[str, Any]] = {}
    by_category: Dict[str, Dict[str, Any]] = {}

    for t in txns:
        posted_at = t.get("posted_at") or t.get("created_at")
        dt = _parse_iso(posted_at) if posted_at else None
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
        big = sorted(debit_txns, key=lambda x: abs(float(x.get("amount", 0))), reverse=True)[:10]
        for t in big:
            amt = abs(float(t.get("amount", 0.0)))
            if amt >= thresh:
                anomalies.append({
                    "amount": round(amt, 2),
                    "description": t.get("description"),
                    "merchant": (t.get("merchant") or {}).get("name"),
                    "posted_at": t.get("posted_at") or t.get("created_at"),
                    "account": t.get("_account"),
                })

    byMerchant_list = sorted(by_merchant.values(), key=lambda x: x["spend"], reverse=True)
    byCategory_list = sorted(by_category.values(), key=lambda x: x["spend"], reverse=True)

    findings = {
        "totals": totals,
        "byMerchant": [{"merchant": m["merchant"], "spend": round(m["spend"], 2), "count": m["count"]} for m in byMerchant_list],
        "byCategory": [{"category": c["category"], "spend": round(c["spend"], 2), "count": c["count"]} for c in byCategory_list],
        "recurring": [r for r in _recurring(bank) if _in_window(_parse_iso(r.get("next_charge") or ""), since, until) or r.get("next_charge") is None],
        "anomalies": anomalies,
    }

    if since and until:
        days = (until - since).days or 1
        window_caption = f"last {days} days"
    else:
        window_caption = "selected window"

    spend, count = totals["spend"], totals["count"]
    summary = f"In the {window_caption} you spent {currency} {spend:,.2f} across {count} transactions."
    if anomalies:
        summary += f" Flagged {len(anomalies)} potential anomalies."

    sms = f"{window_caption.capitalize()} spend {currency} {spend:,.2f}; {count} txns."

    return {
        "status": "ok",
        "data": {"findings": findings},
        "summary": summary,
        "sms": sms,
        "error": None,
        "traceId": traceId,
    }

BankSummaryTool = FunctionTool.from_fn(
    fn=bank_window_summary_tool,
    name="bank_window_summary",
    description="Summarize spending, merchants, categories, recurring, anomalies for a time window.",
)

banking_agent = LlmAgent(
    name="banking_agent",
    description="Banking agent (A2A): summarizes spending from a JSON dataset.",
    tools=[BankSummaryTool],
    instruction=(
        "When invoked, call tool `bank_window_summary` with fields from payload "
        "(json_path or inline_json, window, currency, templateParams, traceId). "
        "Return ONLY the tool result JSON."
    ),
)

def serve(host: str = "127.0.0.1", port: int = 7001):
    server = A2AServer(host=host, port=port, agents=[banking_agent])
    print(f"[banking_agent] A2A server on {host}:{port}")
    server.run()

if __name__ == "__main__":
    serve()
