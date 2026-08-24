# -*- coding: utf-8 -*-
"""parser.py — Amazon HTML 解析（正则 + 锚点，纯函数无 IO，可单测）

主价多候选、Save/Code/Coupon 分层读取；全部返回原始文本 + 解析值 + 命中规则。
"""
from __future__ import annotations

import re
from decimal import Decimal

from models import PriceCandidate
from pricing import parse_price_text, parse_pct_text
from amazon.selectors import (
    CODE_TEXT_PATTERNS, COUPON_AMOUNT_PATTERNS, COUPON_HTML_PATTERNS,
    MAIN_PRICE_CANDIDATES, SAVE_SELECTORS,
)


def _compact(html: str) -> str:
    """压缩标签间空白，让跨行正则可靠"""
    return re.sub(r'>\s+<', '><', html or '')


def _segment(html: str, patterns: list[str], length: int = 1200) -> str | None:
    """找到第一个锚点，返回其后 length 字符片段"""
    html = _compact(html)
    for p in patterns:
        m = re.search(p, html)
        if m:
            return html[m.start():m.start() + length]
    return None


def _price_from_segment(seg: str) -> tuple[Decimal | None, str]:
    """从片段提取价格：
    1) 元素内 a-offscreen（可为空），空则回退到同组的 whole/fraction（主价常见形态）；
    2) 任意非空 a-offscreen；
    3) 任意 whole/fraction 组合。"""
    m = re.search(r'a-offscreen">([^<]*?)</span>', seg)
    if m:
        raw = m.group(1).strip()
        if raw:
            v = parse_price_text(raw)
            if v is not None and v > 0:
                return v, raw
        # 空 offscreen：紧随其后的 whole/fraction 才是主价
        tail = seg[m.end():m.end() + 400]
        m2 = re.search(r'a-price-whole">\s*([\d,]+).{0,200}?a-price-fraction">\s*(\d+)', tail)
        if m2:
            txt = f'{m2.group(1)}.{m2.group(2)}'
            return Decimal(m2.group(1).replace(',', '') + '.' + m2.group(2)), txt
    m3 = re.search(r'a-offscreen">\s*([^<]+?)\s*<', seg)
    if m3:
        raw = m3.group(1).strip()
        v = parse_price_text(raw)
        if v is not None:
            return v, raw
    m4 = re.search(r'a-price-whole">\s*([\d,]+).{0,300}?a-price-fraction">\s*(\d+)', seg)
    if m4:
        txt = f'{m4.group(1)}.{m4.group(2)}'
        return Decimal(m4.group(1).replace(',', '') + '.' + m4.group(2)), txt
    return None, ''


def _container(html: str, open_pat: str, length: int) -> str | None:
    """按容器锚点提取片段（优先容器语义）"""
    m = re.search(open_pat, html)
    if m:
        return html[m.start():m.start() + length]
    return None


def parse_main_price(html: str) -> list[PriceCandidate]:
    """按容器语义收集主价候选（不去重，调用方做冲突判断）。"""
    html = _compact(html)
    cands: list[PriceCandidate] = []

    # 1. #corePrice_feature_div 主价格容器（最权威）
    seg = _container(html, r'id="corePrice_feature_div"', 5000)
    if seg:
        v, raw = _price_from_segment(seg)
        cands.append(PriceCandidate(rule='corePrice', raw_text=raw, value=v))

    # 2. Price to Pay 元素
    seg = _segment(html, [r'class="[^"]*priceToPay[^"]*"', r'apex-pricetopay-value'], 1500)
    if seg:
        v, raw = _price_from_segment(seg)
        cands.append(PriceCandidate(rule='priceToPay', raw_text=raw, value=v))

    # 3. Buy Box
    seg = _container(html, r'id="buybox"', 5000)
    if seg:
        v, raw = _price_from_segment(seg)
        cands.append(PriceCandidate(rule='buybox', raw_text=raw, value=v))

    # 4. 全局 whole/fraction 兜底（只在前面都没拿到时）
    if not any(c.value is not None for c in cands):
        m = re.search(r'a-price-whole">\s*([\d,]+).{0,300}?a-price-fraction">\s*(\d+)', html)
        if m:
            raw = f'{m.group(1)}.{m.group(2)}'
            cands.append(PriceCandidate(
                rule='whole_fraction',
                raw_text=raw,
                value=Decimal(m.group(1).replace(',', '') + '.' + m.group(2)),
            ))

    # 5. 全局第一个 a-offscreen 兜底
    if not any(c.value is not None for c in cands):
        m = re.search(r'a-offscreen">\s*([^<]+?)\s*<', html)
        if m:
            raw = m.group(1).strip()
            v = parse_price_text(raw)
            cands.append(PriceCandidate(rule='global_offscreen', raw_text=raw, value=v))

    return cands


def select_main_price(cands: list[PriceCandidate], ambiguous_ratio: str) -> tuple[Decimal | None, str, bool]:
    """选择主价：按候选顺序取第一个有效值；多个不同值差异超阈值 → ambiguous=True。
    返回 (主价, 命中规则, 是否冲突)"""
    vals: list[tuple[Decimal, str]] = []
    for c in cands:
        if c.value is not None and c.value > 0:
            vals.append((c.value, c.rule))
    if not vals:
        return None, '', False
    base, rule = vals[0]
    ratio = Decimal(ambiguous_ratio or '0.05')
    seen = {base}
    for v, _ in vals:
        if v in seen:
            continue
        seen.add(v)
        if abs(v - base) / base > ratio:
            return None, rule, True     # 冲突，交给调用方标 parse_error
    return base, rule, False


def _save_in_segment(seg: str) -> tuple[Decimal | None, str]:
    """在限定片段内找 Save% 折扣（只认主价格容器，避免推荐商品/动态区域误抓）"""
    for cls in SAVE_SELECTORS:
        m = re.search(rf'class="[^"]*{re.escape(cls.lstrip("."))}[^"]*"[^>]*>\s*([+-]?\s*[\d.]+\s*%)', seg)
        if m:
            raw = m.group(1).strip()
            pct = parse_pct_text(raw)
            if pct is not None:
                return pct, raw
    return None, ''


def parse_save(html: str) -> tuple[Decimal | None, str]:
    """价格折扣：只读主价格区域的 Save 百分比（corePrice 容器 → priceToPay 前后窗口）。
    严禁全局搜索——推荐商品区/JS 动态区域的 -X% 会误判；多变体页无 corePrice 容器时用 priceToPay 窗口兜底。"""
    html = _compact(html)
    # 1. 主价格容器 #corePrice_feature_div
    seg = _container(html, r'id="corePrice_feature_div"', 5000)
    if seg:
        pct, raw = _save_in_segment(seg)
        if pct is not None:
            return pct, raw
    # 2. priceToPay 锚点前后窗口（savings 通常在 priceToPay 上方）
    #    优先 class 里的 priceToPay（真主价区）；apex-pricetopay-value 可能在变体/其他区，仅兜底
    m = re.search(r'class="[^"]*priceToPay[^"]*"', html) or re.search(r'apex-pricetopay-value', html)
    if m:
        win = html[max(0, m.start() - 3000): m.start() + 1500]
        pct, raw = _save_in_segment(win)
        if pct is not None:
            return pct, raw
    return None, ''


def parse_code(html: str) -> tuple[Decimal | None, str]:
    """Code：返回 (code_pct, 原始文本)。只认促销文案，禁止反推。"""
    html = _compact(html)
    for pat in CODE_TEXT_PATTERNS:
        m = re.search(pat, html)
        if m:
            raw = m.group(0).strip()
            pct = parse_pct_text(raw)
            if pct is not None:
                return pct, raw
    return None, ''


def parse_coupon(html: str) -> tuple[Decimal | None, Decimal | None, str]:
    """Coupon：返回 (coupon_pct, coupon_amount, 原始文本)。final 由 DOM 流程补充。"""
    html = _compact(html)
    raw_parts: list[str] = []
    pct = None
    amount = None

    for pat in COUPON_HTML_PATTERNS:
        m = re.search(pat, html)
        if m:
            raw_parts.append(m.group(0).strip())
            v = Decimal(m.group(1))
            if '%' in m.group(0):
                pct = (v / 100) if pct is None else pct
            else:
                amount = v if amount is None else amount
            break

    # 金额：Saving $15.00 / Save $X with coupon（金额必须 > 0，过滤隐藏字段 value="0"）
    if pct is not None or amount is not None:
        for pat in COUPON_AMOUNT_PATTERNS:
            m = re.search(pat, html)
            if m:
                v = Decimal(m.group(1))
                if v > 0:
                    raw_parts.append(m.group(0).strip())
                    amount = v
                break

    raw = ' | '.join(dict.fromkeys(raw_parts))[:300]
    return pct, amount, raw


def collect_promotion_raw(html: str) -> str:
    """汇总 coupon/code/save 的原始证据文本（截断 500 字符）"""
    parts = []
    _, _, cr = parse_coupon(html)
    _, cr2 = parse_code(html)
    _, cr3 = parse_save(html)
    for t in (cr, cr2, cr3):
        if t:
            parts.append(t)
    return ' | '.join(dict.fromkeys(parts))[:500]
