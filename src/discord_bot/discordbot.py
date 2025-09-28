"""
Discord → Frontend JSON Mirror Bot (Windows-friendly)
-----------------------------------------------------
- Mirrors any message (DM or server) to your frontend inlet via HTTP POST
- Acknowledges DMs so you know it worked
- Robust logging, retries, graceful shutdown

ENV (.env or PowerShell $env:):
    DISCORD_BOT_TOKEN=YOUR_TOKEN
    INGEST_URL=http://127.0.0.1:3000/ingest
    INGEST_SECRET=dev-secret

Requires:
    pip install discord.py aiohttp python-dotenv

Discord portal:
    Turn ON "Message Content Intent" for your bot.
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
import discord
from dotenv import load_dotenv


# --------------------------- config & setup ---------------------------



def _load_env_best_effort() -> None:
    """Load .env from cwd and (if running inside a repo) parent dirs."""
    # load .env in current working dir
    load_dotenv()
    # also try a repo-root .env (two levels up from this file), if available
    try:
        here = Path(__file__).resolve()
        for parent in [here.parent, *here.parents]:
            env_path = parent / ".env"
            if env_path.exists():
                load_dotenv(env_path, override=False)
                break
    except Exception:
        pass


@dataclass(frozen=True)
class Config:
    token: str
    ingest_url: str = "http://127.0.0.1:3000/ingest"
    ingest_secret: str = "dev-secret"
    request_timeout: float = 10.0

    @staticmethod
    def from_env() -> "Config":
        _load_env_best_effort()
        token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
        if not token:
            raise RuntimeError("DISCORD_BOT_TOKEN is missing. Put it in .env or set $env:DISCORD_BOT_TOKEN")
        return Config(
            token=token,
            ingest_url=os.getenv("INGEST_URL", "http://127.0.0.1:3000/ingest").strip(),
            ingest_secret=os.getenv("INGEST_SECRET", "dev-secret").strip(),
            request_timeout=float(os.getenv("INGEST_TIMEOUT", "10.0")),
        )


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )


# --------------------------- HTTP client ---------------------------

class IngestClient:
    """Persistent aiohttp client with small retry/backoff."""

    def __init__(self, url: str, secret: str, timeout: float = 10.0):
        self.url = url
        self.secret = secret
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None
        self._log = logging.getLogger("ingest")

    async def start(self) -> None:
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
            self._log.debug("HTTP session started")

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
            self._log.debug("HTTP session closed")

    async def post(self, payload: Dict[str, Any], attempts: int = 3) -> bool:
        await self.start()
        assert self._session is not None

        headers = {
            "X-Ingest-Secret": self.secret,
            "Content-Type": "application/json",
        }

        for i in range(attempts):
            try:
                async with self._session.post(self.url, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        self._log.info("POST ok (len=%s)", len(payload.get("content", "")))
                        return True
                    txt = await resp.text()
                    self._log.warning("POST http %s: %s", resp.status, txt[:300])
                    # For 4xx (auth/validation), no point retrying
                    if 400 <= resp.status < 500:
                        return False
            except Exception as e:
                self._log.warning("POST attempt %d failed: %s", i + 1, e)
            # backoff: 0.3, 0.6, 1.2
            await asyncio.sleep(0.3 * (2 ** i))
        return False


# --------------------------- utilities ---------------------------

def attachments_to_list(msg: discord.Message) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for a in msg.attachments:
        out.append(
            {
                "id": str(a.id),
                "filename": a.filename,
                "content_type": a.content_type,
                "size": a.size,
                "url": a.url,  # CDN url (respect channel privacy)
            }
        )
    return out


def build_payload(message: discord.Message) -> Dict[str, Any]:
    # created_at is timezone-aware UTC; use ISO 8601
    created = message.created_at.isoformat()
    channel_type = "DM" if isinstance(message.channel, discord.DMChannel) else "GUILD_TEXT"
    channel_name = getattr(message.channel, "name", "DM")

    guild_info: Optional[Dict[str, Any]] = None
    if hasattr(message, "guild") and message.guild is not None:
        guild_info = {"id": str(message.guild.id), "name": message.guild.name}

    payload: Dict[str, Any] = {
        "id": str(message.id),
        "author": {
            "id": str(message.author.id),
            "name": str(message.author),  # Username#1234 or display name
        },
        "guild": guild_info,
        "channel": {"id": str(message.channel.id), "type": channel_type, "name": channel_name},
        "content": message.content or "",
        "attachments": attachments_to_list(message),
        "created_at": created,
        "source": "discord",
        "traceId": f"disc-{message.id}",
    }
    return payload


# --------------------------- the bot ---------------------------

class MirrorBot(discord.Client):
    def __init__(self, ingest: IngestClient, **kwargs: Any):
        super().__init__(**kwargs)
        self.ingest = ingest
        self.log = logging.getLogger("bot")

    async def on_ready(self) -> None:
        self.log.info("Logged in as %s (id=%s)", self.user, getattr(self.user, "id", "?"))
        try:
            await self.change_presence(
                status=discord.Status.online, activity=discord.Game("Mirroring messages → JSON")
            )
        except Exception:
            pass

    async def on_message(self, message: discord.Message) -> None:
        # Ignore bots (including ourselves)
        if message.author.bot:
            return

        payload = build_payload(message)
        ok = await self.ingest.post(payload)

        # DM: explicit acknowledgement (visible)
        if isinstance(message.channel, discord.DMChannel):
            try:
                await message.channel.send(
                    "✅ Sent your message to the frontend." if ok else "⚠️ Couldn't reach the frontend inlet."
                )
            except Exception:
                pass
        else:
            # Server: subtle signal to avoid spam
            try:
                await message.add_reaction("📤" if ok else "⚠️")
            except Exception:
                pass


# --------------------------- entrypoint ---------------------------

async def main() -> None:
    setup_logging()
    cfg = Config.from_env()

    intents = discord.Intents.default()
    intents.message_content = True   # REQUIRED to read message text
    intents.dm_messages = True       # explicit for DMs

    ingest = IngestClient(cfg.ingest_url, cfg.ingest_secret, timeout=cfg.request_timeout)
    bot = MirrorBot(ingest=ingest, intents=intents)

    try:
        await bot.start(cfg.token)
    finally:
        await ingest.close()
        # discord.py cleans up its own HTTP session on logout/close.


if __name__ == "__main__":
    # Run with:   python -m src.discord_bot.bot   (from repo root)
    # or just:    python bot.py                    (if this file is standalone)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
