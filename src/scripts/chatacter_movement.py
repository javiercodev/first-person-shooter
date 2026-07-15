import bge

# CONFIGURATION
JOYSTICK_INDEX = 0
AXIS_X_INDEX = 0             
AXIS_Y_INDEX = 1             
INVERT_Y = True              
DEADZONE = 0.15

WALK_SPEED = 2.0             

# Keyboard keys (set to None to disable one)
KEY_FORWARD = bge.events.WKEY
KEY_BACK = bge.events.SKEY
KEY_LEFT = bge.events.AKEY
KEY_RIGHT = bge.events.DKEY


def get_joystick_input():
    joysticks = bge.logic.joysticks
    if JOYSTICK_INDEX >= len(joysticks) or joysticks[JOYSTICK_INDEX] is None:
        return 0.0, 0.0

    joy = joysticks[JOYSTICK_INDEX]
    axis_values = joy.axisValues

    if AXIS_X_INDEX >= len(axis_values) or AXIS_Y_INDEX >= len(axis_values):
        return 0.0, 0.0

    raw_x = axis_values[AXIS_X_INDEX]
    raw_y = axis_values[AXIS_Y_INDEX]

    def apply_deadzone(v):
        if abs(v) < DEADZONE:
            return 0.0
        sign = 1.0 if v > 0 else -1.0
        return sign * (abs(v) - DEADZONE) / (1.0 - DEADZONE)

    raw_x = apply_deadzone(raw_x)
    raw_y = apply_deadzone(raw_y)

    if INVERT_Y:
        raw_y = -raw_y

    return raw_x, raw_y


def get_keyboard_input():
    keyboard = bge.logic.keyboard
    active = keyboard.active_events

    move_x = 0.0
    move_y = 0.0

    if KEY_FORWARD is not None and KEY_FORWARD in active:
        move_y += 1.0
    if KEY_BACK is not None and KEY_BACK in active:
        move_y -= 1.0
    if KEY_RIGHT is not None and KEY_RIGHT in active:
        move_x += 1.0
    if KEY_LEFT is not None and KEY_LEFT in active:
        move_x -= 1.0

    # normalize diagonal keyboard movement so it isn't faster than straight movement
    length = (move_x ** 2 + move_y ** 2) ** 0.5
    if length > 1.0:
        move_x /= length
        move_y /= length

    return move_x, move_y


def main():
    cont = bge.logic.getCurrentController()
    obj = cont.owner

    joy_x, joy_y = get_joystick_input()
    key_x, key_y = get_keyboard_input()

    # combine both sources; keyboard takes priority if both are used at once
    move_x = key_x if key_x != 0.0 else joy_x
    move_y = key_y if key_y != 0.0 else joy_y

    if move_x == 0.0 and move_y == 0.0:
        return

    fps = bge.logic.getAverageFrameRate()
    dt = 1.0 / fps if fps > 0 else (1.0 / 60.0)

    # local space movement: X = strafe, Y = forward/back, Z = 0 (no flying)
    dx = move_x * WALK_SPEED * dt
    dy = move_y * WALK_SPEED * dt

    obj.applyMovement((dx, dy, 0.0), True)


main()