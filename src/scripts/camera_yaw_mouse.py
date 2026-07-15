import math
import bge

# CONFIGURATION
SENSITIVITY = 0.15
INVERT_AXIS = False
USE_LIMITS = False
YAW_MIN = -180.0
YAW_MAX = 180.0


def main():
    cont = bge.logic.getCurrentController()
    obj = cont.owner

    mouse = bge.logic.mouse

    width = bge.render.getWindowWidth()
    height = bge.render.getWindowHeight()
    center_x_px = width // 2
    center_y_px = height // 2

    pos = mouse.position
    current_x_px = round(pos[0] * width)
    delta_x_px = current_x_px - center_x_px

    mouse.position = (center_x_px / width, center_y_px / height)

    # first frame after start: just center the mouse, ignore whatever delta this produced
    if not obj.get("mouse_initialized_yaw", False):
        obj["mouse_initialized_yaw"] = True
        return

    if abs(delta_x_px) < 1:
        return

    raw = -float(delta_x_px)
    if INVERT_AXIS:
        raw = -raw

    prev_yaw = obj.get("cam_yaw", 0.0)
    new_yaw = prev_yaw + raw * SENSITIVITY

    if USE_LIMITS:
        new_yaw = max(YAW_MIN, min(YAW_MAX, new_yaw))
    else:
        new_yaw = (new_yaw + 180.0) % 360.0 - 180.0

    delta_deg = new_yaw - prev_yaw
    obj["cam_yaw"] = new_yaw

    if abs(delta_deg) > 0.0001:
        delta_rad = math.radians(delta_deg)
        obj.applyRotation((0.0, 0.0, delta_rad), True)


main()