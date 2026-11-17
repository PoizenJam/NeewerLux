"""Neewer lights: light states to command bytes and back, writes, and capabilities.

NeewerLux holds each light's state as values (LightState); this module is the only place that
knows the Neewer byte encoding, so other brands can be added beside it later (1.5 milestone 7).

A state encodes to the bytes NeewerLux has always stored for a light:
  CCT    [120, 135, 2, bri, kelvin / 100, checksum]
  HSI    [120, 134, 4, hue & 255, hue >> 8, sat, bri, checksum]
  SCENE  [120, 136, 2, bri, scene, checksum]
  power  [120, 129, 1, 1 (on) or 2 (off), checksum]   (mode None: a power command alone)
A colour state with power False is the colour to show once switched back on: its first byte is
0 (the checksum stays that of the 120 form), which the write path sends as a power off.
"""
from dataclasses import dataclass, replace

SET_LIGHT_UUID = "69400002-B5A3-F393-E0A9-E50E24DCCA99"

CMD_POWER, CMD_HSI, CMD_CCT, CMD_SCENE = 129, 134, 135, 136

# The colours each built-in scene (1 to 9) cycles through, for drawing it still on a swatch.
# Approximate, from the scene names (the light doesn't report them): police red and blue,
# ambulance red and white, fire truck red and orange, fireworks and party rainbow, candlelight
# warm white, lightning cool white, paparazzi white, TV screen bluish white.
_RAINBOW = ((255, 0, 0), (255, 170, 0), (0, 200, 0), (0, 120, 255), (170, 0, 255))
SCENE_COLOURS = {1: ((255, 0, 0), (0, 60, 255)), 2: ((255, 0, 0), (255, 255, 255)), 3: ((255, 0, 0), (255, 120, 0)),
                 4: _RAINBOW, 5: _RAINBOW[::-1], 6: ((255, 160, 70),), 7: ((215, 225, 255), (120, 140, 255)),
                 8: ((255, 255, 255),), 9: ((190, 210, 255), (120, 150, 230))}


@dataclass(frozen=True)
class LightState:
    """What a light shows, or is to show: mode "CCT", "HSI" or "SCENE" (None: power alone),
    power, and the values for the mode (bri 0 to 100, kelvin, hue 0 to 360, sat 0 to 100,
    scene 1 to 9). Brand-neutral: nothing here is Neewer's."""
    mode: object = None
    power: bool = True
    bri: int = 0
    kelvin: int = 0
    hue: int = 0
    sat: int = 0
    scene: int = 0

    def with_(self, **changes):
        return replace(self, **changes)


def checksum(data):
    """Neewer's checksum: the sum of every byte but the last, as unsigned bytes, mod 256."""
    total = 0
    for v in data[:-1]:
        total += int(v + 256) if v < 0 else int(v)
    return total & 255


def encode(state):
    """The command bytes for a state ([] for no state)."""
    if state is None:
        return []
    if state.mode is None:
        data = [120, CMD_POWER, 1, 1 if state.power else 2, 0]
    elif state.mode == "CCT":
        data = [120, CMD_CCT, 2, state.bri, state.kelvin // 100, 0]
    elif state.mode == "HSI":
        data = [120, CMD_HSI, 4, state.hue & 255, (state.hue & 65280) >> 8, state.sat, state.bri, 0]
    elif state.mode == "SCENE":
        data = [120, CMD_SCENE, 2, state.bri, state.scene, 0]
    else:
        raise ValueError("unknown mode %r" % (state.mode,))
    data[-1] = checksum(data)
    if state.mode is not None and not state.power:
        data[0] = 0
    return data


def decode(data):
    """The state for command bytes (None for none)."""
    if not data:
        return None
    cmd = data[1]
    if cmd == CMD_POWER:
        return LightState(mode=None, power=data[3] == 1)
    power = data[0] != 0
    if cmd == CMD_CCT:
        return LightState(mode="CCT", power=power, bri=data[3], kelvin=data[4] * 100)
    if cmd == CMD_HSI:
        return LightState(mode="HSI", power=power, bri=data[6], hue=data[3] + (data[4] << 8), sat=data[5])
    if cmd == CMD_SCENE:
        return LightState(mode="SCENE", power=power, bri=data[3], scene=data[4])
    raise ValueError("not a light state: %r" % (data,))


async def write(client, data):
    """Send command bytes to a light over its Bleak connection."""
    await client.write_gatt_char(SET_LIGHT_UUID, bytearray(data), False)


def capabilities(light):
    """What a light can do: its colour temperature range in Kelvin, whether it is CCT only, and
    whether it has HSI colour (every light that isn't CCT only)."""
    return {"cctRange": list(light.cctRange), "cctOnly": bool(light.cctOnly), "hsi": not light.cctOnly}
