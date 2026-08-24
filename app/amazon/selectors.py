# -*- coding: utf-8 -*-
"""selectors.py — 选择器与规则版本集中管理

页面结构变化时只需改这里，并递增 parser_rule_version。
规则版本同时用于缓存失效判断。
"""
from __future__ import annotations

RULE_VERSION = '2026-08-21-v1'

# ---- 主价格候选（按优先级） ----
MAIN_PRICE_CANDIDATES = [
    # 1. Price to Pay / 折后主价
    ('priceToPay', '.priceToPay .a-offscreen, .apex-pricetopay-value .a-offscreen'),
    # 2. Core Price 容器
    ('corePrice', '#corePrice_feature_div .a-price .a-offscreen'),
    # 3. Buy Box 当前价格
    ('buybox', '#buybox .a-price .a-offscreen'),
    # 4. Deal 价格容器
    ('dealPrice', '#dealPrice_feature_div .a-price .a-offscreen, .a-price.apexPriceToPay'),
]
# whole/fraction 组合（a-offscreen 为空时的兼容）
WHOLE_FRACTION = '.a-price-whole + .a-price-fraction, .a-price-whole'

# ---- 价格折扣（Save%） ----
SAVE_SELECTORS = [
    '.apex-savings-percentage',
    '.savingsPercentage',
    '.apex-savings-percent',
]

# ---- Code（Save X% at checkout）----
CODE_TEXT_PATTERNS = [
    r'Save\s+([\d.]+)\s*%\s*(?:at checkout|off)',
    r'([\d.]+)\s*%\s*off\s+at\s+checkout',
]

# ---- Coupon ----
COUPON_HTML_PATTERNS = [
    r'aria-label="\s*([\d.]+)\s*%\s*off\s+coupon\s+applied',          # claimed 磁贴
    r'Apply\s+([\d.]+)\s*%\s*coupon',                                  # 可勾选
    r'Save\s+\$?([\d.]+)\s+(?:with\s+)?coupon',                        # Save $X with coupon
    r'([\d.]+)\s*%\s*(?:coupon|off\s+coupon)',                         # 通用 X% coupon
]
COUPON_AMOUNT_PATTERNS = [
    r'Saving.{0,300}?\$?\s?([0-9]+(?:\.[0-9]+)?)',   # ct-coupon-tile Saving $15.00
    r'Save\s+\$([0-9]+(?:\.[0-9]+)?)',               # Save $X with coupon
    r'\$([0-9]+(?:\.[0-9]+)?)\s*(?:coupon|off)',     # $X coupon
]
COUPON_ELEM_HINTS = ('couponText', 'couponLabelText', 'couponLabelRegular',
                     'ct-coupon-tile', 'coupon applied')

# ---- 页面状态特征 ----
TITLE_404 = ('page not found', 'we could not find', '找不到页面')
TITLE_CAPTCHA = ('robot check', 'captcha')
TITLE_BLOCKED = ('sorry, we just need to make sure', 'access denied', 'sorry! something went wrong')
BODY_UNAVAILABLE = ('currently unavailable', 'currently unvailable', 'temporarily out of stock',
                    'see all buying options')
