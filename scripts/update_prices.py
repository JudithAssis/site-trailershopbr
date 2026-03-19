#!/usr/bin/env python3
"""
Automated Price Updater for Trailer Shop BR
Uses ML public API for Mercado Livre products and web scraping for Amazon.
Runs via GitHub Actions daily to keep prices synchronized.
"""

import json
import re
import sys
import os
import time
import random
import urllib.request
import urllib.error

# ─── Configuration ───────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PRODUCTS_FILE = os.path.join(SCRIPT_DIR, '..', 'products.json')
HTML_FILE = os.path.join(SCRIPT_DIR, '..', 'index.html')
USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/122.0.0.0 Safari/537.36'
)
MAX_RETRIES = 2
REQUEST_DELAY = (2, 4)  # seconds between requests


# ─── Price Helpers ───────────────────────────────────────────────
def parse_price(price_str):
    """Convert 'R$ 149,00' to float 149.0"""
    if not price_str:
        return None
    cleaned = price_str.replace('R$', '').replace('\xa0', '').strip()
    cleaned = cleaned.replace('.', '').replace(',', '.')
    try:
        return float(cleaned)
    except ValueError:
        return None


def format_price(value):
    """Convert float 149.0 to 'R$ 149,00'"""
    if value is None:
        return None
    formatted = f"{value:,.2f}"
    parts = formatted.split('.')
    integer_part = parts[0].replace(',', '.')
    decimal_part = parts[1]
    return f"R$ {integer_part},{decimal_part}"


# ─── HTTP Helper ─────────────────────────────────────────────────
def fetch_url(url, headers=None, timeout=15):
    """Fetch a URL safely with retries."""
    if headers is None:
        headers = {
            'User-Agent': USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.7',
            'Accept-Encoding': 'identity',
        }

    for attempt in range(MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode('utf-8', errors='replace'), resp.geturl()
        except Exception as e:
            if attempt < MAX_RETRIES:
                time.sleep(random.uniform(1, 3))
            else:
                print(f"  ✗ Failed: {e}")
                return None, None


# ─── Mercado Livre: Product Page Scraping ────────────────────────
def get_ml_price(product):
    """Get price from Mercado Livre product page using MLB item ID."""
    mlb_id = product.get('mlb_id')
    if not mlb_id:
        print(f"  ⚠ No MLB ID for this product, skipping")
        return None, None

    # Format: MLB4129234911 -> MLB-4129234911
    formatted_id = mlb_id[:3] + '-' + mlb_id[3:]
    page_url = f"https://produto.mercadolivre.com.br/{formatted_id}"

    print(f"  → ML Page: {page_url}")
    html, _ = fetch_url(page_url)
    if not html:
        return None, None

    current_price = None
    original_price = None

    # Strategy 1: Find "price" in embedded JSON data
    prices = re.findall(r'"price"\s*:\s*(\d+\.?\d*)', html)
    if prices:
        try:
            current_price = float(prices[0])
        except ValueError:
            pass

    # Strategy 2: meta itemprop
    if not current_price:
        m = re.search(r'itemprop="price"[^>]*content="([\d.]+)"', html)
        if m:
            try:
                current_price = float(m.group(1))
            except ValueError:
                pass

    # Try to find original price (before discount)
    orig_matches = re.findall(r'"original_price"\s*:\s*(\d+\.?\d*)', html)
    if orig_matches:
        try:
            original_price = float(orig_matches[0])
            if current_price and abs(original_price - current_price) < 0.01:
                original_price = None  # No actual discount
        except ValueError:
            pass

    # Fallback: look for crossed-out price patterns
    if not original_price:
        m = re.search(r'"list_price"\s*:\s*(\d+\.?\d*)', html)
        if m:
            try:
                original_price = float(m.group(1))
                if current_price and abs(original_price - current_price) < 0.01:
                    original_price = None
            except ValueError:
                pass

    return current_price, original_price


# ─── Amazon: Web Scraping ────────────────────────────────────────
def get_amazon_price(product):
    """Get price from Amazon product page via scraping."""
    link = product['link']
    print(f"  → Following: {link}")

    html, final_url = fetch_url(link)
    if not html:
        return None, None

    current_price = None
    original_price = None

    # Strategy 1: price in corePrice feature
    core_block = re.search(r'id="corePrice(?:Display_desktop)?_feature_div"(.*?)</div>', html, re.DOTALL)
    search_area = core_block.group(1) if core_block else html

    m = re.search(r'class="a-price-whole"[^>]*>([\d.]+)', search_area)
    m2 = re.search(r'class="a-price-fraction"[^>]*>(\d+)', search_area)
    if m and m2:
        try:
            current_price = float(m.group(1).replace('.', '') + '.' + m2.group(1))
        except ValueError:
            pass

    # Strategy 2: priceblock IDs
    if not current_price:
        m = re.search(r'id="priceblock_(?:ourprice|dealprice|saleprice)"[^>]*>\s*R\$\s*([\d.,]+)', search_area)
        if m:
            try:
                current_price = float(m.group(1).replace('.', '').replace(',', '.'))
            except ValueError:
                pass

    # Strategy 3: JSON-LD / structured data
    if not current_price:
        m = re.search(r'"price"\s*:\s*"?([\d.]+)"?', html)
        if m:
            try:
                current_price = float(m.group(1))
            except ValueError:
                pass

    # Strategy 4: meta itemprop
    if not current_price:
        m = re.search(r'<meta\s+itemprop="price"\s+content="([\d.]+)"', html)
        if m:
            try:
                current_price = float(m.group(1))
            except ValueError:
                pass

    # Original/list price (strikethrough)
    m = re.search(r'class="[^"]*a-text-strike[^"]*"[^>]*>(?:<span[^>]*>)?\s*R\$\s*([\d.,]+)', html, re.DOTALL)
    if m:
        try:
            original_price = float(m.group(1).replace('.', '').replace(',', '.'))
        except ValueError:
            pass

    return current_price, original_price


# ─── HTML Updater ────────────────────────────────────────────────
def update_html_price(html, product, new_price, new_orig):
    """Update the price in the HTML for a specific product card by rewriting the price block."""
    old_price = product['current_price']
    old_orig = product.get('original_price')
    new_price_str = format_price(new_price)
    
    if not new_price_str:
        return html, False

    link_escaped = re.escape(product['link'])
    pattern = re.compile(rf'(<a\s+href="{link_escaped}"[^>]*>.*?</a>)', re.DOTALL)
    match = pattern.search(html)
    if not match:
        print(f"  ✗ Product block not found in HTML")
        return html, False

    block = match.group(1)
    
    # Extract the block containing the prices and Oferta badge
    div_match = re.search(r'(<div class="mt-auto pt-2">)(.*?)(</div>)', block, re.DOTALL)
    if not div_match:
        print(f"  ✗ Price container not found in HTML block")
        return html, False
        
    old_inner_html = div_match.group(2)

    # Check if there is a real offer (original price is higher than current price)
    if new_orig and new_orig > new_price + 0.01:
        new_orig_str = format_price(new_orig)
        inner_html = f'''
                                            <span class="inline-flex items-center bg-red-500 text-white text-[9px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wide">🏷️ Oferta</span>
                                            <p class="text-[11px] text-gray-400 mt-1 line-through">{new_orig_str}</p>
                                            <p class="text-sm font-bold text-green-600">{new_price_str}</p>
                                        '''
    else:
        # No real offer, just the price
        # Using mt-1 on the price to keep the alignment
        inner_html = f'''
                                            <p class="text-sm font-bold text-green-600 mt-1">{new_price_str}</p>
                                        '''

    new_div = f"{div_match.group(1)}{inner_html}{div_match.group(3)}"
    new_block = block.replace(div_match.group(0), new_div)

    changed = (block != new_block)
    if changed:
        html = html.replace(block, new_block)

    return html, changed


# ─── Main ────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("🔄 Trailer Shop BR — Price Updater")
    print("=" * 60)

    products_path = os.path.abspath(PRODUCTS_FILE)
    html_path = os.path.abspath(HTML_FILE)

    with open(products_path, 'r', encoding='utf-8') as f:
        products = json.load(f)
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()

    ml_count = sum(1 for p in products if p['source'] == 'mercadolivre')
    amz_count = sum(1 for p in products if p['source'] == 'amazon')
    print(f"\n📊 {len(products)} products ({amz_count} Amazon, {ml_count} ML)\n")

    updates = []
    errors = []

    for i, prod in enumerate(products):
        print(f"[{i+1}/{len(products)}] {prod['name'][:50]}")

        if i > 0:
            time.sleep(random.uniform(*REQUEST_DELAY))

        try:
            if prod['source'] == 'mercadolivre':
                new_price, new_orig = get_ml_price(prod)
            elif prod['source'] == 'amazon':
                new_price, new_orig = get_amazon_price(prod)
            else:
                continue

            if new_price is None:
                print(f"  ⚠ Could not get price")
                errors.append(prod['name'])
                continue

            old_price = parse_price(prod['current_price'])
            new_fmt = format_price(new_price)

            is_price_changed = False
            if old_price is None or abs(old_price - new_price) >= 0.01:
                is_price_changed = True

            # Always update HTML to ensure the structure (Oferta tags) is correct
            html, html_changed = update_html_price(html, prod, new_price, new_orig)
            
            if is_price_changed or html_changed:
                if is_price_changed:
                    print(f"  💰 Changed: {format_price(old_price) if old_price else 'N/A'} → {new_fmt}")
                else:
                    print(f"  ✓ Layout fixed: {prod['current_price']}")
                    
                prod['current_price'] = new_fmt
                if new_orig:
                    prod['original_price'] = format_price(new_orig)
                elif 'original_price' in prod: # removing original price from JSON if it no longer has one
                    del prod['original_price']
                    
                updates.append({
                    'name': prod['name'],
                    'old': format_price(old_price) if old_price else 'N/A',
                    'new': new_fmt,
                })
            else:
                print(f"  ✓ Unchanged: {prod['current_price']}")

        except Exception as e:
            print(f"  ✗ Error: {e}")
            errors.append(prod['name'])

    # ─── Summary ─────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("📋 SUMMARY")
    print("=" * 60)

    if updates:
        print(f"\n✅ {len(updates)} price(s) updated:")
        for u in updates:
            print(f"   • {u['name'][:45]}: {u['old']} → {u['new']}")

        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html)
        with open(products_path, 'w', encoding='utf-8') as f:
            json.dump(products, f, indent=2, ensure_ascii=False)

        print("\n💾 Files saved!")
    else:
        print("\n✅ All prices up to date.")

    if errors:
        print(f"\n⚠ {len(errors)} product(s) failed:")
        for e in errors:
            print(f"   • {e[:50]}")

    return 1 if updates else 0


if __name__ == '__main__':
    sys.exit(main())
