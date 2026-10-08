"""Source-grounded decoder for the supplied Smart fortwo CAN dataset.

IMPORTANT:
    This module decodes only signals explicitly documented in the supplied
    Smart fortwo dataset README. Unknown CAN IDs are returned as unknown
    instead of being guessed.
"""

from __future__ import annotations

from typing import Dict, Optional


def _bytes(data: str | bytes) -> bytes:
    if isinstance(data, bytes):
        return data
    value = data.replace(" ", "").replace(":", "").strip()
    return bytes.fromhex(value)


def decode_soc(data: str | bytes) -> float:
    """Decode SOC from CAN ID 0x2D5 using the README formula."""
    b = _bytes(data)
    if len(b) < 2:
        raise ValueError("0x2D5 requires at least 2 data bytes")
    return ((b[0] & 0x03) * 256 + b[1]) / 10.0


def decode_charge_limit_reply(data: str | bytes) -> Optional[float]:
    """Decode the documented 0x483 charging-current-limit byte.

    The supplied README identifies the second byte of the *second* 0x483
    reply as the limit. This function therefore returns byte 1 as an integer
    number of amps for a matching response frame.
    """
    b = _bytes(data)
    if len(b) < 2:
        return None
    return float(b[1])


def decode_charge_limit_command(data: str | bytes) -> float:
    """Decode the documented 0x512 fifth-byte current-limit command."""
    b = _bytes(data)
    if len(b) < 5:
        raise ValueError("0x512 requires at least 5 data bytes")
    return 32.0 - (0xA4 - b[4]) / 2.0


def decode_frame(can_id: int | str, data: str | bytes) -> Dict[str, object]:
    """Decode a single documented Smart fortwo CAN frame."""
    if isinstance(can_id, str):
        can_id = int(can_id, 16) if can_id.lower().startswith("0x") else int(can_id, 16)

    if can_id == 0x2D5:
        return {"can_id": "0x2D5", "signal": "SOC", "value": decode_soc(data), "unit": "%"}
    if can_id == 0x483:
        return {
            "can_id": "0x483",
            "signal": "charging_current_limit_reply_byte1",
            "value": decode_charge_limit_reply(data),
            "unit": "A (documented example)",
        }
    if can_id == 0x512:
        return {
            "can_id": "0x512",
            "signal": "charging_current_limit_command",
            "value": decode_charge_limit_command(data),
            "unit": "A",
        }
    if can_id == 0x61A:
        return {"can_id": "0x61A", "signal": "diagnostic_request", "value": data.hex() if isinstance(data, bytes) else data}

    return {"can_id": f"0x{can_id:X}", "signal": "unknown", "value": None, "unit": None}


if __name__ == "__main__":
    print(decode_frame(0x2D5, "03 E5 00 00 00 00 00 00"))
    print(decode_frame(0x483, "21 08 FF FF 00 00 00 02"))
    print(decode_frame(0x512, "00 00 1F FF 74 00 00 00"))
