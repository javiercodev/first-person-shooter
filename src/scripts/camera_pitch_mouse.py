import math
import bge

# CONFIGURATION
SENSITIVITY = 0.15
INVERT_AXIS = False
PITCH_MIN = -60.0
PITCH_MAX = 60.0


def main():
    cont = bge.logic.getCurrentController()
    obj = cont.owner

    mouse = bge.logic.mouse

    width = bge.render.getWindowWidth()
    height = bge.render.getWindowHeight()
    center_x_px = width // 2
    center_y_px = height // 2

    pos = mouse.position
    current_y_px = round(pos[1] * height)
    delta_y_px = current_y_px - center_y_px

    # always re-center, every frame
    mouse.position = (center_x_px / width, center_y_px / height)

    # first frame after start: just center the mouse, ignore whatever delta this produced
    if not obj.get("mouse_initialized", False):
        obj["mouse_initialized"] = True
        return

    if abs(delta_y_px) < 1:
        return

    raw = -float(delta_y_px)
    if INVERT_AXIS:
        raw = -raw

    prev_pitch = obj.get("cam_pitch", 0.0)
    new_pitch = prev_pitch + raw * SENSITIVITY
    new_pitch = max(PITCH_MIN, min(PITCH_MAX, new_pitch))

    delta_deg = new_pitch - prev_pitch
    obj["cam_pitch"] = new_pitch

    if abs(delta_deg) > 0.0001:
        delta_rad = math.radians(delta_deg)
        obj.applyRotation((delta_rad, 0.0, 0.0), True)


main()