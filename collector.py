#!/usr/bin/env python3
"""SBMLife V4 public Kraken 1-minute candle archival. No credentials/orders."""
import csv
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import requests

BASE = 'https://api.kraken.com/0/public/OHLC'
PAIRS = {'BTC': 'XBTUSD', 'ETH': 'ETHUSD'}
FIELDS = ['time', 'open', 'high', 'low', 'close', 'volume', 'count']
DATA = Path(__file__).resolve().parent / 'data'
DATA.mkdir(exist_ok=True)

def fetch(pair):
    last = None
    for attempt in range(4):
        try:
            r = requests.get(BASE, params={'pair': pair, 'interval': 1}, timeout=25,
                             headers={'User-Agent': 'SBMLife-V4-Research-Collector/1.0'})
            r.raise_for_status()
            body = r.json()
            if body.get('error'):
                raise RuntimeError(str(body['error']))
            result = body['result']
            key = next(k for k in result if k != 'last')
            candles = result[key]
            # Kraken documents last candle as unfinished, regardless of since.
            return candles[:-1]
        except Exception as exc:
            last = exc
            time.sleep(2 ** attempt)
    raise RuntimeError(f'Kraken API failed: {last}')

def read_existing(path):
    out = {}
    if path.exists():
        with path.open(newline='') as f:
            for row in csv.DictReader(f):
                if all(k in row for k in FIELDS):
                    try:
                        stamp = int(datetime.fromisoformat(row['time'].replace('Z', '+00:00')).timestamp())
                        out[stamp] = {k: row[k] for k in FIELDS}
                    except (ValueError, TypeError):
                        pass
    return out

def main():
    failures = 0
    for symbol, pair in PAIRS.items():
        path = DATA / f'{symbol}_kraken_1m.csv'
        try:
            rows = fetch(pair)
            if not rows:
                raise RuntimeError('No completed candles')
            old = read_existing(path)
            old_count = len(old)
            for r in rows:
                stamp = int(r[0])
                vals = [float(r[i]) for i in (1, 2, 3, 4, 6)]
                op, hi, lo, close, volume = vals
                if not (0 < lo <= op <= hi and lo <= close <= hi and volume >= 0):
                    continue
                old[stamp] = {
                    'time': datetime.fromtimestamp(stamp, timezone.utc).isoformat(),
                    'open': str(r[1]), 'high': str(r[2]), 'low': str(r[3]),
                    'close': str(r[4]), 'volume': str(r[6]), 'count': str(r[7]),
                }
            stamps = sorted(old)
            tmp = path.with_suffix('.tmp')
            with tmp.open('w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(old[t] for t in stamps)
            os.replace(tmp, path)
            missing = sum(max(0, (b - a) // 60 - 1) for a, b in zip(stamps, stamps[1:]))
            print(f'{symbol}: {len(rows)} fetched, {len(stamps)} stored (+{len(stamps)-old_count}), '
                  f'{missing} missing minute slots; latest={old[stamps[-1]]["time"]}')
        except Exception as exc:
            failures += 1
            print(f'{symbol}: ERROR: {exc}', file=sys.stderr)
    if failures:
        sys.exit(1)

if __name__ == '__main__':
    main()
