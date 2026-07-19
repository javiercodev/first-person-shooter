import bge
import random
import aud

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

# --- footsteps ---
STEP_SOUND_NAMES = [
    "player_step_1.wav",
    "player_step_2.wav",
    "player_step_3.wav",
    "player_step_4.wav",
]
DEFAULT_STEP_INTERVAL = 0.45     # seconds between steps at WALK_SPEED
DEFAULT_STEP_PITCH_VARIATION = 0.04  # +/- pitch variation per step
DEFAULT_STEP_VOLUME = 1.0        # 0.0 (mute) - 1.0 (full volume), can be overridden with "step_volume"

# shared audio device and cached sound factories
_audio_device = aud.Device()
_step_factories_cache = {}


def get_step_factories(cont, obj):
    key = id(obj)
    factories = _step_factories_cache.get(key)
    if factories is None:
        factories = []
        for name in STEP_SOUND_NAMES:
            actuator = cont.actuators.get(name)
            if actuator is not None and actuator.sound is not None:
                factories.append(actuator.sound)
            else:
                print(
                    "[character_movement] Aviso: falta el actuador de sonido '{}' "
                    "en '{}' (o no tiene sonido asignado); se ignora.".format(
                        name, obj.name
                    )
                )
        _step_factories_cache[key] = factories
    return factories


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

    is_moving = move_x != 0.0 or move_y != 0.0

    if is_moving:
        fps = bge.logic.getAverageFrameRate()
        dt = 1.0 / fps if fps > 0 else (1.0 / 60.0)

        # local space movement: X = strafe, Y = forward/back, Z = 0 (no flying)
        dx = move_x * WALK_SPEED * dt
        dy = move_y * WALK_SPEED * dt

        obj.applyMovement((dx, dy, 0.0), True)

    # --- footsteps: only while actually moving, spaced by a time interval ---
    step_interval = obj.get("step_interval", DEFAULT_STEP_INTERVAL)
    if step_interval <= 0:
        step_interval = DEFAULT_STEP_INTERVAL  # guard against 0/negative

    step_volume = obj.get("step_volume", DEFAULT_STEP_VOLUME)
    # clamp to a sane 0.0-1.0 range in case of a bad game property value
    step_volume = max(0.0, min(1.0, step_volume))

    now = bge.logic.getRealTime()
    next_step_time = obj.get("next_step_time", 0.0)
    last_step_idx = obj.get("last_step_sound_idx", -1)

    if is_moving and now >= next_step_time:
        step_factories = get_step_factories(cont, obj)
        if step_factories:
            # avoid repeating the previous step sound
            choices = list(range(len(step_factories)))
            if last_step_idx in choices and len(choices) > 1:
                choices.remove(last_step_idx)
            idx = random.choice(choices)

            handle = _audio_device.play(step_factories[idx])
            if handle is not None:
                handle.pitch = 1.0 + random.uniform(
                    -DEFAULT_STEP_PITCH_VARIATION, DEFAULT_STEP_PITCH_VARIATION
                )
                handle.volume = step_volume

            last_step_idx = idx
        next_step_time = now + step_interval
    elif not is_moving:
        # stopped moving: next step should play right away when movement resumes
        next_step_time = now

    obj["next_step_time"] = next_step_time
    obj["last_step_sound_idx"] = last_step_idx
    obj["is_moving"] = is_moving  # exposed so other scripts (e.g. the weapon) can react to it
    obj["is_moving"] = is_moving  # exposed so other scripts (e.g. the weapon) can react to it


main()