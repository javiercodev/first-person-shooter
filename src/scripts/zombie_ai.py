import bge
import mathutils
import math
import random

# CONFIGURATION
ACTION_LAYER = 0  # single animation layer for this zombie (idle, run and
                   # punch all share this layer, they never overlap)

# ---- base animations ----
IDLE_ACTION = "action_zombie_idle"
IDLE_START = 0
IDLE_END = 240

RUN_ACTION = "action_zombie_run"
RUN_START = 0
RUN_END = 48

# ---- attack animations ----
# Two punch animations that are chosen randomly at the start of each attack
# sequence. While the zombie is in contact with the player, it loops the
# selected animation a random number of times before picking a new one.
PUNCH_1_ACTION = "action_zombie_punching"
PUNCH_1_START = 0
PUNCH_1_END = 231
PUNCH_1_CANCEL_FRAME = 125  # if the player moves away before this frame,
                             # the punch is locked and cannot cancel --
                             # prevents the zombie from popping out of the
                             # animation too early and looking broken

PUNCH_2_ACTION = "action_zombie_attack"
PUNCH_2_START = 0
PUNCH_2_END = 278
PUNCH_2_CANCEL_FRAME = 160

# ---- random loop configuration ----
# Minimum and maximum consecutive loops for the same attack animation.
# The zombie will loop the randomly selected punch 1 to 3 times before
# reconsidering its state (or earlier if the player moves out of contact).
MIN_LOOPS = 1
MAX_LOOPS = 3

# ---- detection and movement ----
DEFAULT_PLAYER_NAME = "firstperson_character"  # can be overridden with
                                                # "player_object"
DEFAULT_ANIM_OBJECT_NAME = "zombie_smoke"     # the mesh/object that receives
                                                # playAction calls; can be
                                                # overridden with
                                                # "zombie_anim_object"
DEFAULT_DETECTION_RADIUS = 15.0               # can be overridden with
                                                # "detection_radius"
DEFAULT_BLENDIN = 8                           # blend frames when switching
                                                # animation, can be overridden
                                                # with "zombie_blendin"
DEFAULT_SPEED = 3.0                           # units/sec, can be overridden
                                                # with "zombie_speed"
DEFAULT_TURN_FACTOR = 0.15                    # smoothness when turning toward
                                                # the player (0-1), can be
                                                # overridden with
                                                # "zombie_turn_factor"
DEFAULT_PUNCH_RADIUS = 1.2                    # distance at which the zombie is
                                                # considered to be "in contact"
                                                # with the player and starts
                                                # punching, can be overridden
                                                # with "zombie_punch_radius"
DEFAULT_PUNCH_SPEED_MULTIPLIER = 0.0          # fraction of the normal speed
                                                # used while punching (0.0 =
                                                # frozen in place, 1.0 = same
                                                # speed as running).
                                                # IMPORTANT: keep this at 0.0
                                                # (or very close to it). any
                                                # noticeable value makes the
                                                # zombie keep pushing forward
                                                # into the player's collider
                                                # while already in contact,
                                                # which the physics engine
                                                # resolves as a constant
                                                # shove/counter-shove -> the
                                                # "stuck together" feeling.
                                                # 0.0 avoids that entirely
                                                # while still turning to face
                                                # the player. can be overridden
                                                # with
                                                # "zombie_punch_speed_multiplier"

# ---- orientation calibration ----
# instead of trying to guess which local axis of the model is "forward" and
# which is "up" (which depends on how the character was exported/rigged and
# is very easy to get wrong), we rotate only in yaw (around the global z
# axis). this makes it impossible for the zombie to end up lying down,
# face up or face down: its pitch/roll is never touched, only where it
# "looks" is.
#
# front_offset_deg is the only value that needs manual calibration: it's
# the angle (in degrees) that must be added so that "yaw = 0" matches the
# direction the model actually faces in its rest pose.
# if the zombie chases correctly but looks toward the wrong side, try
# 90, 180 or -90 (it's usually one of those 4 values).
FRONT_OFFSET_DEG = 90.0

# ---- field of view (fov) ----
# if the player is behind the zombie (outside its field of view), it
# shouldn't notice them at the full detection_radius. instead, it only
# notices them if they get within a much shorter "rear" distance --
# simulating that the zombie can't see behind itself but can still sense
# something very close.
DEFAULT_FOV_ANGLE = 120.0            # degrees, full cone width in front of the
                                      # zombie, can be overridden with
                                      # "zombie_fov_angle"
DEFAULT_REAR_DETECTION_RADIUS = 3.0  # distance at which the zombie notices the
                                      # player even from behind/outside the fov
                                      # cone, can be overridden with
                                      # "zombie_rear_detection_radius"



# HELPER FUNCTIONS
def get_frame_duration(start_frame, end_frame, blendin, logic_tic_rate):
    """Calculates the duration in seconds for an animation frame range."""
    return (abs(end_frame - start_frame) + blendin) / logic_tic_rate


def pick_new_attack():
    """
    Randomly selects an attack animation and a number of loops.
    Returns a dictionary with the attack configuration.
    """
    if random.choice([True, False]):
        action = PUNCH_1_ACTION
        start = PUNCH_1_START
        end = PUNCH_1_END
        cancel_frame = PUNCH_1_CANCEL_FRAME
    else:
        action = PUNCH_2_ACTION
        start = PUNCH_2_START
        end = PUNCH_2_END
        cancel_frame = PUNCH_2_CANCEL_FRAME
    
    total_loops = random.randint(MIN_LOOPS, MAX_LOOPS)
    
    return {
        "action": action,
        "start": start,
        "end": end,
        "cancel_frame": cancel_frame,
        "total_loops": total_loops,
        "current_loop": 0,
    }



# MAIN
def main():
    cont = bge.logic.getCurrentController()
    # obj is now the LOGIC/MOVEMENT object (zombie_smoke_character):
    # it is the one that moves, turns and detects the player. The Python
    # controller must be placed on this object.
    obj = cont.owner
    scene = bge.logic.getCurrentScene()
    logic_tic_rate = bge.logic.getLogicTicRate()

    # ---- configuration read from game properties (with default values) ----
    player_name = obj.get("player_object", DEFAULT_PLAYER_NAME)
    if not player_name:
        player_name = DEFAULT_PLAYER_NAME

    anim_object_name = obj.get("zombie_anim_object", DEFAULT_ANIM_OBJECT_NAME)
    if not anim_object_name:
        anim_object_name = DEFAULT_ANIM_OBJECT_NAME

    detection_radius = obj.get("detection_radius", DEFAULT_DETECTION_RADIUS)
    if detection_radius <= 0:
        detection_radius = DEFAULT_DETECTION_RADIUS

    blendin = obj.get("zombie_blendin", DEFAULT_BLENDIN)
    speed = obj.get("zombie_speed", DEFAULT_SPEED)
    turn_factor = obj.get("zombie_turn_factor", DEFAULT_TURN_FACTOR)
    fov_angle = obj.get("zombie_fov_angle", DEFAULT_FOV_ANGLE)
    rear_detection_radius = obj.get("zombie_rear_detection_radius", DEFAULT_REAR_DETECTION_RADIUS)
    punch_radius = obj.get("zombie_punch_radius", DEFAULT_PUNCH_RADIUS)
    punch_speed_multiplier = obj.get("zombie_punch_speed_multiplier", DEFAULT_PUNCH_SPEED_MULTIPLIER)

    # ---- locate the player ----
    player_obj = scene.objects.get(player_name)
    if player_obj is None:
        if not obj.get("_player_warned", False):
            print(
                "[zombie_ai] Warning: player object '{}' not found in the "
                "scene. The zombie will stay idle forever.".format(player_name)
            )
            obj["_player_warned"] = True
        return

    # ---- locate the animation object ----
    # the object that actually receives playAction (zombie_smoke) can be
    # different from the one that moves and detects the player
    # (zombie_smoke_character). this is useful, for example, when the
    # animated mesh is a separate child or a different object linked by
    # name, instead of being the owner itself.
    anim_obj = scene.objects.get(anim_object_name)
    if anim_obj is None:
        if not obj.get("_anim_obj_warned", False):
            print(
                "[zombie_ai] Warning: animation object '{}' not found in "
                "the scene. The zombie will move but won't play any "
                "animation.".format(anim_object_name)
            )
            obj["_anim_obj_warned"] = True
        anim_obj = None

    # ---- direction/distance toward the player (needed both for fov and movement) ----
    distance = obj.getDistanceTo(player_obj)
    direction = player_obj.worldPosition - obj.worldPosition
    direction.z = 0.0  # we don't want the zombie to "fly" or sink while chasing on z
    dist_xy = direction.length
    if dist_xy > 0.001:
        direction.normalize()

    # ---- field of view check ----
    # the zombie's actual facing angle in world space is its current yaw
    # minus the calibration offset (see front_offset_deg above).
    front_offset_rad = math.radians(FRONT_OFFSET_DEG)
    current_yaw = obj.worldOrientation.to_euler().z
    facing_angle = current_yaw - front_offset_rad

    if dist_xy > 0.001:
        angle_to_player = math.atan2(direction.y, direction.x)
        angle_diff = abs((angle_to_player - facing_angle + math.pi) % (2 * math.pi) - math.pi)
    else:
        angle_diff = 0.0  # player is basically on top of the zombie, no meaningful angle

    in_fov = angle_diff <= math.radians(fov_angle) / 2.0

    # ---- distance-based detection, limited by field of view ----
    effective_radius = detection_radius if in_fov else rear_detection_radius
    player_detected = distance <= effective_radius

    # ---- contact/collision detection ----
    # we prefer a real collision sensor (more reliable than an eyeball
    # distance, because it respects the actual shape/size of the colliders).
    # if the "PlayerTouch" sensor exists and is connected to the controller,
    # we use it; otherwise we fall back to the distance threshold as an
    # approximation.
    touch_sensor = cont.sensors.get("PlayerTouch")
    if touch_sensor is not None:
        in_contact = touch_sensor.positive
    else:
        in_contact = distance <= punch_radius
        if not obj.get("_touch_sensor_warned", False):
            connected_names = [s.name for s in cont.sensors]
            print(
                "[zombie_ai] Warning: collision sensor 'PlayerTouch' not "
                "found connected to the controller. Actually connected "
                "sensors: {}. Falling back to distance detection "
                "(punch_radius) as a backup, less precise than a real "
                "collision sensor.".format(connected_names)
            )
            obj["_touch_sensor_warned"] = True

    # ---- state logic ----
    current_state = obj.get("zombie_state", None)
    punch_start_time = obj.get("_punch_start_time", 0.0)
    now = bge.logic.getRealTime()

    if current_state == "punch":
        # get current attack configuration
        atk = obj.get("_attack_config", None)
        if atk is None:
            # safety fallback - should not happen
            atk = pick_new_attack()
            obj["_attack_config"] = atk
        
        # durations for this specific attack
        cancel_duration = get_frame_duration(atk["start"], atk["cancel_frame"], blendin, logic_tic_rate)
        full_duration = get_frame_duration(atk["start"], atk["end"], blendin, logic_tic_rate)
        
        time_punching = now - punch_start_time
        
        past_cancel_point = time_punching >= cancel_duration
        past_full_anim = time_punching >= full_duration
        
        if not past_cancel_point:
            # before cancel frame: locked into the punch
            target_state = "punch"
            
        elif not past_full_anim:
            # between cancel frame and end: decide based on distance
            if in_contact:
                target_state = "punch"
            else:
                if player_detected:
                    target_state = "run"
                else:
                    target_state = "idle"
                    
        else:
            # one loop finished
            atk["current_loop"] += 1
            
            if in_contact and atk["current_loop"] < atk["total_loops"]:
                # more loops pending, player still in contact
                obj["_punch_start_time"] = now
                target_state = "punch"
                # replay same animation for the next loop
                if anim_obj is not None:
                    anim_obj.playAction(
                        atk["action"],
                        atk["start"],
                        atk["end"],
                        layer=ACTION_LAYER,
                        play_mode=bge.logic.KX_ACTION_MODE_LOOP,
                        blendin=blendin,
                    )
            else:
                # all loops done or player moved away
                # clear config so next attack picks a new random animation
                obj["_attack_config"] = None
                
                if in_contact:
                    # player still in contact: NEW attack with NEW random animation
                    target_state = "punch"
                    obj["_punch_start_time"] = now
                    obj["_attack_config"] = pick_new_attack()
                elif player_detected:
                    target_state = "run"
                else:
                    target_state = "idle"
                    
    else:
        # not punching: normal decision
        if in_contact:
            target_state = "punch"
            obj["_punch_start_time"] = now
            # new attack: pick random animation
            obj["_attack_config"] = pick_new_attack()
        elif player_detected:
            target_state = "run"
        else:
            target_state = "idle"

    # ---- only trigger a new animation if the state actually changed ----
    # the state is still stored on obj (the logic object), but the
    # animation itself is played on anim_obj (zombie_smoke).
    if current_state != target_state:
        if anim_obj is not None:
            if target_state == "punch":
                atk = obj.get("_attack_config")
                if atk is None:
                    atk = pick_new_attack()
                    obj["_attack_config"] = atk
                anim_obj.playAction(
                    atk["action"],
                    atk["start"],
                    atk["end"],
                    layer=ACTION_LAYER,
                    play_mode=bge.logic.KX_ACTION_MODE_LOOP,
                    blendin=blendin,
                )
            elif target_state == "run":
                anim_obj.playAction(
                    RUN_ACTION,
                    RUN_START,
                    RUN_END,
                    layer=ACTION_LAYER,
                    play_mode=bge.logic.KX_ACTION_MODE_LOOP,
                    blendin=blendin,
                )
            else:
                anim_obj.playAction(
                    IDLE_ACTION,
                    IDLE_START,
                    IDLE_END,
                    layer=ACTION_LAYER,
                    play_mode=bge.logic.KX_ACTION_MODE_LOOP,
                    blendin=blendin,
                )
        obj["zombie_state"] = target_state
    # if the state didn't change, we do nothing: upbge's native loop already
    # keeps playing the current animation on its own, no need (and no
    # benefit) to call playAction again every frame.

    # ---- chase: move and orient the zombie toward the player ----
    # movement and turning are still applied to obj
    # (zombie_smoke_character), not on anim_obj.
    if player_detected:
        dt = 1.0 / logic_tic_rate

        direction = player_obj.worldPosition - obj.worldPosition
        direction.z = 0.0  # we don't want the zombie to "fly" or sink while chasing on z

        dist_xy = direction.length
        if dist_xy > 0.001:
            direction.normalize()

            # while punching, move much slower instead of being completely
            # frozen: this gives the player a real window to escape while
            # the animation lasts, without the zombie looking like a statue
            # nailed to the spot.
            effective_speed = speed
            if target_state == "punch":
                effective_speed = speed * punch_speed_multiplier

            # move on the horizontal plane, in world space (false = not local)
            obj.applyMovement(
                (direction.x * effective_speed * dt, direction.y * effective_speed * dt, 0.0),
                False,
            )

            # smoothly turn the model to "look" toward the player,
            # only in yaw (rotation around the global z axis). we never
            # touch pitch/roll, so the zombie can't end up lying down or
            # face up/down, regardless of the mesh's local axis orientation.
            target_yaw = math.atan2(direction.y, direction.x) + math.radians(FRONT_OFFSET_DEG)

            current_yaw = obj.worldOrientation.to_euler().z
            diff = (target_yaw - current_yaw + math.pi) % (2 * math.pi) - math.pi
            new_yaw = current_yaw + diff * turn_factor

            euler = obj.worldOrientation.to_euler()
            euler.z = new_yaw
            obj.worldOrientation = euler


main()