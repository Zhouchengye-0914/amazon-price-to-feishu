"""DOM-bounded main-price evidence; recommendation/hidden subtrees are excluded."""
import re
from html import escape
from html.parser import HTMLParser

class Node:
    def __init__(self, tag='', attrs=(), parent=None):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs), parent, []

    def excluded(self):
        attrs = self.attrs
        marker = ' '.join(str(attrs.get(k) or '') for k in ('id', 'class', 'data-feature-name', 'data-hook')).lower()
        style = re.sub(r'\s+', '', attrs.get('style') or '').lower()
        return (self.tag in ('script', 'style', 'template', 'noscript')
                or str(attrs.get('data-csa-c-buying-option-type') or '').upper() in ('USED', 'REFURBISHED')
                or attrs.get('data-csa-c-slot-id') == 'usedAccordionRow'
                or 'aok-hidden' in (attrs.get('class') or '').split()
                or 'hidden' in attrs or 'display:none' in style or 'visibility:hidden' in style
                or attrs.get('data-price-audit-hidden') == 'true'
                or bool(re.search(r'recommend|similar|sponsored|carousel|sims-|desktop-dp-sims|a-text-price|review|customer.*question|ask-btf|sns-|subscribe', marker)))

    def html(self):
        if self.excluded():
            return ''
        attrs = ''.join(f' {k}="{escape(v or "", quote=True)}"' for k, v in self.attrs.items())
        return f'<{self.tag}{attrs}>' + ''.join(
            c.html() if isinstance(c, Node) else escape(c, quote=False) for c in self.children) + f'</{self.tag}>'

class Tree(HTMLParser):
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = self.current = Node()
        self.nodes = []
        self.feed(html or '')

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.current)
        self.current.children.append(node)
        self.nodes.append(node)
        if tag not in self.VOID:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        node = self.current
        while node.parent is not None:
            if node.tag == tag:
                self.current = node.parent
                return
            node = node.parent

    def handle_data(self, data):
        self.current.children.append(data)

def as_tree(html):
    return html if isinstance(html, Tree) else Tree(html)

def eligible(node):
    while node is not None:
        if node.excluded():
            return False
        node = node.parent
    return True

def main_segments(html):
    segments = []
    for node in as_tree(html).nodes:
        parent = node
        excluded = False
        while parent is not None:
            if parent.excluded():
                excluded = True
                break
            parent = parent.parent
        if excluded:
            continue
        attrs = node.attrs
        ident, classes = attrs.get('id'), (attrs.get('class') or '').split()
        if ident in ('corePrice_feature_div', 'corePriceDisplay_desktop_feature_div'):
            rule = 'corePrice'
        elif 'priceToPay' in classes or 'apex-pricetopay-value' in classes:
            rule = 'priceToPay'
        elif ident == 'buybox':
            rule = 'buybox'
        else:
            continue
        segments.append((rule, node.html()))
    return sorted(segments, key=lambda item: ('corePrice', 'priceToPay', 'buybox').index(item[0]))

def observed_currency(raw, expected):
    """Bare $ is meaningful only with the caller's verified domain and location."""
    text = raw.upper()
    codes = set()
    if re.search(r'USD|US\s*\$', text): codes.add('USD')
    if re.search(r'CAD|(?:CA|CDN|C)\s*\$', text): codes.add('CAD')
    if re.search(r'EUR|GBP|JPY|AUD|€|£|¥|(?<![A-Z])A\s*\$', text): codes.add('unsupported')
    if codes:
        return next(iter(codes)) if len(codes) == 1 else 'conflict'
    if re.search(r'[A-Z]{1,3}\s*\$', text):
        return 'unsupported'
    return expected if '$' in text else ''

def explicitly_unavailable(html):
    for node in as_tree(html).nodes:
        if node.attrs.get('id') not in ('availability', 'availabilityInsideBuyBox_feature_div', 'outOfStock'):
            continue
        parent = node
        while parent is not None and not parent.excluded():
            parent = parent.parent
        if parent is None and re.search(r'currently unavailable|temporarily out of stock',
                                        re.sub(r'<[^>]+>', ' ', node.html()), re.I):
            return True
    return False

def promotion_segments(html, kind):
    """Outermost eligible promotion controls, never text windows across siblings."""
    selected = []
    for node in as_tree(html).nodes:
        if not eligible(node):
            continue
        attrs = node.attrs
        marker = ' '.join(str(attrs.get(k) or '') for k in ('id', 'class')).lower()
        if kind == 'coupon':
            matched = any(s in marker for s in ('ct-coupon-tile', 'coupontext', 'couponlabel', 'couponsinbuybox', 'promotioncc', 'newcouponbadge'))
        else:
            matched = any(s in marker for s in ('a-alert-content', 'a-alert-container', 'promopriceblockmessage', 'cxcwemphasislink')) or '/promotion/psp/' in (attrs.get('href') or '')
        if not matched:
            continue
        parent = node.parent
        while parent is not None and parent not in selected:
            parent = parent.parent
        if parent is None:
            selected.append(node)
    return [node.html() for node in selected]
