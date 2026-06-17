from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any, Protocol

from .schemas import ActionType, BrowserAction, Observation


PLACEHOLDER_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


class BrowserSession(Protocol):
    async def open_url(self, url: str) -> Observation:
        ...

    async def click(self, selector: str) -> Observation:
        ...

    async def type_text(self, selector: str, text: str) -> Observation:
        ...

    async def screenshot(self) -> Observation:
        ...


async def execute_browser_action(session: BrowserSession, action: BrowserAction) -> Observation:
    if action.type == ActionType.OPEN_URL:
        if not action.url:
            raise ValueError("open_url action requires url")
        observation = await session.open_url(action.url)
    elif action.type == ActionType.CLICK:
        if not action.selector:
            raise ValueError("click action requires selector")
        observation = await session.click(action.selector)
    elif action.type == ActionType.TYPE:
        if not action.selector or action.text is None:
            raise ValueError("type action requires selector and text")
        observation = await session.type_text(action.selector, action.text)
    elif action.type in {ActionType.SCREENSHOT, ActionType.OBSERVE}:
        observation = await session.screenshot()
    elif action.type == ActionType.DONE:
        observation = await session.screenshot()
    else:
        raise ValueError(f"Unsupported action type: {action.type}")

    observation.action = action
    return observation


class InMemoryBrowserSession:
    def __init__(self, initial_url: str | None = None) -> None:
        self.current_url = initial_url
        self.title = "In-memory browser"
        self.action_log: list[BrowserAction] = []
        self.typed_values: dict[str, str] = {}

    async def start(self) -> "InMemoryBrowserSession":
        return self

    async def close(self) -> None:
        return None

    async def open_url(self, url: str) -> Observation:
        action = BrowserAction(type=ActionType.OPEN_URL, url=url)
        self.action_log.append(action)
        self.current_url = url
        self.title = url
        return self._observation(action)

    async def click(self, selector: str) -> Observation:
        action = BrowserAction(type=ActionType.CLICK, selector=selector)
        self.action_log.append(action)
        return self._observation(action, {"last_clicked": selector})

    async def type_text(self, selector: str, text: str) -> Observation:
        action = BrowserAction(type=ActionType.TYPE, selector=selector, text=text)
        self.action_log.append(action)
        self.typed_values[selector] = text
        return self._observation(action, {"typed_values": dict(self.typed_values)})

    async def screenshot(self) -> Observation:
        action = BrowserAction(type=ActionType.SCREENSHOT)
        return self._observation(action)

    def _observation(
        self,
        action: BrowserAction,
        extra_state: dict[str, Any] | None = None,
    ) -> Observation:
        ui_state: dict[str, Any] = {
            "mode": "in_memory",
            "actions": [entry.model_dump(mode="json") for entry in self.action_log],
        }
        if extra_state:
            ui_state.update(extra_state)
        return Observation(
            url=self.current_url,
            title=self.title,
            screenshot_base64=PLACEHOLDER_PNG_BASE64,
            ui_state=ui_state,
            action=action,
        )


class PlaywrightBrowserSession:
    def __init__(
        self,
        headless: bool = True,
        viewport: dict[str, int] | None = None,
        executable_path: str | None = None,
        channel: str | None = None,
        user_data_dir: str | None = None,
    ) -> None:
        self.headless = headless
        self.viewport = viewport or {"width": 1280, "height": 900}
        self.executable_path = executable_path or os.getenv("AGENTSURF_CHROME_EXECUTABLE")
        self.channel = channel or os.getenv("AGENTSURF_BROWSER_CHANNEL")
        self.user_data_dir = user_data_dir or os.getenv("AGENTSURF_CHROME_PROFILE_DIR")
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None

    async def start(self) -> "PlaywrightBrowserSession":
        try:
            from playwright.async_api import async_playwright
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Playwright is not installed. Install with `python -m pip install -e .[server]` "
                "and run `python -m playwright install chromium`."
            ) from exc

        self._playwright = await async_playwright().start()
        launch_options = self.launch_options()
        if self.user_data_dir:
            profile_dir = Path(self.user_data_dir).resolve()
            profile_dir.mkdir(parents=True, exist_ok=True)
            self._context = await self._playwright.chromium.launch_persistent_context(
                str(profile_dir),
                **launch_options,
                viewport=self.viewport,
            )
            self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        else:
            self._browser = await self._playwright.chromium.launch(**launch_options)
            self._context = await self._browser.new_context(viewport=self.viewport)
            self._page = await self._context.new_page()
        return self

    async def close(self) -> None:
        if self._context is not None:
            await self._context.close()
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()

    def launch_options(self) -> dict[str, Any]:
        launch_options: dict[str, Any] = {
            "headless": self.headless,
            "args": ["--no-first-run", "--disable-default-apps"],
        }
        if self.executable_path:
            launch_options["executable_path"] = self.executable_path
        elif self.channel:
            launch_options["channel"] = self.channel
        return launch_options

    async def open_url(self, url: str) -> Observation:
        page = await self._ensure_page()
        await page.goto(url, wait_until="domcontentloaded")
        return await self.screenshot()

    async def click(self, selector: str) -> Observation:
        page = await self._ensure_page()
        await page.locator(selector).click()
        return await self.screenshot()

    async def type_text(self, selector: str, text: str) -> Observation:
        page = await self._ensure_page()
        await page.locator(selector).fill(text)
        return await self.screenshot()

    async def screenshot(self) -> Observation:
        page = await self._ensure_page()
        screenshot = await page.screenshot(full_page=True)
        page_state = await self._extract_page_state(page)
        return Observation(
            url=page.url,
            title=await page.title(),
            screenshot_base64=base64.b64encode(screenshot).decode("ascii"),
            ui_state=page_state,
        )

    async def _ensure_page(self) -> Any:
        if self._page is None:
            await self.start()
        return self._page

    async def _extract_page_state(self, page: Any) -> dict[str, Any]:
        script = """
        () => {
          const nodes = Array.from(document.querySelectorAll('a,button,input,textarea,select,[role=button],[tabindex]'));
          const elements = nodes.slice(0, 120).map((node, index) => {
            const rect = node.getBoundingClientRect();
            const label = node.getAttribute('aria-label') || node.getAttribute('name') || node.id || '';
            const selector = node.id ? `#${node.id}` : `${node.tagName.toLowerCase()}:nth-of-type(${index + 1})`;
            return {
              selector,
              role: node.getAttribute('role') || node.tagName.toLowerCase(),
              label,
              type: node.getAttribute('type') || '',
              placeholder: node.getAttribute('placeholder') || '',
              text: (node.innerText || node.value || '').slice(0, 160),
              bounds: { x: rect.x, y: rect.y, width: rect.width, height: rect.height }
            };
          });
          return {
            visible_text: (document.body?.innerText || '').slice(0, 6000),
            elements
          };
        }
        """
        try:
            return await page.evaluate(script)
        except Exception:
            return {"visible_text": "", "elements": []}
