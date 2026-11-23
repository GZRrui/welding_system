"""Browser check for the login, prediction, recommendation, history and logout flow."""

import os

from playwright.sync_api import expect, sync_playwright

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel=os.getenv("BROWSER_SMOKE_CHANNEL"))
    page = browser.new_page()
    page.goto(os.getenv("BROWSER_SMOKE_URL", "http://127.0.0.1:4173"))
    page.get_by_label("密码", exact=True).fill(os.environ["BROWSER_SMOKE_PASSWORD"])
    page.get_by_role("button", name="登录", exact=True).click()
    page.get_by_role("button", name="工况预测", exact=True).click()
    page.get_by_role("button", name="计算工况预测").click()
    expect(page.get_by_text("95%边际预测区间", exact=True)).to_be_visible(timeout=30_000)
    page.get_by_role("button", name="工艺参数推荐", exact=True).click()
    page.get_by_role("button", name="提交搜索任务").click()
    expect(page.get_by_text("导出 all_candidates", exact=True)).to_be_visible(timeout=60_000)
    page.get_by_role("button", name="模型与历史", exact=True).click()
    expect(page.get_by_role("heading", name="预测与推荐历史")).to_be_visible()
    page.get_by_role("button", name="退出登录", exact=True).click()
    expect(page.get_by_role("heading", name="管理员登录")).to_be_visible()
    browser.close()
