# -*- coding: utf-8 -*-
"""crawler.py — Amazon 页面抓取（单浏览器 + 多 tab 并发）

并发模型（用户确认的正确模型）：
    一个 ChromiumPage（浏览器进程）+ N 个 ChromiumTab（标签页），
    多线程各自 acquire/release 一个独立 tab，跨 tab 并发抓取。
    不用多浏览器实例——DrissionPage 4.1.1.4 多实例并发必崩（PageDisconnectedError）。

页面状态判定：page_not_found / sold_out / crawl_error(captcha·blocked·超时·空白) / parse_error
重试策略（方案 17）：404 不重试；sold_out 刷新一次确认；技术错误按 retry 重试；captcha 新 tab 重试 1 次；parse_error 刷新一次。
"""
from __future__ import annotations

import random
import threading
import time
from decimal import Decimal

from DrissionPage import ChromiumOptions, ChromiumPage

from amazon.parser import (
    collect_promotion_raw, parse_code, parse_coupon,
    parse_main_price, parse_save, select_main_price,
)
from amazon.selectors import (
    TITLE_404, TITLE_BLOCKED, TITLE_CAPTCHA,
)
from models import CrawlResult, PageStatus, ReportRow

DEFAULT_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')


class AmazonBrowser:
    """单浏览器 + tab 池。

    - 一个 ChromiumPage（一个浏览器进程），预创建 tabs 个标签页；
    - acquire() 取一个空闲 tab（池空时新建），release() 归还；
    - rebuild() 关闭异常 tab 并补新（captcha/断开时用）；
    - cookie 是浏览器级共享（同域），setup 初始化一次即可。
    """

    def __init__(self, headless: bool = True, us_zip: str = '90210',
                 proxy: str | None = None, tabs: int = 1):
        self.us_zip = us_zip
        # 运行环境使用固定 VPN；只有显式配置 proxy 时才设置浏览器代理，
        # 不自动继承 HTTP_PROXY/HTTPS_PROXY，避免意外切换出口。
        self.proxy = proxy
        co = ChromiumOptions()
        co.set_argument('--disable-blink-features=AutomationControlled')
        co.set_argument('--start-maximized')
        co.set_argument('--lang=en-US,en')
        co.set_argument(f'--user-agent={DEFAULT_UA}')
        if headless:
            co.headless(True)
        if self.proxy:
            # 注意：set_proxy 需要 'host:port' 格式（不带协议和尾斜杠），
            # 否则 Chrome 不生效会加载离线页（dino）
            co.set_proxy(self.proxy)
        self.page = ChromiumPage(co)
        self._lock = threading.Lock()
        self._free: list = []      # 空闲 tab
        self._live: set = set()    # 存活 tab 的 id
        for _ in range(max(1, int(tabs))):
            tab = self._create_tab()
            self._free.append(tab)
        self._inited = False

    # ---------- tab 池 ----------
    def _create_tab(self):
        """创建一个已登记但尚未放入空闲池的 tab。"""
        try:
            tab = self.page.new_tab('about:blank')
        except Exception:
            time.sleep(2)
            tab = self.page.new_tab('about:blank')
        with self._lock:
            self._live.add(id(tab))
        return tab

    def acquire(self):
        """取一个空闲 tab；池空时创建一个仅归当前调用方持有的 tab。"""
        with self._lock:
            if self._free:
                return self._free.pop()
        return self._create_tab()

    def release(self, tab):
        """归还 tab。断开的 tab 丢弃（下次 acquire 会自动新建）。"""
        with self._lock:
            if id(tab) in self._live and tab not in self._free:
                self._free.append(tab)

    def rebuild(self, tab):
        """关闭异常 tab，返回一个仅归当前调用方持有的新 tab。"""
        with self._lock:
            self._live.discard(id(tab))
        try:
            tab.close()
        except Exception:
            pass
        return self._create_tab()

    # ---------- 初始化 ----------
    def setup(self) -> bool:
        """初始化三要素（URL + zip cookie），cookie 浏览器级共享，一次即可。失败返回 False"""
        try:
            self.page.get('https://www.amazon.com/?language=en_US', timeout=30000)
            try:
                self.page.wait.doc_loaded(timeout=15)
            except Exception:
                time.sleep(3)
            for _ in range(3):
                try:
                    self.page.run_js(
                        f"document.cookie = 'sp-cdn={self.us_zip}|M|{self.us_zip}; path=/; domain=.amazon.com';")
                    break
                except Exception:
                    time.sleep(2)
            time.sleep(1)
            self._inited = True
            return True
        except Exception as e:
            print(f'[setup] 浏览器初始化失败: {type(e).__name__}: {e}', flush=True)
            return False

    # ---------- 单次抓取 ----------
    def fetch_once(self, tab, row: ReportRow, cfg: dict) -> CrawlResult:
        t0 = time.time()
        cr = CrawlResult(asin=row.asin)
        cr.expected_type = row.h_type
        url = f'https://www.amazon.com/dp/{row.asin}?language=en_US'
        try:
            time.sleep(random.uniform(cfg['delay_min'], cfg['delay_max']))
            tab.get(url)
            try:
                tab.wait.doc_loaded(timeout=cfg['page_timeout'])
            except Exception:
                pass
            cr.page_url = tab.url
            cr.page_title = (tab.title or '').strip()[:200]

            title = cr.page_title.lower()
            # 404
            if any(k in title for k in TITLE_404):
                cr.status = PageStatus.PAGE_NOT_FOUND
                return cr
            # Captcha
            if any(k in title for k in TITLE_CAPTCHA) or 'captcha' in cr.page_url.lower():
                cr.status = PageStatus.CRAWL_ERROR
                cr.error = 'captcha: 机器人验证页'
                return cr
            # 访问受限
            if any(k in title for k in TITLE_BLOCKED) or 'sorry' in title and 'make sure' in title:
                cr.status = PageStatus.CRAWL_ERROR
                cr.error = 'blocked: 访问受限'
                return cr

            # 等待价格出现（headless 首屏可能不渲染 → 只在价格未出现时刷新一次）
            try:
                tab.wait.ele_displayed('css:.a-price, css:.priceToPay', timeout=cfg['price_wait_timeout'])
            except Exception:
                try:
                    tab.refresh()
                    tab.wait.doc_loaded(timeout=cfg['page_timeout'])
                except Exception:
                    pass
                try:
                    tab.wait.ele_displayed('css:.a-price, css:.priceToPay', timeout=cfg['price_wait_timeout'])
                except Exception:
                    pass
            time.sleep(random.uniform(0.5, 1.5))

            html = tab.html
            cands = parse_main_price(html)
            price, rule, ambiguous = select_main_price(cands, str(cfg['ambiguous_price_ratio']))
            cr.price_candidates = cands

            if price is None:
                if self._page_looks_normal(tab, row):
                    cr.status = PageStatus.SOLD_OUT      # 页面存在但无价格 → 售罄
                else:
                    cr.status = PageStatus.CRAWL_ERROR
                    cr.error = '页面未正常加载（空白/超时）'
                return cr
            if ambiguous:
                cr.status = PageStatus.PARSE_ERROR
                cr.error = f'多主价候选冲突: {[(c.rule, str(c.value)) for c in cands if c.value]}'
                cr.display_price = None
                return cr

            cr.display_price = price
            cr.price_rule = rule

            # 折扣证据（全部读取，类型决策交给 pricing.compute_result）
            save_pct, raw_save = parse_save(html)
            code_pct, raw_code = parse_code(html)
            coupon_pct, coupon_amt, raw_coupon = parse_coupon(html)
            cr.save_pct = save_pct
            cr.code_pct = code_pct
            cr.coupon_pct = coupon_pct
            cr.coupon_amount = coupon_amt
            cr.promotion_raw = collect_promotion_raw(html)
            cr.status = PageStatus.OK
            return cr
        except Exception as e:
            cr.status = PageStatus.CRAWL_ERROR
            cr.error = f'{type(e).__name__}: {str(e)[:80]}'
            return cr
        finally:
            cr.duration_ms = int((time.time() - t0) * 1000)
            if cr.timestamp == '':
                from datetime import datetime
                cr.timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def _page_looks_normal(self, tab, row: ReportRow) -> bool:
        """页面是否存在：title 非空、URL 含商品页特征、body 含 ASIN"""
        try:
            title = (tab.title or '').strip()
            if not title:
                return False
            if 'captcha' in (tab.url or '').lower():
                return False
            try:
                body = tab.ele('tag:body')
                body_txt = body.text if body else ''
            except Exception:
                body_txt = ''
            if body_txt and row.asin in body_txt:
                return True
            # Currently unavailable 等明确文案也算页面存在
            low = (body_txt or '').lower()
            if any(k in low for k in ('currently unavailable', 'temporarily out of stock')):
                return True
            return '/dp/' in (tab.url or '') or '/gp/product' in (tab.url or '')
        except Exception:
            return False

    # ---------- 带重试的入口（返回 (result, tab)，tab 可能被 rebuild 更换） ----------
    def fetch_with_retry(self, tab, row: ReportRow, cfg: dict) -> tuple[CrawlResult, object]:
        attempts = 0
        last: CrawlResult | None = None
        while True:
            attempts += 1
            last = self.fetch_once(tab, row, cfg)
            last.attempt_count = attempts
            st = last.status

            if st in (PageStatus.OK, PageStatus.PAGE_NOT_FOUND):
                break
            if st == PageStatus.SOLD_OUT:
                if attempts == 1:          # 刷新一次确认售罄
                    try:
                        tab.refresh()
                        tab.wait.doc_loaded(timeout=cfg['page_timeout'])
                    except Exception:
                        pass
                    continue
                break
            if st == PageStatus.CRAWL_ERROR:
                if 'captcha' in last.error.lower() and attempts <= 1:
                    tab = self.rebuild(tab)  # 新 tab 重试 1 次
                    continue
                if attempts <= cfg['retry']:
                    try:
                        tab.refresh()
                    except Exception:
                        tab = self.rebuild(tab)
                    continue
                break
            if st == PageStatus.PARSE_ERROR:
                if attempts == 1:
                    try:
                        tab.refresh()
                    except Exception:
                        pass
                    continue
                break
            break
        return last, tab

    def quit(self):
        try:
            self.page.quit()
        except Exception:
            pass
