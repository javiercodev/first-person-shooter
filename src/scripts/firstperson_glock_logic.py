import bge
import random
import aud
import math
import mathutils

ACTION_LAYER = 1  # matches the fire/reload action actuator layer -- HIGHER
                   # than WALK_LAYER on purpose, so fire/reload always shows
                   # through instead of being hidden by the walk-bob layer
WALK_LAYER = 0     # walk-bob animation, lower priority than fire/reload
WALK_INTRO_START = 0     # first startup when you begin walking (plays once)
WALK_INTRO_END = 258
WALK_LOOP_START = 20     # perfect loop while you keep walking
WALK_LOOP_END = 258
WALK_STOP_START = 265    # blendin interpolates your current pose into this frame
WALK_END_FRAME = 282     # final resting frame

FIRE_SOUND_NAMES = ["glock_fire_0.wav", "glock_fire_1.wav", "glock_fire_2.wav"]

# default weapon settings (can be overridden with game properties)
DEFAULT_FIRE_RATE = 100.0       # shots per second
DEFAULT_BLENDIN = 3             # animation blend frames
DEFAULT_PITCH_VARIATION = 0.03  # +/- pitch variation
DEFAULT_ANIM_SPEED = 1.5        # can be overridden with "fire_anim_speed"
DEFAULT_MAG_SIZE = 15           # shots per magazine before reload is required
DEFAULT_MUZZLE_NAME = "muzzle"  # can be overridden with "muzzle_object"
DEFAULT_WALK_BLENDIN = 3        # can be overridden with "walk_blendin"
DEFAULT_WALK_LOOP_BLENDIN = 10   # blendin applied on every loop wrap
                                 # (258 -> 20), can be overridden with
                                 # "walk_loop_blendin"
DEFAULT_WALK_STOP_BLEND = 10    # frames to smoothly interpolate into the
                                 # resting pose when you stop moving (can be
                                 # overridden with "walk_stop_blend")
DEFAULT_PLAYER_NAME = "player_object"  # can be overridden with "player_object"

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
                    "[firstperson_glock] Warning: missing sound actuator '{}' "
                    "on '{}' (or it has no sound assigned); skipping it.".format(
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
            "action_firstperson_glock_walk",
            "glock_reload.wav",
            "glock_dry_fire.wav",
        ],
    }
    missing = [n for n in required_names["sensors"] if n not in cont.sensors]
    missing += [n for n in required_names["actuators"] if n not in cont.actuators]
    if missing:
        if not obj.get("_firstperson_glock_warned", False):
            print(
                "[firstperson_glock] ERROR on '{}': missing sensors/actuators: {}. "
                "Check the names in the logic bricks.".format(
                    obj.name, ", ".join(missing)
                )
            )
            obj["_firstperson_glock_warned"] = True
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
    act_walk = cont.actuators["action_firstperson_glock_walk"]  # used only as a
    # container for the walk action name, same trick as the sound actuators
    sound_reload = cont.actuators["glock_reload.wav"]
    sound_dry_fire = cont.actuators["glock_dry_fire.wav"]

    # use sound actuators only as factory containers
    fire_factories = get_fire_factories(cont, obj)

    fire_rate = obj.get("fire_rate", DEFAULT_FIRE_RATE)
    if fire_rate <= 0:
        fire_rate = DEFAULT_FIRE_RATE  # guard against 0/negative -> ZeroDivisionError

    blendin = obj.get("fire_blendin", DEFAULT_BLENDIN)

    walk_blendin = obj.get("walk_blendin", DEFAULT_WALK_BLENDIN)
    walk_loop_blendin = obj.get("walk_loop_blendin", DEFAULT_WALK_LOOP_BLENDIN)
    walk_stop_blend = obj.get("walk_stop_blend", DEFAULT_WALK_STOP_BLEND)
    if walk_stop_blend < 0:
        walk_stop_blend = DEFAULT_WALK_STOP_BLEND  # guard against a negative value

    mag_size = obj.get("mag_size", DEFAULT_MAG_SIZE)
    if mag_size <= 0:
        mag_size = DEFAULT_MAG_SIZE  # guard against a broken/empty magazine setup

    # muzzle flash object: driven entirely from here so it only reacts to a
    # REAL shot, never to reload or an empty trigger pull
    muzzle_name = obj.get("muzzle_object", DEFAULT_MUZZLE_NAME)
    if not muzzle_name:  # property exists but is empty -> fall back to default
        muzzle_name = DEFAULT_MUZZLE_NAME
    scene = bge.logic.getCurrentScene()
    muzzle_obj = scene.objects.get(muzzle_name)
    if muzzle_obj is None and not obj.get("_muzzle_warned", False):
        print(
            "[firstperson_glock] Warning: muzzle object '{}' not found in the "
            "scene. The muzzle flash will not be shown.".format(muzzle_name)
        )
        obj["_muzzle_warned"] = True

    # player object: read its "is_moving" property (set by character_movement.py)
    # to know when to play/stop the walk-bob animation
    player_name = obj.get("player_object", DEFAULT_PLAYER_NAME)
    if not player_name:  # property exists but is empty -> fall back to default
        player_name = DEFAULT_PLAYER_NAME
    player_obj = scene.objects.get(player_name)
    if player_obj is None and not obj.get("_player_warned", False):
        print(
            "[firstperson_glock] Warning: player object '{}' not found in the "
            "scene. The walk animation will not play.".format(player_name)
        )
        obj["_player_warned"] = True
    is_moving = bool(player_obj.get("is_moving", False)) if player_obj is not None else False

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
    walk_was_moving = obj.get("walk_was_moving", False)

    # --- walk-bob animation (own layer, independent of fire/reload state) ---
    # While a shot is actively playing on ACTION_LAYER, we freeze the walk
    # layer completely instead of letting it keep looping underneath the
    # fire animation. Firing several times in a row while walking was
    # causing a visible "cut" every time the fire layer took over the same
    # bones the walk-bob was mid-motion on -- pausing walk while firing
    # removes that fight entirely, the gun just holds still during recoil.
    is_firing_active = obj.isPlayingAction(ACTION_LAYER)

    walk_action_name = act_walk.action
    if walk_action_name:
        if not obj.get("_walk_initialized", False):
            # force the resting pose (frame 282) right at game start, instead
            # of whatever raw bind/edit pose the armature had -- otherwise
            # the gun starts in a random pose until the first time you walk
            obj.playAction(
                walk_action_name,
                WALK_END_FRAME,
                WALK_END_FRAME,
                layer=WALK_LAYER,
                play_mode=bge.logic.KX_ACTION_MODE_PLAY,
                blendin=0,
            )
            obj["_walk_initialized"] = True

        if is_firing_active:
            # pause the walk-bob entirely while a shot/reload is playing on
            # top -- do NOT update walk_was_moving here, so that once firing
            # ends we correctly resume where we left off instead of
            # incorrectly triggering the "just stopped" blend
            obj.stopAction(WALK_LAYER)
        elif is_moving:
            if not walk_was_moving:
                # just started walking (from idle, or right after a burst of
                # firing) -- always begin with the intro segment
                obj["walk_sub_state"] = "intro"

            sub_state = obj.get("walk_sub_state", "intro")

            if sub_state == "intro":
                # plays once, 0 -> 258. calling this every frame while still
                # in "intro" is safe/idempotent, it just keeps advancing
                obj.playAction(
                    walk_action_name,
                    WALK_INTRO_START,
                    WALK_INTRO_END,
                    layer=WALK_LAYER,
                    play_mode=bge.logic.KX_ACTION_MODE_PLAY,
                    blendin=walk_blendin,
                )
                # frame 258's pose == frame 20's pose (that's what makes
                # 20-258 a perfect loop), so once we reach the end of the
                # intro we hand off to the loop segment
                if obj.getActionFrame(WALK_LAYER) >= WALK_INTRO_END - 0.5:
                    sub_state = "loop"
                    obj["walk_sub_state"] = "loop"
            else:
                # perfect loop, driven manually with a predictive crossfade:
                # instead of restarting exactly AT frame 258 (which blends
                # towards a target that's itself still advancing, feeling
                # like a little "catch-up" pop), we start the wrap
                # walk_loop_blendin frames BEFORE the end. That way the
                # blend finishes completing right around the moment the
                # timeline would have hit 258, so you never see a raw,
                # unblended frame at the seam -- much closer to a true
                # crossfade than a snap-and-blend.
                current_frame = obj.getActionFrame(WALK_LAYER)
                trigger_frame = WALK_LOOP_END - max(walk_loop_blendin, 1)
                needs_restart = (
                    not obj.isPlayingAction(WALK_LAYER)
                    or current_frame >= trigger_frame
                )
                if needs_restart:
                    obj.playAction(
                        walk_action_name,
                        WALK_LOOP_START,
                        WALK_LOOP_END,
                        layer=WALK_LAYER,
                        play_mode=bge.logic.KX_ACTION_MODE_PLAY,
                        blendin=walk_loop_blendin,
                    )

            walk_was_moving = is_moving
        elif walk_was_moving:
            # just stopped this frame: blendin smoothly interpolates from
            # whatever pose we were in (anywhere in the loop) into frame
            # WALK_STOP_START, then plays normally through to WALK_END_FRAME
            # to land on the resting pose
            obj.playAction(
                walk_action_name,
                WALK_STOP_START,
                WALK_END_FRAME,
                layer=WALK_LAYER,
                play_mode=bge.logic.KX_ACTION_MODE_PLAY,
                blendin=walk_stop_blend,
            )
            obj["walk_sub_state"] = "idle"
            walk_was_moving = is_moving
        else:
            # already stopped and settled -- do nothing
            walk_was_moving = is_moving

    # wait until reload animation ends
    if is_reloading and not obj.isPlayingAction(ACTION_LAYER):
        is_reloading = False
        ammo = mag_size  # magazine refilled once the reload finishes

    if not is_reloading:
        # allow reload any time, regardless of current ammo
        if reload_input:
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

        # NOTE: releasing the mouse/trigger no longer stops act_fire.
        # This is a semi-automatic weapon -- one press = one full shot
        # animation, regardless of how long the button stays held. Cutting
        # the animation short on release was causing visible pops/cuts,
        # especially noticeable while walking (Layer 0) since the fire
        # animation (Layer 1) would abort mid-recoil and snap back to the
        # walk-bob pose almost instantly after every shot.

    obj["is_reloading"] = is_reloading
    obj["next_fire_time"] = next_fire_time
    obj["last_fire_sound_idx"] = last_fire_idx
    obj["ammo"] = ammo
    obj["walk_was_moving"] = walk_was_moving


main()