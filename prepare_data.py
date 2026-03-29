#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prepare_data.py - Telecharge les cours historiques de l'or (LBMA)
et les taux de change USD->EUR (BCE), applique un forward fill,
et genere metal_prices_data.js.

Note: Silver data has been removed because no freely downloadable CSV
source for historical silver prices (USD/oz) is currently available.
The Nisab calculation will use gold only (85 grams).
"""

import csv
import json
import io
import os
import sys
import urllib.request
import urllib.error
import ssl
import re
from datetime import date, timedelta

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

START_DATE = date(1990, 1, 1)
END_DATE = date.today()

# SSL context that doesn't verify (some corporate/school networks block certs)
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


def download(url, label=""):
    """Download URL content as string."""
    print(f"  Downloading {label}: {url}")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    try:
        with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as resp:
            data = resp.read()
            try:
                return data.decode("utf-8")
            except UnicodeDecodeError:
                return data.decode("latin-1")
    except urllib.error.HTTPError as e:
        print(f"    HTTP Error {e.code}")
        return None
    except Exception as e:
        print(f"    Error: {e}")
        return None


def forward_fill(data_dict, start_date, end_date):
    """Fill missing days with last known value."""
    result = {}
    current = start_date
    last_value = None
    while current <= end_date:
        key = current.isoformat()
        if key in data_dict:
            last_value = data_dict[key]
        if last_value is not None:
            result[key] = round(last_value, 4)
        current += timedelta(days=1)
    return result


def parse_date(s):
    """Parse YYYY-MM-DD or YYYY-MM date string."""
    s = s.strip()
    try:
        parts = s.split("-")
        if len(parts) == 3:
            return date(int(parts[0]), int(parts[1]), int(parts[2]))
        elif len(parts) == 2:
            # YYYY-MM -> use the 1st of the month
            return date(int(parts[0]), int(parts[1]), 1)
    except (ValueError, IndexError):
        pass
    return None


# ================================================================
# GOLD
# ================================================================

def fetch_gold_prices():
    gold = {}

    # Source 1: datahub.io monthly (works reliably)
    print("\n[GOLD] Source 1: datahub.io monthly")
    url = "https://raw.githubusercontent.com/datasets/gold-prices/master/data/monthly.csv"
    raw = download(url, "gold monthly")
    if raw:
        reader = csv.DictReader(io.StringIO(raw))
        for row in reader:
            try:
                d_str = row.get("Date", "").strip()
                p_str = row.get("Price", "").strip()
                if d_str and p_str:
                    d = parse_date(d_str)
                    if d and d >= START_DATE:
                        gold[d.isoformat()] = float(p_str)
            except (ValueError, KeyError):
                continue
    print(f"    -> {len(gold)} entries after datahub monthly")

    # Source 2: FRED GOLDAMGBD228NLBM (daily gold AM fixing)
    print("\n[GOLD] Source 2: FRED daily")
    # FRED sometimes resets connections, try with retries
    for attempt in range(3):
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?bgcolor=%23e1e9f0&fo=open%20sans&id=GOLDAMGBD228NLBM&cosd=1990-01-01&fq=Daily"
        raw = download(url, f"gold FRED (attempt {attempt+1})")
        if raw:
            reader = csv.DictReader(io.StringIO(raw))
            count = 0
            for row in reader:
                try:
                    d_str = row.get("DATE", "").strip()
                    p_str = row.get("GOLDAMGBD228NLBM", "").strip()
                    if d_str and p_str and p_str != ".":
                        d = parse_date(d_str)
                        if d and d >= START_DATE:
                            gold[d.isoformat()] = float(p_str)
                            count += 1
                except (ValueError, KeyError):
                    continue
            print(f"    -> +{count} entries from FRED")
            break
        import time
        time.sleep(2)

    # Source 3: Nasdaq Data Link (formerly Quandl) - free tier
    if len(gold) < 2000:
        print("\n[GOLD] Source 3: Nasdaq Data Link")
        url = "https://data.nasdaq.com/api/v3/datasets/LBMA/GOLD.csv?start_date=1990-01-01&order=asc"
        raw = download(url, "gold Nasdaq/Quandl")
        if raw:
            reader = csv.DictReader(io.StringIO(raw))
            count = 0
            for row in reader:
                try:
                    d_str = row.get("Date", "").strip()
                    # Use USD (PM) column, or USD (AM)
                    p_str = row.get("USD (PM)", row.get("USD (AM)", "")).strip()
                    if d_str and p_str:
                        d = parse_date(d_str)
                        if d and d >= START_DATE:
                            gold[d.isoformat()] = float(p_str)
                            count += 1
                except (ValueError, KeyError):
                    continue
            print(f"    -> +{count} entries from Nasdaq")

    print(f"\n  TOTAL GOLD: {len(gold)} raw entries")
    return gold


# ================================================================
# USD to EUR
# ================================================================

def fetch_usd_to_eur():
    rates = {}

    # Source 1: ECB SDMX CSV data API
    print("\n[EUR/USD] Source 1: ECB API")
    url = "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?format=csvdata"
    raw = download(url, "EUR/USD ECB")
    if raw:
        reader = csv.DictReader(io.StringIO(raw))
        for row in reader:
            try:
                d_str = row.get("TIME_PERIOD", "").strip()
                v_str = row.get("OBS_VALUE", "").strip()
                if d_str and v_str:
                    d = parse_date(d_str)
                    if d:
                        # ECB series EXR.D.USD.EUR.SP00.A = USD per 1 EUR
                        # We need EUR per 1 USD = 1/rate
                        rate = float(v_str)
                        if rate > 0:
                            rates[d.isoformat()] = round(1.0 / rate, 6)
            except (ValueError, KeyError):
                continue
    print(f"    -> {len(rates)} entries from ECB")

    # Source 2: FRED DEXUSEU
    if len(rates) < 2000:
        print("\n[EUR/USD] Source 2: FRED")
        for attempt in range(3):
            url = "https://fred.stlouisfed.org/graph/fredgraph.csv?bgcolor=%23e1e9f0&fo=open%20sans&id=DEXUSEU&cosd=1999-01-01&fq=Daily"
            raw = download(url, f"EUR/USD FRED (attempt {attempt+1})")
            if raw:
                reader = csv.DictReader(io.StringIO(raw))
                count = 0
                for row in reader:
                    try:
                        d_str = row.get("DATE", "").strip()
                        v_str = row.get("DEXUSEU", "").strip()
                        if d_str and v_str and v_str != ".":
                            d = parse_date(d_str)
                            if d:
                                rate = float(v_str)
                                if rate > 0:
                                    rates[d.isoformat()] = round(1.0 / rate, 6)
                                    count += 1
                    except (ValueError, KeyError):
                        continue
                print(f"    -> +{count} entries from FRED")
                break
            import time
            time.sleep(2)

    print(f"\n  TOTAL EUR/USD: {len(rates)} raw entries")
    return rates


# ================================================================
# Generate JS
# ================================================================

def generate_js(gold, usd_to_eur, output_path="metal_prices_data.js"):
    print("\nApplying forward fill...")

    gold_filled = forward_fill(gold, START_DATE, END_DATE)
    eur_start = date(1999, 1, 4)
    usd_to_eur_filled = forward_fill(usd_to_eur, eur_start, END_DATE)

    print(f"\n{'='*50}")
    print(f"STATISTICS")
    print(f"{'='*50}")

    for name, data in [("Gold (USD/oz)", gold_filled),
                       ("USD->EUR", usd_to_eur_filled)]:
        dates = sorted(data.keys())
        if dates:
            print(f"\n  {name}:")
            print(f"    Entries: {len(data)}")
            print(f"    First: {dates[0]} = {data[dates[0]]}")
            print(f"    Last:  {dates[-1]} = {data[dates[-1]]}")
        else:
            print(f"\n  {name}: NO DATA!")

    # Build JS content
    print(f"\nGenerating {output_path}...")

    def dict_to_js_compact(d):
        """Compact JS object - one entry per line for smaller file size."""
        entries = []
        for k in sorted(d.keys()):
            entries.append(f'"{k}":{d[k]}')
        # Join with commas, 5 per line
        lines = []
        for i in range(0, len(entries), 5):
            lines.append(",".join(entries[i:i+5]))
        return "{\n" + ",\n".join(lines) + "\n}"

    # Find last real gold data date (last date where value actually came from source, not forward-fill)
    gold_raw_dates = sorted(gold.keys())
    gold_last_real = gold_raw_dates[-1] if gold_raw_dates else "1990-01-01"
    print(f"  Last real gold data point: {gold_last_real}")

    # Same for EUR
    eur_raw_dates = sorted(usd_to_eur.keys())
    eur_last_real = eur_raw_dates[-1] if eur_raw_dates else "1999-01-04"
    print(f"  Last real EUR/USD data point: {eur_last_real}")

    js = f"""// Generated {date.today().isoformat()} - Gold/EUR data (gold-only Nisab)
// Gold: USD per troy ounce (forward-filled daily)
const GOLD_USD_OZ = {dict_to_js_compact(gold_filled)};

// EUR per 1 USD (forward-filled daily, from 1999-01-04)
const USD_TO_EUR = {dict_to_js_compact(usd_to_eur_filled)};

const OZ_TROY_TO_GRAMS = 31.1035;
const GOLD_DATA_LAST_DATE = "{gold_last_real}";
const EUR_DATA_LAST_DATE = "{eur_last_real}";
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(js)

    fsize = os.path.getsize(output_path)
    print(f"\n  Output: {output_path}")
    print(f"  Size:   {fsize:,} bytes ({fsize/1024:.1f} KB)")
    print(f"{'='*50}")

    return gold_filled, usd_to_eur_filled


def main():
    print("=" * 50)
    print("DATA PREPARATION - Gold, EUR/USD (gold-only Nisab)")
    print("=" * 50)

    gold = fetch_gold_prices()
    usd_to_eur = fetch_usd_to_eur()

    # Check
    warns = []
    if len(gold) < 100:
        warns.append(f"Gold: only {len(gold)} entries")
    if len(usd_to_eur) < 100:
        warns.append(f"EUR/USD: only {len(usd_to_eur)} entries")

    if warns:
        print("\nWARNING - Low data:")
        for w in warns:
            print(f"  - {w}")

    generate_js(gold, usd_to_eur)
    print("\nDone!")


if __name__ == "__main__":
    main()
