#!/usr/bin/env python3
"""
Bulk product addition script for Trailer Shop BR.
Resolves meli.la links, downloads images, and prepares product data.
"""

import json
import os
import re
import ssl
import sys
import time
import urllib.request
import urllib.error
import urllib.parse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.path.join(SCRIPT_DIR, '..')
IMG_DIR = os.path.join(SITE_DIR, 'assets', 'img')
PRODUCTS_FILE = os.path.join(SITE_DIR, 'products.json')
HTML_FILE = os.path.join(SITE_DIR, 'index.html')

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36'

# ─── Product definitions ───
PRODUCTS = [
    {
        "name": "Kit 2 Prateleira Adesiva Suporte Banheiro Chuveiro Sem Furo",
        "link": "https://meli.la/13XzRyg",
        "carousel": "diversos",   # Dia a Dia & Beleza
    },
    {
        "name": "Câmera Veicular 1080p Hd 4 Canais Com Visão Noturna 360°",
        "link": "https://meli.la/2CJCqjE",
        "carousel": "outdoor",    # Vida Outdoor & Trailer
    },
    {
        "name": "Kit 2 Prateleiras Cozinha Utensílios Temperos Preto 30cm",
        "link": "https://meli.la/1tcWbeM",
        "carousel": "cozinha",    # Cozinha Inteligente
    },
    {
        "name": "Estojo Armazenamento Portátil Para Dji Neo Drone Confortável",
        "link": "https://meli.la/1EcBGUY",
        "carousel": "outdoor",    # Vida Outdoor & Trailer
    },
    {
        "name": "Buba Hora do Soninho Girafinha Pelúcia Macia Cor Marrom",
        "link": "https://meli.la/2etnGBR",
        "carousel": "diversos",   # Dia a Dia & Beleza
    },
    {
        "name": "Bateria Solar 12v 460ah Lifepo4 5,88kwh Bms Bluetooth Ip65",
        "link": "https://meli.la/2dfF9Kk",
        "carousel": "outdoor",    # Vida Outdoor & Trailer
    },
    {
        "name": "Inversor Híbrido Baixa Frequência 12v 3kva Motorhome",
        "link": "https://meli.la/1KVUdd7",
        "carousel": "outdoor",    # Vida Outdoor & Trailer
    },
    {
        "name": "1x Prostazen 60 Caps Envio Hoje - Única Loja Oficial",
        "link": "https://meli.la/2yvEYCe",
        "carousel": "diversos",   # Dia a Dia & Beleza
    },
    {
        "name": "Gimbal Estabilizador Com 3 Eixos Celular Tokqi M01 Portátil",
        "link": "https://meli.la/1crkRv6",
        "carousel": "escritorio", # Trabalho & Home Office
    },
    {
        "name": "Kit De Iluminação Led Foto Vídeo + Controle Tripé 2m Bivolt",
        "link": "https://meli.la/2Juoc5x",
        "carousel": "escritorio", # Trabalho & Home Office
    },
    {
        "name": "Guincho Elétrico 3000LB Cabo Aço 6m 1361Kg Importway",
        "link": "https://meli.la/1QLuboW",
        "carousel": "outdoor",    # Vida Outdoor & Trailer
    },
    {
        "name": "Painel 1 Placa Fotovoltaica 550w Da Solar Energia Solar",
        "link": "https://meli.la/2MDFesv",
        "carousel": "outdoor",    # Vida Outdoor & Trailer
    },
    {
        "name": "Drone Dji Neo 2 Standard Dji069",
        "link": "https://meli.la/2hSe54b",
        "carousel": "outdoor",    # Vida Outdoor & Trailer
    },
    {
        "name": "Case Capa Microfone Hollyland Lark M2 Completa",
        "link": "https://meli.la/27VHWkv",
        "carousel": "escritorio", # Trabalho & Home Office
    },
    {
        "name": "Microfone Lapela Hollyland Lark M2 Duplo Usb C E Lightning",
        "link": "https://meli.la/2uWzaLs",
        "carousel": "escritorio", # Trabalho & Home Office
    },
]


def slugify(name):
    """Create a filename-safe slug from product name."""
    s = name.lower()
    s = re.sub(r'[àáâãä]', 'a', s)
    s = re.sub(r'[èéêë]', 'e', s)
    s = re.sub(r'[ìíîï]', 'i', s)
    s = re.sub(r'[òóôõö]', 'o', s)
    s = re.sub(r'[ùúûü]', 'u', s)
    s = re.sub(r'[ç]', 'c', s)
    s = re.sub(r'[^a-z0-9]+', '-', s)
    s = s.strip('-')
    return s[:80]


def fetch_url(url):
    """Fetch URL content with SSL bypass."""
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': 'text/html,application/xhtml+xml,*/*',
        'Accept-Language': 'pt-BR,pt;q=0.9',
    })
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=20) as r:
            return r.read().decode('utf-8', errors='ignore'), r.geturl()
    except Exception as e:
        print(f"  ✗ Fetch error: {e}")
        return None, None


def resolve_ml_storefront(url):
    """Resolve meli.la link → ML storefront page → extract product image & price."""
    print(f"  → Resolving: {url}")
    html, final_url = fetch_url(url)
    if not html:
        return None, None, None

    # Extract image
    imgs = re.findall(r'https://http2\.mlstatic\.com/D_NQ_NP[A-Za-z0-9_/-]*\.webp', html)
    img_url = imgs[0] if imgs else None

    # Extract price from storefront
    price = None
    # Try storefront JSON price
    price_matches = re.findall(r'"price"\s*:\s*(\d+\.?\d*)', html)
    if price_matches:
        try:
            price = float(price_matches[0])
        except:
            pass

    # Fallback: look for R$ pattern
    if not price:
        m = re.search(r'R\$\s*([\d.]+,\d{2})', html)
        if m:
            try:
                price = float(m.group(1).replace('.', '').replace(',', '.'))
            except:
                pass

    return img_url, price, final_url


def download_image(url, filename):
    """Download image to assets/img/."""
    filepath = os.path.join(IMG_DIR, filename)
    if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
        print(f"  ✓ Image exists: {filename}")
        return True

    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
            data = r.read()
            with open(filepath, 'wb') as f:
                f.write(data)
        print(f"  ✓ Downloaded: {filename} ({len(data)} bytes)")
        return True
    except Exception as e:
        print(f"  ✗ Download failed: {e}")
        return False


def format_price(value):
    """Convert float to R$ string."""
    if value is None:
        return "Consulte"
    formatted = f"{value:,.2f}"
    parts = formatted.split('.')
    integer_part = parts[0].replace(',', '.')
    decimal_part = parts[1]
    return f"R$ {integer_part},{decimal_part}"


def generate_card_html(product):
    """Generate HTML card for a product."""
    name = product['name']
    link = product['link']
    image = product['image']
    price = product.get('price_str', 'Consulte')

    return f'''                            <div class="carousel-item flex-shrink-0 w-44 md:w-52 p-3">
                                <a href="{link}" target="_blank" class="block group border border-gray-100 rounded-xl p-3 bg-white hover:shadow-lg transition-all h-full flex flex-col justify-between">
                                    <div class="aspect-square bg-gray-100 rounded-lg mb-3 overflow-hidden">
                                        <img width="400" height="400" loading="lazy" src="{image}" alt="{name}" class="w-full h-full object-cover">
                                    </div>
                                    <div class="flex flex-col flex-grow">
                                        <p class="text-xs font-semibold text-secondary group-hover:text-primary transition-colors line-clamp-2 leading-snug">{name}</p>
                                        <div class="mt-auto pt-2">
                                            <p class="text-sm font-bold text-green-600 mt-1">{price}</p>
                                        </div>
                                    </div>
                                </a>
                            </div>'''


def main():
    print("=" * 60)
    print("🚀 Bulk Product Adder — Trailer Shop BR")
    print("=" * 60)

    results = []

    for i, prod in enumerate(PRODUCTS):
        print(f"\n[{i+1}/{len(PRODUCTS)}] {prod['name']}")

        if i > 0:
            time.sleep(1.5)

        img_url, price, final_url = resolve_ml_storefront(prod['link'])

        slug = slugify(prod['name'])
        img_filename = f"{slug}.jpg"
        img_path = f"assets/img/{img_filename}"

        if img_url:
            download_image(img_url, img_filename)
        else:
            print(f"  ⚠ No image found, will use placeholder")

        price_str = format_price(price)
        print(f"  💰 Price: {price_str}")

        results.append({
            "name": prod['name'],
            "link": prod['link'],
            "source": "mercadolivre",
            "image": img_path,
            "current_price": price_str,
            "carousel": prod['carousel'],
            "price_str": price_str,
        })

    # ── Update products.json ──
    print("\n📦 Updating products.json...")
    with open(PRODUCTS_FILE, 'r', encoding='utf-8') as f:
        existing = json.load(f)

    existing_links = {p['link'] for p in existing}
    added = 0
    for r in results:
        if r['link'] not in existing_links:
            entry = {
                "name": r['name'],
                "link": r['link'],
                "source": r['source'],
                "image": r['image'],
                "current_price": r['current_price'],
            }
            existing.append(entry)
            added += 1
    
    with open(PRODUCTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)
    print(f"  ✓ Added {added} new entries to products.json")

    # ── Update index.html ──
    print("\n📝 Updating index.html...")
    with open(HTML_FILE, 'r', encoding='utf-8') as f:
        html = f.read()

    carousel_map = {
        'cozinha': 'carousel-cozinha',
        'escritorio': 'carousel-escritorio',
        'outdoor': 'carousel-outdoor',
        'diversos': 'carousel-diversos',
    }

    cards_by_carousel = {}
    for r in results:
        c = r['carousel']
        if c not in cards_by_carousel:
            cards_by_carousel[c] = []
        cards_by_carousel[c].append(generate_card_html(r))

    for carousel_key, cards in cards_by_carousel.items():
        carousel_id = carousel_map[carousel_key]
        # Find the carousel div and inject cards after the opening tag
        pattern = re.compile(
            rf'(<div id="{carousel_id}"[^>]*>\s*\n\s*style="[^"]*"[^>]*>)',
            re.DOTALL
        )
        match = pattern.search(html)
        if not match:
            # Try simpler pattern
            pattern2 = re.compile(
                rf'(<div id="{carousel_id}"[^>]*>[\s\S]*?scrollbar-width:none;"?>)',
                re.DOTALL
            )
            match = pattern2.search(html)

        if match:
            insert_point = match.end()
            cards_html = '\n' + '\n'.join(cards)
            html = html[:insert_point] + cards_html + html[insert_point:]
            print(f"  ✓ Injected {len(cards)} cards into {carousel_id}")
        else:
            print(f"  ✗ Could not find {carousel_id} in HTML!")

    with open(HTML_FILE, 'w', encoding='utf-8') as f:
        f.write(html)
    print("  ✓ index.html saved!")

    # ── Summary ──
    print("\n" + "=" * 60)
    print("📋 SUMMARY")
    print("=" * 60)
    for r in results:
        status = "✓" if os.path.exists(os.path.join(SITE_DIR, r['image'])) else "⚠ NO IMG"
        print(f"  {status} [{r['carousel']}] {r['name'][:45]} — {r['price_str']}")

    print(f"\n✅ {len(results)} products processed!")
    return 0


if __name__ == '__main__':
    sys.exit(main())
