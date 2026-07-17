import bge
import random
import aud
import math
import mathutils

ACTION_LAYER = 0  # matches the action actuator layer
FIRE_SOUND_NAMES = ["glock_fire_0.wav", "glock_fire_1.wav", "glock_fire_2.wav"]

# default weapon settings (can be overridden with game properties)
DEFAULT_FIRE_RATE = 100.0         # shots per second
DEFAULT_BLENDIN = 3             # animation blend frames
DEFAULT_PITCH_VARIATION = 0.03  # +/- pitch variation
DEFAULT_ANIM_SPEED = 1.5        # can be overridden with "fire_anim_speed"
DEFAULT_MAG_SIZE = 15           # shots per magazine before reload is required
DEFAULT_MUZZLE_NAME = "muzzle"  # can be overridden with "muzzle_object"

# shared audio device and cached sound factories
_audio_device = aud.Device()
_fire_factories_cache = {}
_muzzle_base_orientation_cache = {}


def get_muzzle_base_orientation(muzzle_obj):
    """Capture the muzzle's original resting orientation the first time
    we see it, so later spins can be applied on TOP of it instead of
    overwriting it (which was making the plane face edge-on / disappear)."""
    key = id(muzzle_obj)
    base = _muzzle_base_orientation_cache.get(key)
    if base is None:
        base = muzzle_obj.localOrientation.copy()
        _muzzle_base_orientation_cache[key] = base
    return base


def get_fire_factories(cont, obj):
    key = id(obj)
    factories = _fire_factories_cache.get(key)
    if factories is None:
        factories = []
        for name in FIRE_SOUND_NAMES:
            actuator = cont.actuators.get(name)
            if actuator is not None and actuator.sound is not None:
                factories.append(actuator.sound)
            else:
                print(
                    "[weapon_fire] Aviso: falta el actuador de sonido '{}' "
                    "en '{}' (o no tiene sonido asignado); se ignora.".format(
                        name, obj.name
                    )
                )
        _fire_factories_cache[key] = factories
    return factories


def main():
    cont = bge.logic.getCurrentController()
    obj = cont.owner

    # --- required sensors/actuators: fail loudly once instead of crashing
    # every single frame if a name is missing or misspelled in the logic bricks
    required_names = {
        "sensors": ["mouse_fire", "joystick_fire", "keyboard_reload", "joystick_reload"],
        "actuators": [
            "action_firstperson_glock_shot",
            "action_firstperson_glock_reload_t",
            "glock_reload.wav",
            "glock_dry_fire.wav",
        ],
    }
    missing = [n for n in required_names["sensors"] if n not in cont.sensors]
    missing += [n for n in required_names["actuators"] if n not in cont.actuators]
    if missing:
        if not obj.get("_weapon_fire_warned", False):
            print(
                "[weapon_fire] ERROR en '{}': faltan sensores/actuadores: {}. "
                "Revisa los nombres en los ladrillos lógicos.".format(
                    obj.name, ", ".join(missing)
                )
            )
            obj["_weapon_fire_warned"] = True
        return  # abort this frame safely, nothing to do without these

    # input
    fire_held = cont.sensors["mouse_fire"].positive or cont.sensors["joystick_fire"].positive
    reload_input = cont.sensors["keyboard_reload"].positive or cont.sensors["joystick_reload"].positive

    # semi-automatic fire: only a fresh press (rising edge) counts as a shot,
    # holding the button/trigger down does NOT keep firing
    fire_was_held = obj.get("fire_was_held", False)
    fire_pressed = fire_held and not fire_was_held
    obj["fire_was_held"] = fire_held

    # actuators
    act_fire = cont.actuators["action_firstperson_glock_shot"]
    act_reload = cont.actuators["action_firstperson_glock_reload_t"]
    sound_reload = cont.actuators["glock_reload.wav"]
    sound_dry_fire = cont.actuators["glock_dry_fire.wav"]

    # use sound actuators only as factory containers
    fire_factories = get_fire_factories(cont, obj)

    fire_rate = obj.get("fire_rate", DEFAULT_FIRE_RATE)
    if fire_rate <= 0:
        fire_rate = DEFAULT_FIRE_RATE  # guard against 0/negative -> ZeroDivisionError

    blendin = obj.get("fire_blendin", DEFAULT_BLENDIN)

    mag_size = obj.get("mag_size", DEFAULT_MAG_SIZE)
    if mag_size <= 0:
        mag_size = DEFAULT_MAG_SIZE  # guard against a broken/empty magazine setup

    # muzzle flash object: driven entirely from here so it only reacts to a
    # REAL shot, never to reload or an empty trigger pull
    muzzle_name = obj.get("muzzle_object", DEFAULT_MUZZLE_NAME)
    scene = bge.logic.getCurrentScene()
    muzzle_obj = scene.objects.get(muzzle_name)
    if muzzle_obj is None and not obj.get("_muzzle_warned", False):
        print(
            "[weapon_fire] Aviso: no se encontró el objeto muzzle '{}' en la "
            "escena. El destello de disparo no se mostrará.".format(muzzle_name)
        )
        obj["_muzzle_warned"] = True

    # smooth animation restart
    try:
        act_fire.blendin = blendin
    except AttributeError:
        pass

    now = bge.logic.getRealTime()

    # persistent state
    is_reloading = obj.get("is_reloading", False)
    next_fire_time = obj.get("next_fire_time", 0.0)
    last_fire_idx = obj.get("last_fire_sound_idx", -1)
    ammo = obj.get("ammo", mag_size)  # first run: magazine starts full

    # wait until reload animation ends
    if is_reloading and not obj.isPlayingAction(ACTION_LAYER):
        is_reloading = False
        ammo = mag_size  # magazine refilled once the reload finishes

    if not is_reloading:
        # allow reload any time it's not already full, or forced by the player
        if reload_input and ammo < mag_size:
            is_reloading = True
            cont.activate(act_reload)
            cont.activate(sound_reload)
            cont.deactivate(act_fire)
            # reset cooldown after reload
            next_fire_time = now

        elif (
            fire_pressed
            and ammo > 0
            and now >= next_fire_time
            and not obj.isPlayingAction(ACTION_LAYER)
        ):
            # a single fresh press = a single shot (semi-automatic).
            # isPlayingAction() blocks a new shot until the previous fire
            # animation has fully finished, so mashing the button faster
            # than the weapon can physically cycle has no effect
            cont.activate(act_fire)

            # play a random shot sound, but only if at least one is available
            # (fire_factories could be empty if the sound actuators were
            # misconfigured -- see the warning printed by get_fire_factories)
            if fire_factories:
                # avoid repeating the previous sound
                choices = list(range(len(fire_factories)))
                if last_fire_idx in choices and len(choices) > 1:
                    choices.remove(last_fire_idx)
                idx = random.choice(choices)

                # aud allows overlapping shot sounds
                handle = _audio_device.play(fire_factories[idx])
                if handle is not None:
                    handle.pitch = 1.0 + random.uniform(
                        -DEFAULT_PITCH_VARIATION, DEFAULT_PITCH_VARIATION
                    )

                last_fire_idx = idx
            next_fire_time = now + (1.0 / fire_rate)
            ammo -= 1  # consume one round per shot

            # muzzle flash: random spin around its own face-normal axis +
            # trigger its animation. Only reached on a confirmed, successful
            # shot. The rotation axis is configurable because it depends on
            # how the muzzle plane's local axes are oriented -- rotating
            # around an axis that lies IN the plane (instead of perpendicular
            # to its face) makes it look like a door swinging/foreshortening
            # instead of spinning flat. Default "Z" matches a standard
            # Blender plane, whose local normal is +Z.
            if muzzle_obj is not None:
                axis = str(obj.get("muzzle_rotation_axis", "Z")).upper()
                if axis not in ("X", "Y", "Z"):
                    axis = "Z"
                angle = random.uniform(0.0, 2.0 * math.pi)
                base_orn = get_muzzle_base_orientation(muzzle_obj)
                spin = mathutils.Matrix.Rotation(angle, 3, axis)
                # apply the spin ON TOP of the muzzle's original resting
                # orientation, instead of replacing it -- this keeps it
                # facing the right way instead of going edge-on/invisible
                muzzle_obj.localOrientation = base_orn @ spin
                # toggle a bool property; the muzzle's own Property sensor
                # (evaluation type "Changed") fires exactly once per toggle,
                # so this reliably pulses the muzzle's Action actuator
                muzzle_obj["fire_trigger"] = not muzzle_obj.get("fire_trigger", False)

        elif fire_pressed and ammo <= 0:
            # empty magazine: play a dry-fire click instead of a shot,
            # no animation, no ammo consumed, no fire cooldown started
            cont.activate(sound_dry_fire)

        elif not fire_held:
            # trigger released: stop the firing animation
            cont.deactivate(act_fire)

    obj["is_reloading"] = is_reloading
    obj["next_fire_time"] = next_fire_time
    obj["last_fire_sound_idx"] = last_fire_idx
    obj["ammo"] = ammo


main()