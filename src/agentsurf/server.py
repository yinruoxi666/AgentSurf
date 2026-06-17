from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from .browser import BrowserSession, PlaywrightBrowserSession
from .schemas import ClickRequest, Observation, OpenUrlRequest, TypeRequest


def create_app(session: BrowserSession | None = None):
    try:
        from fastapi import FastAPI
    except ModuleNotFoundError as exc:
        raise RuntimeError("FastAPI is not installed. Install with `python -m pip install -e .[server]`.") from exc

    browser = session or PlaywrightBrowserSession(
        headless=_env_bool("AGENTSURF_BROWSER_HEADLESS", default=True),
        executable_path=os.getenv("AGENTSURF_CHROME_EXECUTABLE"),
        channel=os.getenv("AGENTSURF_BROWSER_CHANNEL"),
        user_data_dir=os.getenv("AGENTSURF_CHROME_PROFILE_DIR"),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        start = getattr(browser, "start", None)
        if start is not None:
            await start()
        try:
            yield
        finally:
            close = getattr(browser, "close", None)
            if close is not None:
                await close()

    app = FastAPI(title="AgentSurf Browser Tool Server", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/open_url", response_model=Observation)
    async def open_url(payload: OpenUrlRequest) -> Observation:
        return await browser.open_url(payload.url)

    @app.post("/click", response_model=Observation)
    async def click(payload: ClickRequest) -> Observation:
        return await browser.click(payload.selector)

    @app.post("/type", response_model=Observation)
    async def type_text(payload: TypeRequest) -> Observation:
        return await browser.type_text(payload.selector, payload.text)

    @app.post("/screenshot", response_model=Observation)
    async def screenshot() -> Observation:
        return await browser.screenshot()

    return app


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
