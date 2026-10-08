"""
Real-time CAN frame sources.

A "source" is any generator yielding (timestamp, arbitration_id, data_bytes)
tuples, paced in real time. Two are provided so the same downstream pipeline
works whether you're testing against the recorded log or wired to real
hardware later.
"""

import time
import pandas as pd


def replay_csv_realtime(csv_path, speed=1.0):
    """
    Replay a recorded CAN log as if it were arriving live, pacing frames
    using their own recorded timestamps (so gaps in the log become real
    waits, just like a live bus). speed=2.0 plays twice as fast,
    speed=1000 is effectively "as fast as possible" for testing.
    """
    df = pd.read_csv(csv_path)
    last_t = None
    for _, row in df.iterrows():
        t = float(row["timestamp"])
        if last_t is not None:
            dt = (t - last_t) / speed
            if dt > 0:
                time.sleep(dt)
        last_t = t

        arb_id = row["arbitration_id"]
        arb_id = int(arb_id, 16) if isinstance(arb_id, str) and arb_id.startswith("0x") else int(arb_id)
        data = bytes.fromhex(str(row["data"]).strip())
        yield t, arb_id, data


def live_python_can(channel="can0", bustype="socketcan"):
    """
    Read frames from a real CAN interface using python-can. Only used if
    you're actually wired to a vehicle/BMS bus. Needs `pip install python-can`
    and an OS-level CAN interface (e.g. `sudo ip link set can0 up type can
    bitrate 500000` on Linux with SocketCAN, or a USB-CAN adapter's own
    bustype like 'kvaser', 'pcan', 'vector', 'slcan' on Windows).
    """
    import sys
    try:
        import can
    except ImportError:
        print("\n[ERROR] python-can is required for live hardware streaming.")
        print("Please install it with: pip install python-can\n")
        sys.exit(1)

    if sys.platform.startswith("win") and bustype.lower() == "socketcan":
        print("\n" + "=" * 80)
        print("[NOTICE] SocketCAN ('can0') is a Linux-only kernel interface.")
        print("On Windows, please use your hardware adapter's driver interface, for example:")
        print("  - PCAN-USB:     python src/realtime_pipeline.py --live-channel PCAN_USBBUS1 --bustype pcan")
        print("  - Vector CAN:   python src/realtime_pipeline.py --live-channel 0 --bustype vector")
        print("  - SLCAN (USB):  python src/realtime_pipeline.py --live-channel COM3 --bustype slcan")
        print("  - Virtual test: python src/realtime_pipeline.py --live-channel test --bustype virtual")
        print("  - CSV Replay:   python src/realtime_pipeline.py --replay data/ev_pack_drive.csv --speed 10")
        print("=" * 80 + "\n")
        sys.exit(1)

    try:
        bus = can.interface.Bus(channel=channel, bustype=bustype)
    except Exception as e:
        print(f"\n[ERROR] Failed to open CAN channel '{channel}' with bustype '{bustype}': {e}")
        print("If you do not have physical CAN hardware connected, run with the recorded drive replay instead:")
        print("  python src/realtime_pipeline.py --replay data/ev_pack_drive.csv --speed 10\n")
        sys.exit(1)

    t0 = None
    try:
        for msg in bus:
            if t0 is None:
                t0 = msg.timestamp
            yield msg.timestamp - t0, msg.arbitration_id, bytes(msg.data)
    finally:
        bus.shutdown()
