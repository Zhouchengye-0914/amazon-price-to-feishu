# -*- coding: utf-8 -*-
"""test_parser.py — HTML 解析单测（基于真实页面结构片段）"""
import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amazon.parser import (
    collect_promotion_raw, parse_code, parse_coupon, parse_main_price,
    parse_save, select_main_price,
)

# ---- 真实结构片段（摘自 amz前端价格显示html文件/页面类型情况说明.txt）----

HTML_PRICE_DISCOUNT = '''
<div id="corePrice_feature_div">
 <span class="apex-savings-container ">
  <span aria-hidden="true" class="a-size-large a-color-price savingPriceOverride aok-align-center
        reinventPriceSavingsPercentageMargin savingsPercentage apex-savings-percentage">-25%</span>
 </span>
 <span class="a-price aok-align-center reinventPricePriceToPayMargin priceToPay apex-pricetopay-value"
       data-a-size="xl" data-a-color="base">
  <span class="a-offscreen"> </span>
  <span aria-hidden="true">
   <span class="a-price-symbol">$</span>
   <span class="a-price-whole">29<span class="a-price-decimal">.</span></span>
   <span class="a-price-fraction">98</span>
  </span>
 </span>
</div>
'''

HTML_CODE = '''
<div class="a-box-inner a-alert-container">
 <i class="a-icon a-icon-alert" aria-hidden="true"></i>
 <div class="a-alert-content">Save 30%   at checkout</div>
</div>
'''

HTML_COUPON = '''
<div class="ct-coupon-tile claimed" id="doneTilepctch9464649203459693" role="status"
     aria-live="polite" aria-label=" 25% off coupon applied   ">
 <div class="ct-coupon-tile-content">
  <svg ...></svg>
  <span class="ct-coupon-tile-text-content">
   <span> <span>Saving</span> </span>
   <span class="ct-coupon-tile-price-content a-text-bold">
    <span class="a-price" data-a-size="medium_plus" data-a-color="base">
     <span class="a-offscreen">$15.00</span>
     <span aria-hidden="true">
      <span class="a-price-symbol">$</span>
      <span class="a-price-whole">15<span class="a-price-decimal">.</span></span>
      <span class="a-price-fraction">00</span>
     </span>
    </span>
   </span>
  </span>
 </div>
</div>
<div id="corePrice_feature_div"><span class="a-price"><span class="a-offscreen">$59.99</span></span></div>
'''

HTML_PLAIN = '''
<html><head><title>GENIMO Outdoor Rug</title></head>
<body>
<div id="corePrice_feature_div">
 <span class="a-price"><span class="a-offscreen">$49.99</span></span>
</div>
</body></html>
'''


class TestMainPrice(unittest.TestCase):
    def test_price_to_pay_whole_fraction(self):
        cands = parse_main_price(HTML_PRICE_DISCOUNT)
        price, rule, amb = select_main_price(cands, '0.05')
        self.assertFalse(amb)
        self.assertEqual(price, Decimal('29.98'))
        # priceToPay 容器内 a-offscreen 为空时用 whole/fraction 组合
        self.assertTrue(any(c.value == Decimal('29.98') for c in cands))

    def test_core_price_offscreen(self):
        cands = parse_main_price(HTML_PLAIN)
        price, rule, amb = select_main_price(cands, '0.05')
        self.assertFalse(amb)
        self.assertEqual(price, Decimal('49.99'))

    def test_conflict(self):
        # corePrice 容器（$45.00）在前，priceToPay 区（$29.98）在后 → 两候选冲突
        html = ('<div id="corePrice_feature_div"><span class="a-price">'
                '<span class="a-offscreen">$45.00</span></span></div>') + HTML_PRICE_DISCOUNT
        cands = parse_main_price(html)
        price, rule, amb = select_main_price(cands, '0.05')
        self.assertTrue(amb)
        self.assertIsNone(price)

    def test_no_price(self):
        price, rule, amb = select_main_price(parse_main_price('<html><body>no price</body></html>'), '0.05')
        self.assertIsNone(price)
        self.assertFalse(amb)


class TestSave(unittest.TestCase):
    def test_save_pct(self):
        pct, raw = parse_save(HTML_PRICE_DISCOUNT)
        self.assertEqual(pct, Decimal('0.25'))
        self.assertIn('-25%', raw)

    def test_no_save(self):
        self.assertEqual(parse_save(HTML_PLAIN), (None, ''))


class TestCode(unittest.TestCase):
    def test_code(self):
        pct, raw = parse_code(HTML_CODE)
        self.assertEqual(pct, Decimal('0.30'))
        self.assertIn('Save 30%', raw)

    def test_no_code(self):
        self.assertEqual(parse_code(HTML_PLAIN), (None, ''))

    def test_code_text_in_review_is_not_product_promotion(self):
        html = HTML_PLAIN + '<div data-hook="reviewRichContentContainer">I got Save 30% at checkout.</div>'
        self.assertEqual(parse_code(html), (None, ''))


class TestCoupon(unittest.TestCase):
    def test_coupon_pct_and_saving(self):
        pct, amount, raw = parse_coupon(HTML_COUPON)
        self.assertEqual(pct, Decimal('0.25'))
        self.assertEqual(amount, Decimal('15.00'))
        self.assertIn('25% off coupon applied', raw)

    def test_no_coupon(self):
        self.assertEqual(parse_coupon(HTML_PLAIN), (None, None, ''))

    def test_coupon_text_in_review_is_not_product_coupon(self):
        # 真实全量样本 B0CLNRF9P3 曾因评论中的这句话被误判为 Coupon。
        html = (HTML_CODE + HTML_PLAIN +
                '<div data-hook="reviewRichContentContainer">I ordered it with a 30% off coupon.</div>')
        self.assertEqual(parse_coupon(html), (None, None, ''))
        self.assertEqual(parse_code(html)[0], Decimal('0.30'))

    def test_unrelated_saving_amount_is_not_attached_to_coupon(self):
        html = ('''<span id="couponText123" class="couponLabelText">Apply 25% coupon</span>'''
                + ('x' * 2500) + '<div>Saving $80.00 on another item</div>')
        pct, amount, _ = parse_coupon(html)
        self.assertEqual(pct, Decimal('0.25'))
        self.assertIsNone(amount)


class TestPromotionRaw(unittest.TestCase):
    def test_collect(self):
        raw = collect_promotion_raw(HTML_COUPON)
        self.assertIn('25% off coupon applied', raw)
        self.assertIn('Saving', raw)


if __name__ == '__main__':
    unittest.main()
