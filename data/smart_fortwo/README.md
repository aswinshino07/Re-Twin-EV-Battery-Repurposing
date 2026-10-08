# Smart fortwo Real CAN Dataset for RE-TWIN

This folder contains the supplied Smart fortwo electric-vehicle CAN captures and a source-grounded signal map.

## Files
- `SOURCE_README.md` — original dataset README supplied by the user.
- `charge_current_soc94_2_to_100.txt` — charging-current log from the source dataset.
- `smart_fortwo_charge_soc94_2_to_100.pcap.zip` — main real OBD/CAN capture.
- `smart_fortwo_charge_current_change_12A_to_8A.pcap.zip` — secondary real CAN capture.
- `SMART_FORTWO_SIGNAL_MAP.md` — confirmed signals and explicit limitations.

## Decoder
Use `src/smart_fortwo_can_decoder.py` for the CAN IDs explicitly documented in the source README.

Do not treat undocumented CAN IDs as decoded battery signals until their byte-level definitions are verified.
