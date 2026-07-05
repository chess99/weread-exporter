from __future__ import annotations

import subprocess
from pathlib import Path

from playwright.async_api import BrowserContext, Page, async_playwright

from .capture import CANVAS_HOOK


class ProfileInUseError(RuntimeError):
    pass


class BrowserSession:
    def __init__(self, profile: Path, *, headless: bool = False) -> None:
        self.profile = Path(profile)
        self.headless = headless
        self._playwright = None
        self.context: BrowserContext | None = None

    async def __aenter__(self) -> "BrowserSession":
        self.profile.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        try:
            self.context = await self._playwright.chromium.launch_persistent_context(
                str(self.profile),
                headless=self.headless,
                viewport={"width": 1200, "height": 900},
                args=["--disable-blink-features=AutomationControlled"],
            )
        except Exception as exc:  # Playwright wraps profile-lock failures.
            await self._playwright.stop()
            if "existing browser session" in str(exc):
                raise ProfileInUseError(
                    f"Playwright profile is already in use: {self.profile}. "
                    "Close the Chromium window or run `weread-export clean-locks`."
                ) from exc
            raise
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self.context:
            await self.context.close()
        if self._playwright:
            await self._playwright.stop()

    async def new_reader_page(self) -> Page:
        if not self.context:
            raise RuntimeError("browser session is not started")
        page = await self.context.new_page()
        await page.add_init_script(CANVAS_HOOK)
        return page


def clean_profile_locks(profile: Path) -> int:
    profile = Path(profile).resolve()
    profile_literal = str(profile).replace("'", "''")
    script = (
        f"$profile = '{profile_literal}'; "
        "$procs = Get-CimInstance Win32_Process | Where-Object { "
        "$_.Name -match 'chrome|chromium' -and $_.CommandLine -like \"*$profile*\" "
        "}; foreach($p in $procs){ Stop-Process -Id $p.ProcessId -Force }; "
        "Write-Output $procs.Count"
    )
    completed = subprocess.run(["powershell", "-NoProfile", "-Command", script], text=True, capture_output=True)
    try:
        return int(completed.stdout.strip().splitlines()[-1])
    except Exception:
        return 0
