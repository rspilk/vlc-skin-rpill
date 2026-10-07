"""Create the test audio tools/run.ps1 plays (200 s, 220 Hz tone).

The long name exercises the scrolling ticker; Short.wav keeps it still.
"""
import math
import struct
import wave
from pathlib import Path

out = Path(__file__).resolve().parent.parent / "testmedia"
out.mkdir(exist_ok=True)
rate = 22050
tone = b"".join(struct.pack("<h", int(3000 * math.sin(i * 2 * math.pi * 220 / rate)))
                for i in range(rate * 200))
for name in ("Béla Fleck - Punchdrunk.wav", "Short.wav"):
    with wave.open(str(out / name), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(tone)
    print("wrote", out / name)
