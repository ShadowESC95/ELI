"""
Web Automation plugin for ELI – uses Playwright's sync API.
No asyncio, no event loop conflicts – just works.
"""

from playwright.sync_api import sync_playwright, Browser, Page
from typing import Dict, Any, Optional
from .base import Plugin
from ..brain import config

# Global browser instance (reused across commands)
_playwright = None
_browser: Optional[Browser] = None
_page: Optional[Page] = None

def ensure_browser(headless: bool = True) -> Page:
    """Launch or reuse a browser instance (sync)."""
    global _playwright, _browser, _page
    if _page is None or _browser is None:
        _playwright = sync_playwright().start()
        _browser = _playwright.chromium.launch(headless=headless)
        _page = _browser.new_page()
        _page.set_default_timeout(10000)
    return _page

class WebAutomationPlugin(Plugin):
    name = "web_automation"
    description = "Control web browsers – navigate, search, click, fill, screenshot, extract."

    def navigate(self, args: Dict[str, Any]) -> Dict[str, Any]:
        url = args.get("url", "")
        if not url:
            return {"ok": False, "error": "No URL provided."}
        if not url.startswith("http"):
            url = "https://" + url
        try:
            page = ensure_browser(headless=config.get("web_headless", True))
            page.goto(url)
            title = page.title()
            return {
                "ok": True,
                "url": url,
                "title": title,
                "content": f"Navigated to {url} (title: {title})"
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def search(self, args: Dict[str, Any]) -> Dict[str, Any]:
        engine = args.get("engine", "google").lower()
        query = args.get("query", "")
        if not query:
            return {"ok": False, "error": "No search query provided."}
        search_urls = {
            "google": "https://www.google.com/search?q={}",
            "bing": "https://www.bing.com/search?q={}",
            "duckduckgo": "https://duckduckgo.com/?q={}",
            "yahoo": "https://search.yahoo.com/search?p={}",
            "youtube": "https://www.youtube.com/results?search_query={}",
            "amazon": "https://www.amazon.com/s?k={}",
            "wikipedia": "https://en.wikipedia.org/wiki/Special:Search?search={}",
        }
        url_template = search_urls.get(engine, search_urls["google"])
        url = url_template.format(query.replace(" ", "+"))
        try:
            page = ensure_browser(headless=config.get("web_headless", True))
            page.goto(url)
            title = page.title()
            return {
                "ok": True,
                "engine": engine,
                "query": query,
                "url": url,
                "title": title,
                "content": f"Searched {engine} for '{query}' – {title}"
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def click(self, args: Dict[str, Any]) -> Dict[str, Any]:
        selector = args.get("selector", "")
        text = args.get("text", "")
        if not selector and not text:
            return {"ok": False, "error": "No selector or text provided."}
        try:
            page = ensure_browser(headless=config.get("web_headless", True))
            if selector:
                page.click(selector)
                msg = f"Clicked element with selector '{selector}'"
            else:
                page.click(f"text={text}")
                msg = f"Clicked element with text '{text}'"
            return {"ok": True, "content": msg}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def fill(self, args: Dict[str, Any]) -> Dict[str, Any]:
        selector = args.get("selector", "")
        value = args.get("value", "")
        if not selector or not value:
            return {"ok": False, "error": "Missing selector or value."}
        try:
            page = ensure_browser(headless=config.get("web_headless", True))
            page.fill(selector, value)
            return {"ok": True, "content": f"Filled '{selector}' with '{value}'"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def screenshot(self, args: Dict[str, Any]) -> Dict[str, Any]:
        path = args.get("path", None)
        if not path:
            import time
            path = f"/tmp/eli_web_screenshot_{int(time.time())}.png"
        try:
            page = ensure_browser(headless=config.get("web_headless", True))
            page.screenshot(path=path, timeout=5000)
            return {"ok": True, "path": path, "content": f"Screenshot saved to {path}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def extract_text(self, args: Dict[str, Any]) -> Dict[str, Any]:
        selector = args.get("selector", None)
        try:
            page = ensure_browser(headless=config.get("web_headless", True))
            if selector:
                elements = page.query_selector_all(selector)
                texts = [el.text_content() for el in elements]
                content = "\n".join(filter(None, texts))
            else:
                content = page.text_content("body")
            return {"ok": True, "content": content.strip()[:1000] + "..." if len(content) > 1000 else content}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def close(self, args: Dict[str, Any]) -> Dict[str, Any]:
        global _playwright, _browser, _page
        try:
            if _page:
                _page.close()
                _page = None
            if _browser:
                _browser.close()
                _browser = None
            if _playwright:
                _playwright.stop()
                _playwright = None
            return {"ok": True, "content": "Browser closed."}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    actions = {
        "navigate": navigate,
        "search": search,
        "click": click,
        "fill": fill,
        "screenshot": screenshot,
        "extract": extract_text,
        "close": close,
    }
