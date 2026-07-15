import math
import bge

# CONFIGURATION
JOYSTICK_INDEX = 0
AXIS_INDEX = 3
INVERT_AXIS = False          
DEADZONE = 0.15
SENSITIVITY = 90.0
PITCH_MIN = -60.0
PITCH_MAX = 60.0


def main():
    cont = bge.logic.getCurrentController()
    obj = cont.owner
    joysticks = bge.logic.joysticks
    if JOYSTICK_INDEX >= len(joysticks) or joysticks[JOYSTICK_INDEX] is None:
        return
    joy = joysticks[JOYSTICK_INDEX]
    axis_values = joy.axisValues
    if AXIS_INDEX >= len(axis_values):
        return
    raw = axis_values[AXIS_INDEX]
    if abs(raw) < DEADZONE:
        raw = 0.0
    else:
        sign = 1.0 if raw > 0 else -1.0
        raw = sign * (abs(raw) - DEADZONE) / (1.0 - DEADZONE)

    # stick up reports negative, but pitch should grow upward -> flip sign
    raw = -raw

    if INVERT_AXIS:
        raw = -raw

    fps = bge.logic.getAverageFrameRate()
    dt = 1.0 / fps if fps > 0 else (1.0 / 60.0)

    prev_pitch = obj.get("cam_pitch", 0.0)
    new_pitch = prev_pitch + raw * SENSITIVITY * dt
    new_pitch = max(PITCH_MIN, min(PITCH_MAX, new_pitch))
    delta_deg = new_pitch - prev_pitch
    obj["cam_pitch"] = new_pitch
    if abs(delta_deg) > 0.0001:
        delta_rad = math.radians(delta_deg)
        obj.applyRotation((delta_rad, 0.0, 0.0), True)


main()