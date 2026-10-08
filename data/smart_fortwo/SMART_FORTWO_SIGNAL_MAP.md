# Smart fortwo EV CAN Signal Map (source-grounded)

This file documents **only** the Smart fortwo CAN signals explicitly described in the supplied source README. It intentionally does not invent mappings for other CAN IDs.

## Capture provenance
- CAN access: OBD port pins 6 and 14.
- CAN interface: CANable USB dongle.
- Main capture: charging from 94.2% to 100%, 240 V AC, charging current limited to 14 A.
- Secondary capture: charging-current change from 12 A to 8 A.
- Source decoding reference named by the supplied README: ED BMSdiag `canDiag.cpp`.

## Confirmed signals from the supplied README

| CAN ID | Signal | Bytes / rule | Unit | Status |
|---|---|---|---|---|
| `0x2D5` | Battery SOC | `(((byte0 & 0x03) * 256) + byte1) / 10` | % | Confirmed |
| `0x483` | Charging-current limit (diagnostic reply) | Second byte of the shown reply | A | Confirmed example |
| `0x512` | Charging-current limit command | Fifth byte; `32 - (0xA4 - byte4) / 2` | A | Confirmed command rule |
| `0x61A` | Diagnostic request | `03 22 02 2A FF FF FF FF` shown in README | request frame | Confirmed example |

### SOC example
For bytes `03 E5 ...` in CAN ID `0x2D5`:

```text
((0x03 & 0x03) * 256 + 0xE5) / 10 = 99.7 %
```

### Charging-current-limit example
The README shows:

```text
61A: 03 22 02 2A FF FF FF FF
483: 10 0C 62 02 2A 00 00 02
61A: 30 08 14 FF FF FF FF FF
483: 21 08 FF FF 00 00 00 02
```

The README identifies the **second byte of the second `0x483` reply** (`08`) as the charging-current limit: 8 A.

### Charging-current-limit command example
The README shows:

```text
512: 00 00 1F FF 00 74 00 00
```

and states that the fifth byte (`0x74`) is the charging-current limit, using:

```text
32 - (0xA4 - 0x74) / 2 = 8 A
```

## Signals NOT confirmed by the supplied README

The README says BMS, cooling and charging information can be decoded using the external ED BMSdiag `canDiag.cpp` source, but it does not provide a complete signal table for:

- pack voltage
- pack current measurement
- individual cell voltages
- battery temperatures
- SOH
- RUL
- fault/status signals

Therefore this project does **not** claim those signals are decoded from the Smart fortwo capture yet.

## RE-TWIN integration status

Use this dataset as a **real automotive CAN source**. The currently confirmed extraction is primarily SOC and charging-current-limit information. Additional BMS signals should only be added after their byte-level definitions are verified from the referenced ED BMSdiag source and against the actual capture.
