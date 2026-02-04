import csv
import time
from datetime import datetime, timezone
from typing import Iterable

import requests

api_exchange_address = "https://www.deribit.com"


def get_funding_rate_value_or_none(
    instrument: str,
    start_timestamp: int,
    end_timestamp: int,
    *,
    timeout_s: float = 30.0,
    retries: int = 3,
    retry_backoff_s: float = 1.0,
) -> float | None:
    """
    Calls /api/v2/public/get_funding_rate_value.

    Returns:
      - float (payload["result"]) on success
      - None on ANY Deribit JSON-RPC error (including HTTP 400 cases like invalid params)
      - None on network/HTTP failures after retries

    This matches your requirement: treat errors as "no data yet" and keep going.
    """
    url = "/api/v2/public/get_funding_rate_value"
    params = {
        "instrument_name": instrument,
        "start_timestamp": start_timestamp,
        "end_timestamp": end_timestamp,
    }

    last_exc: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            r = requests.get(api_exchange_address + url, params=params, timeout=timeout_s)

            # Try JSON regardless of HTTP status (Deribit can return JSON-RPC errors with 400)
            try:
                payload = r.json()
            except Exception:
                payload = None

            # If Deribit sent a JSON-RPC error object, treat as "no data"
            if isinstance(payload, dict) and payload.get("error"):
                return None

            # If it's not OK and not a JSON-RPC error we could parse, treat as transient
            if not r.ok:
                r.raise_for_status()

            if not isinstance(payload, dict) or "result" not in payload:
                # Unexpected shape; treat as transient and retry
                raise RuntimeError(f"Unexpected response: status={r.status_code}, body={r.text[:300]}")

            return payload["result"]

        except Exception as e:
            last_exc = e
            if attempt < retries:
                time.sleep(retry_backoff_s * attempt)

    # After retries, treat as "no data"
    return None


def _parse_month_yyyy_mm(month_str: str) -> tuple[int, int]:
    y, m = month_str.split("-")
    y, m = int(y), int(m)
    if not (1 <= m <= 12):
        raise ValueError(f"Invalid month '{month_str}'. Expected YYYY-MM.")
    return y, m


def _month_start_utc(year: int, month: int) -> datetime:
    return datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc)


def _add_one_month(dt: datetime) -> datetime:
    if dt.month == 12:
        return datetime(dt.year + 1, 1, 1, tzinfo=timezone.utc)
    return datetime(dt.year, dt.month + 1, 1, tzinfo=timezone.utc)


def _to_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _month_label(dt: datetime) -> str:
    return f"{dt.year:04d}-{dt.month:02d}"


def fetch_monthly_funding_multi_instruments_to_csv(
    instruments: Iterable[str],
    start_month: str,
    end_month: str,
    csv_path: str,
    *,
    sleep_s: float = 0.0,
    timeout_s: float = 30.0,
    retries: int = 3,
    retry_backoff_s: float = 1.0,
    error_value: float = 0.0,
):
    """
    Wide CSV: one row per month, one column per instrument.
    Any error (instrument not open, invalid params, pre-listing months, etc.) => writes `error_value` (default 0.0)
    and continues.
    """
    instruments = [i.strip() for i in instruments if i and i.strip()]
    if not instruments:
        raise ValueError("No instruments provided.")

    sy, sm = _parse_month_yyyy_mm(start_month)
    ey, em = _parse_month_yyyy_mm(end_month)

    current = _month_start_utc(sy, sm)
    end_dt_inclusive = _month_start_utc(ey, em)
    if current > end_dt_inclusive:
        raise ValueError("start_month must be <= end_month")

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["month", "start_timestamp_ms", "end_timestamp_ms", *instruments])

        while current <= end_dt_inclusive:
            next_month = _add_one_month(current)
            start_ts = _to_ms(current)
            end_ts = _to_ms(next_month) - 1  # inclusive end-of-month

            values = []
            for inst in instruments:
                v = get_funding_rate_value_or_none(
                    inst,
                    start_ts,
                    end_ts,
                    timeout_s=timeout_s,
                    retries=retries,
                    retry_backoff_s=retry_backoff_s,
                )
                values.append(v if v is not None else error_value)

                if sleep_s > 0:
                    time.sleep(sleep_s)

            writer.writerow([_month_label(current), start_ts, end_ts, *values])
            current = next_month


# Example usage:
instruments = [
    "BTC-PERPETUAL", "ETH-PERPETUAL", "SOL_USDC-PERPETUAL",
    "PAXG_USDC-PERPETUAL", "BTC_USDC-PERPETUAL", "ETH_USDC-PERPETUAL",
    "XRP_USDC-PERPETUAL", "UNI_USDC-PERPETUAL",
    "DOGE_USDC-PERPETUAL", "ADA_USDC-PERPETUAL", "LINK_USDC-PERPETUAL",
    "BCH_USDC-PERPETUAL", "AVAX_USDC-PERPETUAL", "LTC_USDC-PERPETUAL",
    "DOT_USDC-PERPETUAL", "TRX_USDC-PERPETUAL", "NEAR_USDC-PERPETUAL",
    "BNB_USDC-PERPETUAL", "TRUMP_USDC-PERPETUAL", "ALGO_USDC-PERPETUAL",

]
fetch_monthly_funding_multi_instruments_to_csv(
    instruments=instruments,
    start_month="2019-03",
    end_month="2026-01",
    csv_path="funding_rate_value_monthly_wide.csv",
    sleep_s=0.21,
    retries=3,
    error_value=0.0,
)
