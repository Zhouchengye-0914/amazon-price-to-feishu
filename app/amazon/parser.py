# -*- coding: utf-8 -*-
"""parser.py — Amazon DOM控件内解析（纯函数无 IO，可单测）

主价多候选、Save/Code/Coupon 分层读取；全部返回原始文本 + 解析值 + 命中规则。
"""
from __future__ import annotations

import re
from decimal import Decimal

from models import PriceCandidate
from amazon.price_evidence import main_segments, promotion_segments, Tree
from pricing import parse_price_text, parse_pct_text
from amazon.selectors import (
    CODE_TEXT_PATTERNS, COUPON_AMOUNT_PATTERNS, COUPON_ELEM_HINTS, COUPON_HTML_PATTERNS,
    SAVE_SELECTORS,
)


def _compact(html: str) -> str:
    """压缩标签间空白，让跨行正则可靠"""
    return html if isinstance(html, Tree) else re.sub(r'>\s+<', '><', html or '')


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


def parse_main_price(html: str) -> list[PriceCandidate]:
    """按容器语义收集主价候选（不去重，调用方做冲突判断）。"""
    html = _compact(html)
    cands: list[PriceCandidate] = []

    for rule, seg in main_segments(html):
        v, raw = _price_from_segment(seg)
        if not re.search(r'[$€£¥]|USD|CAD', raw, re.I):
            symbol = re.search(r'a-price-symbol[^>]*>([^<]+)', seg)
            if symbol:
                raw = symbol.group(1).strip() + raw
        cands.append(PriceCandidate(rule=rule, raw_text=raw, value=v))

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
    matches = [m.group(1).strip() for cls in SAVE_SELECTORS
               for m in re.finditer(rf'class="[^"]*{re.escape(cls.lstrip("."))}[^"]*"[^>]*>\s*([+-]?\s*[\d.]+\s*%)', seg)]
    pct = _unique([parse_pct_text(raw) for raw in matches], 'Save控件')
    return pct, ' | '.join(dict.fromkeys(matches))


def _parse_code_segment(html: str) -> tuple[Decimal | None, str]:
    """Code：返回 (code_pct, 原始文本)。只认促销文案，禁止反推。"""
    html = _compact(html)
    matches = [(parse_pct_text(m.group(0)), m.group(0).strip())
               for pat in CODE_TEXT_PATTERNS for m in re.finditer(pat, html, re.I)]
    pct = _unique([item[0] for item in matches], 'Code控件')
    return pct, ' | '.join(dict.fromkeys(item[1] for item in matches))


def _parse_coupon_segment(html: str) -> tuple[Decimal | None, Decimal | None, str]:
    """Coupon：返回 (coupon_pct, coupon_amount, 原始文本)。final 由 DOM 流程补充。"""
    html = _compact(html)
    _unique([Decimal(m.group(1)) for pat in COUPON_HTML_PATTERNS
             for m in re.finditer(pat, html, re.I) if '%' in m.group(0)], 'Coupon比例')
    raw_parts: list[str] = []
    pct = None
    amount = None

    evidence_span: tuple[int, int] | None = None
    for pat in COUPON_HTML_PATTERNS:
        for m in re.finditer(pat, html, re.IGNORECASE):
            context = html[max(0, m.start() - 700):m.end() + 700].lower()
            # aria-label="X% off coupon applied" 本身就是结构化证据；其他较宽松
            # 文案必须位于 Amazon Coupon 控件内。这样不会把评论中的 coupon
            # 经历、推荐商品优惠或脚本模板误认为当前 ASIN 的优惠。
            structured = 'aria-label=' in m.group(0).lower()
            anchored = any(h.lower() in context for h in COUPON_ELEM_HINTS) or any(
                h in context for h in ('couponsinbuybox', 'promotioncc', 'newcouponbadge')
            )
            if not (structured or anchored):
                continue
            raw_parts.append(m.group(0).strip())
            v = Decimal(m.group(1))
            if '%' in m.group(0):
                pct = (v / 100) if pct is None else pct
            else:
                amount = v if amount is None else amount
            evidence_span = (m.start(), m.end())
            break
        if evidence_span is not None:
            break

    # 金额：Saving $15.00 / Save $X with coupon（金额必须 > 0，过滤隐藏字段 value="0"）
    if evidence_span is not None:
        # Saving 金额必须来自同一个 Coupon 控件，禁止再扫描整页。评论区和
        # “Frequently bought together” 中也经常出现 Saving/$X 文案。
        start, end = evidence_span
        coupon_scope = html  # already bounded to one eligible DOM control
        patterns = [r'Saving.{0,300}?\$\s*([0-9]+(?:\.[0-9]+)?)',
                    *COUPON_AMOUNT_PATTERNS[1:]]
        _unique([Decimal(m.group(1)) for pat in patterns
                 for m in re.finditer(pat, coupon_scope, re.I) if Decimal(m.group(1)) > 0], 'Coupon金额')
        for pat in patterns:
            m = re.search(pat, coupon_scope, re.IGNORECASE)
            if m:
                v = Decimal(m.group(1))
                if v > 0:
                    raw_parts.append(m.group(0).strip())
                    amount = v
                break

    raw = ' | '.join(dict.fromkeys(raw_parts))[:300]
    return pct, amount, raw


class PromotionEvidenceError(ValueError):
    pass

def _unique(items, name):
    present = {item for item in items if item is not None}
    if len(present) > 1:
        raise PromotionEvidenceError(f'{name}存在互相冲突的促销证据: {sorted(present)}')
    return next(iter(present), None)

def parse_save(html):
    values = [_save_in_segment(seg) for _, seg in main_segments(html)]
    pct = _unique([v[0] for v in values], 'Save')
    return pct, ' | '.join(dict.fromkeys(v[1] for v in values if v[1]))

def parse_code(html):
    values = [_parse_code_segment(seg) for seg in promotion_segments(html, 'code')]
    pct = _unique([v[0] for v in values], 'Code')
    return pct, ' | '.join(dict.fromkeys(v[1] for v in values if v[1]))

def parse_coupon(html):
    values = [_parse_coupon_segment(seg) for seg in promotion_segments(html, 'coupon')]
    # Do not merge a percentage from one offer with an amount from another.
    offers = {(pct, amount) for pct, amount, _ in values if pct is not None or amount is not None}
    if len(offers) > 1:
        raise PromotionEvidenceError('Coupon控件存在不同优惠，禁止跨控件拼接')
    pct, amount = next(iter(offers), (None, None))
    return pct, amount, ' | '.join(dict.fromkeys(v[2] for v in values if v[2]))[:300]

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
