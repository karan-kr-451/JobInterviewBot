"""
Quick audio device checker - Run this to see all available audio devices
"""

import sounddevice as sd

print("=" * 70)
print("AUDIO DEVICES DETECTED")
print("=" * 70)

devices = sd.query_devices()

print("\nINPUT DEVICES (Microphones):")
print("-" * 70)
for i, device in enumerate(devices):
    if device['max_input_channels'] > 0:
        name = device['name']
        channels = device['max_input_channels']
        default = " (DEFAULT)" if i == sd.default.device[0] else ""
        print(f"[{i}] {name}")
        print(f"    Channels: {channels}{default}")
        print()

print("\nOUTPUT DEVICES (Speakers/Headphones):")
print("-" * 70)
for i, device in enumerate(devices):
    if device['max_output_channels'] > 0:
        name = device['name']
        channels = device['max_output_channels']
        default = " (DEFAULT)" if i == sd.default.device[1] else ""
        print(f"[{i}] {name}")
        print(f"    Channels: {channels}{default}")
        print()

print("=" * 70)
print("\nTo use a specific device:")
print("1. Note the device index [number]")
print("2. Open Settings in the GUI")
print("3. Enter the index in 'Override Index' field")
print("4. Or select from dropdown")
print("=" * 70)
