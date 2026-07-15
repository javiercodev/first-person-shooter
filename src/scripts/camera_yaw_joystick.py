import math
import bge

# CONFIGURATION
JOYSTICK_INDEX = 0
AXIS_INDEX = 2               
INVERT_AXIS = True
DEADZONE = 0.15
SENSITIVITY = 90.0           

# Optional yaw limits (set USE_LIMITS = True to enable clamping)
USE_LIMITS = False
YAW_MIN = -180.0
YAW_MAX = 180.0


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

    if INVERT_AXIS:
        raw = -raw

    fps = bge.logic.getAverageFrameRate()
    dt = 1.0 / fps if fps > 0 else (1.0 / 60.0)

    # accumulated yaw (absolute), used only to know HOW MUCH
    # ...is left to rotate, never to reconstruct the full orientation
    prev_yaw = obj.get("cam_yaw", 0.0)
    new_yaw = prev_yaw + raw * SENSITIVITY * dt

    if USE_LIMITS:
        new_yaw = max(YAW_MIN, min(YAW_MAX, new_yaw))
    else:
        # keep it bounded to avoid float growing unbounded over long sessions
        new_yaw = (new_yaw + 180.0) % 360.0 - 180.0

    delta_deg = new_yaw - prev_yaw
    obj["cam_yaw"] = new_yaw

    if abs(delta_deg) > 0.0001:
        delta_rad = math.radians(delta_deg)
        # we only apply the delta, in local space, without touching X/Y
        # ...which is already handled by Mouse Look
        obj.applyRotation((0.0, 0.0, delta_rad), True)


main()