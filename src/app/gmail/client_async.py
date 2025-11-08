"""
Async Gmail client with parallel message processing.
"""

from __future__ import annotations
from typing import Optional, List, Dict, Tuple
from bs4 import BeautifulSoup
import asyncio
import re
import base64
import html

from app.storage.local_state import PointerStorage
from app.logging import logger
from app.utils.retry_async import async_retry_with_backoff
from googleapiclient.errors import HttpError


class AsyncGmailClient:
    """
    Async Gmail client helpers for fetching message bodies and preparing
    classification-ready summaries (full body + recent head).
    Designed for pointer-based incremental ingestion with parallel processing.
    """

    #: OAuth scope used for read-only access to Gmail.
    SCOPES_READONLY = ["https://www.googleapis.com/auth/gmail.readonly"]

    #: Heuristics for trimming quoted history / replies when extracting the head.
    #: Matches common markers across EN/RU/UA and typical provider footers.
    _QUOTE_SEPARATORS = (
        "-----original message-----",
        "original message",
        "wrote:",
        "написал", "написала", "написав", "пише",
        "через linkedin",
    )

    def __init__(
        self,
        gmail_service,
        max_batch_size: int = 325,
        head_max_chars: int = 2000,
        rate_limiter=None,
    ) -> None:
        """
        Initialize the client with an authenticated Gmail service.

        Args:
            gmail_service: An instance of googleapiclient Gmail service, already
                authorized with read-only scope.
            max_batch_size: Maximum number of messages to fetch per batch (default: 325)
            head_max_chars: Maximum characters in email head (default: 2000)
            rate_limiter: Optional AsyncRateLimiter instance for API rate limiting
        """
        self.svc = gmail_service
        self.max_batch_size = max_batch_size
        self.head_max_chars = head_max_chars
        self.rate_limiter = rate_limiter

    def _extract_recent_head(self, raw_text: str, *, max_chars: Optional[int] = None) -> str:
        """
        Extracts the most recent (relevant) portion of an email body.

        This method trims out quoted history, signatures, and reply chains that
        appear below the latest message. It detects common patterns like
        'On ... wrote:', 'Original Message', or '-----Original Message-----'.
        It also removes quoted lines starting with '>' and limits the total
        length of the resulting head.

        Args:
            raw_text (str): The full plain text of the email body.
            max_chars (int, optional): Maximum number of characters to keep
                in the head section. Defaults to self.head_max_chars.

        Returns:
            str: Cleaned "recent head" text — the upper, most relevant portion
            of the message to be analyzed for classification.
        """
        if max_chars is None:
            max_chars = self.head_max_chars
        head = raw_text or ""
        lower = head.casefold()
        cut = None
        for m in self._QUOTE_SEPARATORS:
            p = lower.find(m)
            if p != -1:
                cut = p if cut is None else min(cut, p)
        if cut is not None:
            head = head[:cut]

        lines = []
        for ln in head.splitlines():
            if ln.lstrip().startswith(">"):
                continue
            lines.append(ln)
        head = "\n".join(lines)

        if len(head) > max_chars:
            head = head[:max_chars]
        return head.strip()

    @async_retry_with_backoff(max_retries=3, initial_delay=1.0, exceptions=(HttpError,))
    async def _list_messages_page(
        self,
        user_id: str,
        query: str,
        max_results: int,
        page_token: Optional[str] = None,
    ) -> Dict:
        """
        Fetch a single page of message IDs from Gmail API with retry logic and rate limiting (async).

        Args:
            user_id: Gmail user ID (typically "me")
            query: Gmail search query
            max_results: Maximum number of results per page
            page_token: Optional page token for pagination

        Returns:
            Response dictionary from Gmail API

        Raises:
            HttpError: If API call fails after retries
        """
        # Apply rate limiting if configured
        if self.rate_limiter:
            await self.rate_limiter.acquire(blocking=True)
        
        # Run synchronous API call in thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.svc.users().messages().list(
                userId=user_id,
                q=query,
                maxResults=max_results,
                pageToken=page_token
            ).execute()
        )

    async def _list_until_marker(
        self,
        limit: int,
        marker_id: Optional[str],
        query: Optional[str] = None,
    ) -> Tuple[List[str], bool]:
        """
        Collect up to `limit` newest->oldest message IDs (async).
        Stop natively when `marker_id` is encountered (exclusive).
        Returns (collected_ids, seen_marker).
        """
        user_id = "me"
        collected: List[str] = []
        page_token: Optional[str] = None
        seen_marker = False
        query_str = query or "-in:spam -in:trash"

        try:
            while len(collected) < limit:
                remaining = max(1, limit - len(collected))
                resp = await self._list_messages_page(
                    user_id=user_id,
                    query=query_str,
                    max_results=min(500, remaining),
                    page_token=page_token,
                )

                msgs = resp.get("messages", [])
                if not msgs:
                    break

                # NOTE: Gmail returns IDs newest->oldest per page; we preserve this order.
                for m in msgs:
                    mid = m["id"]
                    if marker_id and mid == marker_id:
                        seen_marker = True
                        break
                    collected.append(mid)
                    if len(collected) >= limit:
                        break

                if seen_marker or len(collected) >= limit:
                    break

                page_token = resp.get("nextPageToken")
                if not page_token:
                    break

        except HttpError as e:
            logger.error(f"Failed to list messages: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error listing messages: {e}")
            raise

        return collected, seen_marker

    def _decode_b64(self, data: str) -> str:
        """
        Decode Gmail's URL-safe base64 payload into UTF-8 text.

        Args:
            data (str): URL-safe base64-encoded string from Gmail API.

        Returns:
            str: Decoded UTF-8 string. Invalid sequences are replaced safely.
        """
        return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="replace")

    def _normalize_whitespace(self, text: str) -> str:
        """
        Performs minimal and safe whitespace normalization on plain text.

        - Unescapes HTML entities (&nbsp;, etc.)
        - Removes zero-width characters
        - Converts wrapped <https://...> links into plain URLs
        - Reduces multiple blank lines to a maximum of two
        - Collapses redundant spaces within lines while preserving line breaks

        Args:
            text (str): Raw text input (may contain newlines and HTML escapes).

        Returns:
            str: Whitespace-normalized text that remains human-readable and
            suitable for exact phrase matching.
        """
        text = html.unescape(text)
        text = re.sub(r"[\u200B-\u200D\uFEFF]", "", text)
        text = re.sub(r"<(https?://[^>\s]+)>", r"\1", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = "\n".join(" ".join(line.split()) for line in text.splitlines())
        return text.strip()

    def _html_to_text(self, html_str: str) -> str:
        """
        Converts HTML content into a clean plain-text representation.

        - Strips <script> and <style> elements entirely
        - Removes known quote blocks (.gmail_quote, <blockquote>)
        - Converts <br> and <p> tags into line breaks
        - Keeps the text structure readable while avoiding excessive spacing

        Args:
            html_str (str): Raw HTML email body.

        Returns:
            str: Normalized plain text suitable for further processing or
            phrase matching.
        """
        # Use html.parser to avoid XML/HTML warning, or explicitly use lxml with features
        try:
            soup = BeautifulSoup(html_str, "html.parser")
        except Exception:
            # Fallback to lxml if html.parser fails
            soup = BeautifulSoup(html_str, "lxml")
        for tag in soup(["script", "style"]):
            tag.decompose()
        for q in soup.select(".gmail_quote, blockquote"):
            q.decompose()
        for br in soup.find_all(["br"]):
            br.replace_with("\n")
        for p in soup.find_all("p"):
            if p.text and not p.text.endswith("\n"):
                p.append("\n")
        text = soup.get_text(separator="", strip=False)
        return self._normalize_whitespace(text)

    def _extract_text_from_payload(self, payload: dict) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract plain and HTML bodies from a Gmail payload tree.

        Traversal prefers `text/plain` but will also return raw `text/html`
        (if present) for later conversion. Recurses through multipart structures.

        Args:
            payload (dict): Gmail message payload node.

        Returns:
            Tuple[Optional[str], Optional[str]]: (plain_text, html_text)
            where each element may be None if not available.
        """
        if not payload:
            return None, None

        mime = payload.get("mimeType")
        body = payload.get("body", {})
        data = body.get("data")

        # leaf node with inline data
        if data and isinstance(data, str):
            decoded = self._decode_b64(data)
            if mime == "text/plain":
                return self._normalize_whitespace(decoded), None
            if mime == "text/html":
                return None, decoded  # raw HTML; convert later
            # some providers send text/* with charset issues; fallback to plain path
            if mime and mime.startswith("text/"):
                return self._normalize_whitespace(decoded), None

        # multipart
        parts = payload.get("parts") or []
        plain_best, html_best = None, None
        for p in parts:
            p_plain, p_html = self._extract_text_from_payload(p)
            if p_plain and not plain_best:
                plain_best = p_plain
            if p_html and not html_best:
                html_best = p_html
            if plain_best and html_best:
                break
        return plain_best, html_best

    @async_retry_with_backoff(max_retries=3, initial_delay=1.0, exceptions=(HttpError,))
    async def _fetch_message(self, message_id: str) -> Dict:
        """
        Fetch a single message from Gmail API with retry logic and rate limiting (async).

        Args:
            message_id: Gmail message ID

        Returns:
            Message dictionary from Gmail API

        Raises:
            HttpError: If API call fails after retries
        """
        # Apply rate limiting if configured
        if self.rate_limiter:
            await self.rate_limiter.acquire(blocking=True)
        
        # Run synchronous API call in thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.svc.users().messages().get(
                userId="me",
                id=message_id,
                format="full",
                metadataHeaders=["From", "Subject"]
            ).execute()
        )

    async def _process_single_message(self, mid: str) -> Optional[Dict]:
        """
        Process a single message ID and return its brief representation.

        Args:
            mid: Gmail message ID

        Returns:
            Optional[Dict]: Message brief dict or None if processing failed
        """
        try:
            m = await self._fetch_message(mid)
            headers = {h["name"]: h["value"] for h in m.get("payload", {}).get("headers", [])}
            plain, html_raw = self._extract_text_from_payload(m.get("payload", {}))

            if plain:
                text_full = plain
            elif html_raw:
                text_full = self._html_to_text(html_raw)
            else:
                text_full = ""

            head = self._extract_recent_head(text_full, max_chars=self.head_max_chars)

            return {
                "id": mid,
                "from": headers.get("From", ""),
                "subject": headers.get("Subject", ""),
                "text_full": text_full,
                "head": head,
                "internalDate": m.get("internalDate"),
                "threadId": m.get("threadId"),
            }
        except HttpError as e:
            logger.error(f"Failed to fetch message {mid}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error processing message {mid}: {e}")
            return None

    async def get_message_briefs(
        self,
        ids: List[str],
        *,
        max_concurrent: int = 10
    ) -> List[Dict]:
        """
        Fetches and prepares brief representations of Gmail messages in parallel.

        For each message ID, retrieves metadata and body content, producing
        both the full plain text (`text_full`) and a trimmed, recent-only
        version (`head`) for classification.

        Each entry includes:
            - id: Gmail message ID
            - from: Sender header
            - subject: Subject header
            - text_full: Entire body text (plain or converted from HTML)
            - head: Cleaned top portion of the body (most relevant part)
            - internalDate: Message timestamp
            - threadId: Gmail thread identifier

        Args:
            ids: List of Gmail message IDs to fetch
            max_concurrent: Maximum number of concurrent message fetches (default: 10)

        Returns:
            List[Dict]: A list of structured message summaries.
        """
        # Limit batch size to avoid API rate limits
        processed_ids = ids[:self.max_batch_size] if len(ids) > self.max_batch_size else ids

        if len(ids) > self.max_batch_size:
            logger.warning(f"Limiting message fetch to {self.max_batch_size} messages (requested {len(ids)})")

        # Process messages in parallel with semaphore to limit concurrency
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def process_with_semaphore(mid: str) -> Optional[Dict]:
            async with semaphore:
                return await self._process_single_message(mid)

        # Create tasks for all messages
        tasks = [process_with_semaphore(mid) for mid in processed_ids]
        
        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out None results and exceptions
        out: List[Dict] = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Exception in message processing: {result}")
                continue
            if result is not None:
                out.append(result)

        logger.debug(f"Successfully processed {len(out)}/{len(processed_ids)} messages")
        return out

    async def collect_new_messages_once(
        self,
        storage: PointerStorage,
        *,
        pointer_key: str = "gmail:last_processed_id",
        limit: int = 200,
        query: Optional[str] = None,
    ) -> Tuple[List[str], str, bool]:
        """
        Returns:
          - ids_to_process: newest -> oldest, excluding the marker itself
          - head_id: newest id of the *first fetched page* (used to advance pointer after processing)
          - has_more: True if marker was NOT seen within `limit` (there may be more unseen messages)

        Behavior:
          - Always attempt to collect up to `limit`.
          - If no marker (first run/crash): simply return up to `limit`.
          - If marker exists: stop as soon as the marker appears (exclusive).
        """
        marker = storage.get(pointer_key)

        ids, seen_marker = await self._list_until_marker(limit=limit, marker_id=marker, query=query)
        if not ids:
            head_probe, _ = await self._list_until_marker(limit=1, marker_id=None, query=query)
            head_id = head_probe[0] if head_probe else ""
            return [], head_id, (False if marker is None else not seen_marker)

        head_id = ids[0]

        if marker is None and head_id:
            storage.set(pointer_key, head_id)

        has_more = not seen_marker if marker else False
        return ids, head_id, has_more

    def advance_pointer_after_processing(
        self,
        storage: PointerStorage,
        head_id: str,
        *,
        pointer_key: str = "gmail:last_processed_id"
    ) -> None:
        """
        Advance the stored ingestion pointer after successful processing.

        This sets the marker to the newest message ID of the last fetch cycle.
        Call this only after all messages from the current run have been handled.

        Args:
            storage (PointerStorage): Key-value storage for the marker.
            head_id (str): The newest message ID from the last batch.
            pointer_key (str, optional): Storage key for the marker. Defaults to
                "gmail:last_processed_id".
        """
        if head_id:
            storage.set(pointer_key, head_id)

