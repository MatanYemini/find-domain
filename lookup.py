#!/usr/bin/env python3
"""Domain availability checker backed by the GoDaddy API."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from itertools import product
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional


try:  # Prefer python-dotenv if available to keep parity with the Node version
    from dotenv import load_dotenv  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None  # type: ignore

try:
    import requests  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    requests = None  # type: ignore


BATCH_SIZE = 50
DELAY_SECONDS = 2
LETTERS = "abcdefghijklmnopqrstuvwxyz"
DEFAULT_TLD = ".com"
OUTPUT_FILE = Path("available.json")


def load_env() -> None:
    """Load environment variables from a .env file if possible."""

    if load_dotenv is not None:
        load_dotenv()
        return

    env_path = Path(".env")
    if not env_path.exists():
        return

    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check domain availability using the GoDaddy API",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "letters",
        type=int,
        help="Number of characters to combine when generating domain names",
    )
    parser.add_argument(
        "tlds",
        nargs="?",
        default=DEFAULT_TLD,
        help="Comma-separated list of TLDs (e.g. .com,.io)",
    )
    parser.add_argument(
        "--to",
        dest="max_price",
        type=float,
        default=None,
        help="Maximum acceptable price in USD",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--only-available",
        action="store_true",
        help="Only print domains that are available and within the price filter",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE,
        help="Number of domains to send per API request (max 50 per GoDaddy docs)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DELAY_SECONDS,
        help="Delay in seconds between API requests",
    )
    parser.add_argument(
        "--suffixes",
        default="",
        help="Comma-separated list of suffixes appended before the TLD (e.g. -app,-ai)",
    )
    args = parser.parse_args(argv)

    if args.letters < 1:
        parser.error("letters must be a positive integer")
    if args.batch_size < 1:
        parser.error("batch-size must be at least 1")
    if args.delay < 0:
        parser.error("delay must not be negative")
    if args.max_price is not None and args.max_price < 0:
        parser.error("--to must be a positive number")

    return args


def generate_combos(length: int) -> Iterator[str]:
    for combo in product(LETTERS, repeat=length):
        yield "".join(combo)


def chunked(iterable: Iterable[str], chunk_size: int) -> Iterator[List[str]]:
    chunk: List[str] = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) == chunk_size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def format_price(value: Optional[float]) -> str:
    return f" ${value:.2f}" if value is not None else ""


def normalize_price(obj: Dict[str, object]) -> Optional[float]:
    candidates = [
        obj.get("price"),
        obj.get("priceInfo", {}).get("price") if isinstance(obj.get("priceInfo"), dict) else None,
        obj.get("period", {}).get("price") if isinstance(obj.get("period"), dict) else None,
        obj.get("pricing", {}).get("price") if isinstance(obj.get("pricing"), dict) else None,
    ]

    for candidate in candidates:
        if candidate is None:
            continue
        if isinstance(candidate, (int, float)):
            price = float(candidate)
            return price / 100 if price > 1000 else price
    return None


def is_available(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"true", "available"}
    return False


def is_definitive(value: object) -> bool:
    """Check if the availability result is definitive."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"true", "definitive"}
    return True  # Default to True if not specified


def check_domains_batch(domains: List[str], api_key: str, api_secret: str, verbose: bool) -> List[Dict[str, object]]:
    if requests is None:  # pragma: no cover - dependency missing
        print("❌ The 'requests' package is required. Install it with 'pip install requests'.", file=sys.stderr)
        sys.exit(1)

    url = "https://api.ote-godaddy.com/v1/domains/available?checkType=FULL"
    headers = {
        "Authorization": f"sso-key {api_key}:{api_secret}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        response = requests.post(url, headers=headers, json=domains, timeout=30)
    except requests.RequestException as exc:  # pragma: no cover - network failure
        print(f"⚠️  API request failed: {exc}", file=sys.stderr)
        return []

    if response.status_code >= 400:
        print(f"⚠️  API Error ({response.status_code}): {response.text}")
        if verbose:
            print(
                json.dumps(
                    {
                        "status": response.status_code,
                        "body": response.text,
                    },
                    indent=2,
                )
            )
        return []

    data = response.json()
    # Only show JSON in verbose mode, and only for debugging API structure
    if verbose:
        print("📋 Full API Response:")
        print(json.dumps(data, indent=2))
    return data.get("domains", []) if isinstance(data, dict) else []


def save_results(results: Dict[str, List[Dict[str, object]]]) -> None:
    OUTPUT_FILE.write_text(json.dumps(results, indent=2))
    print(f"\n💾 Results saved to {OUTPUT_FILE}")


def main() -> None:
    load_env()

    args = parse_args()

    suffixes = [suffix.strip() for suffix in args.suffixes.split(",") if suffix.strip()]
    if not suffixes:
        suffixes = [""]

    api_key = os.environ.get("GODADDY_API_KEY")
    api_secret = os.environ.get("GODADDY_API_SECRET")
    if not api_key or not api_secret:
        print("❌ Missing GoDaddy API credentials in .env file", file=sys.stderr)
        sys.exit(1)

    tlds = [t.strip() for t in args.tlds.split(",") if t.strip()]
    if not tlds:
        print("❌ No valid TLDs were provided", file=sys.stderr)
        sys.exit(1)

    base_combinations = 26 ** args.letters
    total_combinations = base_combinations * len(suffixes)
    suffix_display = ", ".join(suffix or "(none)" for suffix in suffixes)
    print(
        "🧩 Config: "
        f"{args.letters}-letter combos | TLDs: {', '.join(tlds)}"
        f" | Suffixes: {suffix_display}"
        f"{' | Max price: $' + str(args.max_price) if args.max_price is not None else ''}"
        f"{' | Verbose mode: ON' if args.verbose else ''}"
    )
    print(f"🧮 {base_combinations:,} base combinations ({total_combinations:,} variants per TLD)")

    available: Dict[str, List[Dict[str, object]]] = {tld: [] for tld in tlds}

    def handle_signal(signum: int, _frame) -> None:  # pragma: no cover - signal handling
        print(f"\n\n⚠️  Received signal {signum}. Saving current results...")
        save_results(available)
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    for tld in tlds:
        print(f"\n🔍 Checking {tld} domains...")
        processed = 0

        domain_iterator = (
            f"{combo}{suffix}{tld}"
            for combo in generate_combos(args.letters)
            for suffix in suffixes
        )

        for batch in chunked(domain_iterator, args.batch_size):
            results = check_domains_batch(batch, api_key, api_secret, args.verbose)
            if args.verbose and results:
                print(f"\n📊 Received {len(results)} results for this batch")

            for result in results:
                domain_name = result.get("domain")
                if not isinstance(domain_name, str):
                    continue

                available_flag = is_available(result.get("available"))
                definitive_flag = is_definitive(result.get("definitive"))
                
                if available_flag:
                    price = normalize_price(result)
                    include = (
                        args.max_price is None
                        or price is None
                        or price <= args.max_price
                    )
                    if include:
                        domain_info: Dict[str, object] = {"domain": domain_name}
                        if price is not None:
                            domain_info["price"] = price
                        if not definitive_flag:
                            domain_info["definitive"] = False
                        available[tld].append(domain_info)
                        if args.verbose:
                            # Green dot for available (verbose mode shows definitive status)
                            print(f"\033[92m●\033[0m {domain_name} (Available{' - Definitive' if definitive_flag else ' - Tentative'})")
                        else:
                            # Green dot for available
                            print(f"\033[92m●\033[0m {domain_name}")
                    else:
                        if not args.only_available and not args.verbose:
                            # Yellow dot for too expensive
                            print(f"\033[93m●\033[0m {domain_name} (too expensive)")
                else:
                    if not args.only_available and not args.verbose:
                        # Red dot for taken
                        print(f"\033[91m●\033[0m {domain_name}")
                    elif args.verbose:
                        print(f"\033[91m●\033[0m {domain_name} (Taken{' - Definitive' if definitive_flag else ' - Tentative'})")

            processed += len(batch)
            print(
                f"⏳ Processed {processed:,}/{total_combinations:,} for {tld}"
            )
            time.sleep(args.delay)

    save_results(available)
    print("✅ Done!")


if __name__ == "__main__":
    main()

