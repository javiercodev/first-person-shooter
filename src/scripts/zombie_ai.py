import bge
import mathutils
import math

# CONFIGURATION
ACTION_LAYER = 0  # single animation layer for this zombie (idle and run take turns here)
IDLE_ACTION = "action_zombie_idle"
IDLE_START = 0
IDLE_END = 240
RUN_ACTION = "action_zombie_run"
RUN_START = 0
RUN_END = 48
DEFAULT_PLAYER_NAME = "firstperson_character"  # can be overridden with "player_object"
DEFAULT_DETECTION_RADIUS = 15.0                 # can be overridden with "detection_radius"
DEFAULT_BLENDIN = 8                             # blend frames when switching animation,
                                                  # can be overridden with "zombie_blendin"
DEFAULT_SPEED = 3.0                             # units/sec, can be overridden with "zombie_speed"
DEFAULT_TURN_FACTOR = 0.15                      # smoothness when turning toward the player (0-1),
                                                  # can be overridden with "zombie_turn_factor"

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
# notices them if they get within a much shorter "rear" distance -
# simulating that the zombie can't see behind itself but can still sense
# something very close.
DEFAULT_FOV_ANGLE = 120.0            # degrees, full cone width in front of the zombie,
                                       # can be overridden with "zombie_fov_angle"
DEFAULT_REAR_DETECTION_RADIUS = 3.0  # distance at which the zombie notices the player
                                       # even from behind/outside the fov cone,
                                       # can be overridden with "zombie_rear_detection_radius"


def main():
    cont = bge.logic.getCurrentController()
    obj = cont.owner
    scene = bge.logic.getCurrentScene()

    # ---- configuration read from game properties (with default values) ----
    player_name = obj.get("player_object", DEFAULT_PLAYER_NAME)
    if not player_name:
        player_name = DEFAULT_PLAYER_NAME

    detection_radius = obj.get("detection_radius", DEFAULT_DETECTION_RADIUS)
    if detection_radius <= 0:
        detection_radius = DEFAULT_DETECTION_RADIUS

    blendin = obj.get("zombie_blendin", DEFAULT_BLENDIN)
    speed = obj.get("zombie_speed", DEFAULT_SPEED)
    turn_factor = obj.get("zombie_turn_factor", DEFAULT_TURN_FACTOR)
    fov_angle = obj.get("zombie_fov_angle", DEFAULT_FOV_ANGLE)
    rear_detection_radius = obj.get("zombie_rear_detection_radius", DEFAULT_REAR_DETECTION_RADIUS)

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
    target_state = "run" if player_detected else "idle"

    # ---- only trigger a new animation if the state actually changed ----
    current_state = obj.get("zombie_state", None)
    if current_state != target_state:
        if target_state == "run":
            obj.playAction(
                RUN_ACTION,
                RUN_START,
                RUN_END,
                layer=ACTION_LAYER,
                play_mode=bge.logic.KX_ACTION_MODE_LOOP,
                blendin=blendin,
            )
        else:
            obj.playAction(
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
    # benefit) to call playaction again every frame.

    # ---- chase: move and orient the zombie toward the player ----
    if player_detected:
        dt = 1.0 / bge.logic.getLogicTicRate()

        direction = player_obj.worldPosition - obj.worldPosition
        direction.z = 0.0  # we don't want the zombie to "fly" or sink while chasing on z

        dist_xy = direction.length
        if dist_xy > 0.001:
            direction.normalize()

            # move on the horizontal plane, in world space (false = not local)
            obj.applyMovement(
                (direction.x * speed * dt, direction.y * speed * dt, 0.0),
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