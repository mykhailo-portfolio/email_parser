# src/app/utils/filters.py
"""
Filtering and classification utilities (simple pipeline).

Pipeline per run:
1) Stage-1: keep emails that mention a known company (by body head)
2) Stage-2a: keep only emails that contain any phrase (pos/neg)
3) Stage-2b: for each company select the newest email (by internalDate)
4) Stage-2c: classify that single email via "first-hit-wins" (approve/decline)
"""

from __future__ import annotations
from typing import List, Dict, Tuple
from app.utils.transform import normalize_soft, normalize_company
from app.utils.patterns import PHRASES_POS, PHRASES_NEG, SKIP_HINTS


def should_skip(email: dict) -> bool:
    """
    Returns True if the message looks like an ad, aggregator alert,
    newsletter, or OTP/2FA system message.

    Matching is done on normalized `subject + head` only.
    """
    hay = normalize_soft(f"{email.get('subject','')} {email.get('head','')}")
    return any(h in hay for h in SKIP_HINTS)

# ---------------------------------------------------------------------
# STAGE 1 — COMPANY MATCHING (by head only)
# ---------------------------------------------------------------------
def filter_by_company(emails: List[dict], companies: List[str]) -> Dict[str, List[dict]]:
    """
    Filter emails that contain at least one company name in the normalized head.

    Args:
        emails: Message briefs from GmailClient; must include "head".
        companies: Company names (raw) from Sheets.

    Returns:
        Mapping company -> list of matched email dicts.
    """
    result: Dict[str, List[dict]] = {}
    norm_companies = {c: normalize_company(c) for c in companies}
    BODY_WINDOW = 6000  # safe window for long auto-footers

    for email in emails:
        head_norm = normalize_soft(email.get("head", "") or "")
        body_norm = ""

        if should_skip(email):
            continue
        
        # lazy build body_norm only if needed
        for comp, norm in norm_companies.items():
            if not norm:
                continue
            if norm in head_norm:
                result.setdefault(comp, []).append(email)
                break
        else:
            # not found in head → fallback to full body window
            text_full = (email.get("text_full") or "")[:BODY_WINDOW]
            if text_full:
                body_norm = normalize_soft(text_full)
                for comp, norm in norm_companies.items():
                    if norm and norm in body_norm:
                        result.setdefault(comp, []).append(email)
                        break

    return result

# ---------------------------------------------------------------------
# PHRASE INDEXES (normalized)
# ---------------------------------------------------------------------
def _build_phrase_indexes() -> Tuple[list[str], list[str]]:
    """
    Prepare normalized phrase lists (longer first).
    """
    pos_norm = sorted([normalize_soft(p) for p in PHRASES_POS if p], key=len, reverse=True)
    neg_norm = sorted([normalize_soft(p) for p in PHRASES_NEG if p], key=len, reverse=True)
    return pos_norm, neg_norm


def _contains_any(text_norm: str, phrases_norm: list[str]) -> bool:
    """
    Returns True if any phrase is a substring of text_norm.
    """
    for p in phrases_norm:
        if p and p in text_norm:
            return True
    return False


def _first_hit_indices(text_norm: str, pos_norm: list[str], neg_norm: list[str]) -> Tuple[int, int]:
    """
    Find first occurrence indices for any POS and any NEG phrase.
    Returns (-1, -1) if not found.
    """
    pos_idx = -1
    for p in pos_norm:
        i = text_norm.find(p)
        if i != -1 and (pos_idx == -1 or i < pos_idx):
            pos_idx = i

    neg_idx = -1
    for p in neg_norm:
        i = text_norm.find(p)
        if i != -1 and (neg_idx == -1 or i < neg_idx):
            neg_idx = i

    return pos_idx, neg_idx


# ---------------------------------------------------------------------
# SIMPLE PIPELINE FOR LATEST-FIRST CLASSIFICATION
# ---------------------------------------------------------------------
def classify_latest(filtered: Dict[str, List[dict]]) -> Dict[str, Dict[str, List[dict]]]:
    """
    For each company:
      - select the newest email (by internalDate) among company-related emails
      - classify that single email by "first-hit-wins":
          * if neither POS nor NEG is found -> review
          * if both found -> whichever appears first wins
          * otherwise -> approve/decline accordingly

    Returns:
        {
          "approve": {company: [email]},
          "decline": {company: [email]},
          "review":  {company: [email]}
        }
    """
    pos_norm, neg_norm = _build_phrase_indexes()
    out = {"approve": {}, "decline": {}, "review": {}}

    for company, emails in filtered.items():
        # newest by internalDate
        def _ts(msg: dict) -> int:
            try:
                return int(msg.get("internalDate") or 0)
            except Exception:
                return 0

        if not emails:
            continue

        latest = max(emails, key=_ts)
        head_norm = normalize_soft(latest.get("head", ""))

        # compute first-hit indices (or -1)
        pos_idx, neg_idx = _first_hit_indices(head_norm, pos_norm, neg_norm)

        if pos_idx == -1 and neg_idx == -1:
            bucket = "review"
        elif pos_idx != -1 and neg_idx == -1:
            bucket = "approve"
        elif neg_idx != -1 and pos_idx == -1:
            bucket = "decline"
        else:
            bucket = "approve" if pos_idx < neg_idx else "decline"

        out[bucket].setdefault(company, []).append(latest)

    return out
