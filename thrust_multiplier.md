# thrust_multiplier: what it is, whether 667 is right, what to change

Written 2026-10-05. Fix is tracked in Jira: USOIT-36, subtask of USOIT-11.

## Short version

- `thrust_multiplier` is not a thrust factor and not a tuning knob. It is the **rotor
  speed at full throttle in rad/s**. The Gazebo plugin needs it to turn ArduPilot's PWM
  into the rotor speed the motor model expects. It cannot be removed.
- Its value, 667, is the same number as the motor model's `max_rot_velocity`. Today the
  two are typed separately. That is the bad practice: one physical quantity, two places,
  a misleading name and a stale comment.
- The conversion works exactly as the code says (measured).
- Whether 667 is the right maximum was open until 2026-10-13. Closed: there is no
  physical kopterworx, the `MOT_THST_HOVER 0.290` in the parameter file came from a
  simulation, and the Noetic sim uses 667. Parity with Noetic is the only reference, so
  667 stays. See "Part B outcome".
- It never has to change for a ROS, Gazebo or firmware version. Only when the modelled
  motor, propeller or battery changes.

## What it is

```
ArduPilot SITL                Gazebo plugin (ArduPilotPlugin)             motor model (one per rotor)
motor output, PWM 1000..2000  raw = (pwm - servo_min)/(servo_max - servo_min)   ref = min(cmd, maxRotVelocity)
                       ---->  cmd = multiplier * (raw + offset)          ---->  thrust = motorConstant * speed^2
                              cmd is a rotor speed in rad/s
```

- Plugin code: `ArduPilotPlugin.cc`, `UpdateMotorCommands` (Harmonic, line 1708) and the
  same expression in the Classic fork (line 1163).
- Motor model: `gazebo_motor_model.cpp:131` on Classic (rotors_simulator),
  `MulticopterMotorModel.cc:537` on gz-sim 8. Both clamp the reference to
  `maxRotVelocity`.
- `<multiplier>` is the plugin's name. Every upstream model has one (iris: 838).
  `thrust_multiplier` is our name: an argument of the `ardupilot` xacro macro in
  `larics/ardupilot_gazebo`, `models/util/multirotor_base.urdf.xacro`, added in a4d3060
  (2020-04-24).
- Not to be confused with mavros `thrust_scaling`, which scales the thrust field of an
  AttitudeTarget inside mavros and has nothing to do with the model.

## Where 667 comes from

| quantity | value | source |
|---|---|---|
| `motor_constant` | 2.440724623743665e-04 N s^2 | reproducible: `motor_parameters/get_thrust_and_torque_k.m` on `22x8.mat` (APC 22x8 static data) gives 2.440724618e-04 |
| `moment_constant` | 0.044148079282817 m | same script, gives 0.0441480777 |
| `max_rot_velocity` | 667 rad/s (6370 rpm) | **not derived anywhere in the repo**, no motor, ESC or battery data |
| `thrust_multiplier` | 667 | copy of `max_rot_velocity` |

- Multiplier and `max_rot_velocity` are the same number in kopterworx (667/667), broli
  (667/667), hawk (628.318/628.318) and ardrone (1475/1475). Bebop is the one model
  where they drifted apart (1000 vs 1475).
- Both went from 600 to 667 in one commit, 7a39b49 (2022-12-05), together with the
  switch of the propeller table from APC 22x11E to 22x8.
- What 667 implies: 108.6 N (11.07 kgf) per motor at full throttle, thrust to weight
  4.9 for the 9 kg model. With 600 it is 87.9 N and 4.0.
- Detail on the script: it uses the quadratic coefficient of a full second order fit.
  A pure k w^2 fit of the same table gives 2.398e-4, 1.7 % lower. Not significant here.

## Measurements

PoC session `kopterworx_flat`, headless, clean SITL storage, 50 s hover at 3 m, ArduPilot
master, parameters `kopterworx_v432.params`. Model mass 9.05 kg (9 kg body, rotors,
sensor links), weight 88.78 N.

| multiplier | hover PWM (normalised) | rotor speed published by the plugin | 4 k w^2 | learned `MOT_THST_HOVER` |
|---|---|---|---|---|
| 667 (repo) | 1452 (0.452) | 301.48 rad/s | 88.74 N | 0.225 |
| 602 (scratch copy of the model) | 1501 (0.501) | 301.60 rad/s | 88.81 N | 0.275 |
| 600 (scratch copy, 2026-10-13) | 1502 (0.502) | 301.2 rad/s | 88.57 N | 0.2775 |

- 0.452 x 667 = 301.5 and 0.501 x 602 = 301.6. The plugin does what the code says.
- Thrust equals weight to 0.05 %. The motor model does what its constants say.
- The hover rotor speed is the same in both runs. The multiplier only decides which PWM
  produces it.
- `kopterworx_v432.params` carries `MOT_THST_HOVER` 0.290. On 2026-10-05 this was taken
  for a value learned on the real aircraft; it is not, it came from a simulation
  (2026-10-13). With 667 the simulation learns 0.225, 22 % lower. With 602 it learns
  0.275, 5 % lower.

So the simulated vehicle is stronger, or lighter, than whatever produced 0.290. Three
possible causes, not separable from the repo:

1. the real maximum rotor speed is lower than 667 rad/s (around 600 would fit),
2. the real take-off mass is above 9 kg,
3. the real thrust is below the APC static table.

Withdrawn 2026-10-13: there is no real aircraft to match, see "Part B outcome" below. 667 stays.

## What it affects

- **Hover throttle.** ArduPilot learns it (`MOT_HOVER_LEARN 2`), so the vehicle flies
  with either value.
- **Gain of the plant the rate loops see.** Thrust per unit of command at hover is 97.9 N
  at 667 and 88.4 N at 602, 10 % apart. The rate gains in the parameter file were tuned
  in simulation, at 667.
- **Thrust headroom.** 4.9 vs 4.0.
- **Not what the stack sends.** `kopterworx_v432.params` has `GUID_OPTIONS 0`. ArduPilot
  then reads the thrust of an AttitudeTarget as a climb rate, 0.5 means hold altitude
  (`GCS_MAVLink_Copter.cpp`, same on master and Larics-4.4.3). The multiplier does not
  move that. The xacro comment "Value is tuned in order for
  mavros/setpoint_raw/attitude/thrust to reflect real-world behavior" belongs to the
  older parameter sets with `GUID_OPTIONS 8` (thrust as thrust,
  `kopterworx_red_v41_thrust_compassless.params`), where the mavros thrust went straight
  to the motors. For the current parameters it is stale.

## When it has to change

- Only when the powertrain of the modelled aircraft changes: motor, propeller, battery
  voltage. Then together with `max_rot_velocity`, because it is the same quantity.
- Not for ROS 1 to ROS 2, Classic to Harmonic, or a firmware version. The port carried
  it over unchanged and the hover point matches the analytic value.
- If the two numbers diverge:
  - multiplier above `max_rot_velocity`: the motor model clamps, the top of the throttle
    range does nothing, ArduPilot does not know it is saturated;
  - multiplier below: the maximum is never reached and `max_rot_velocity` means nothing.

## What is wrong today

1. One physical quantity is typed in two places (`max_rot_velocity` in the base xacro,
   `thrust_multiplier` at the macro call). Bebop shows they drift.
2. The name says thrust. It is a rotor speed. It also gets mixed up with mavros
   `thrust_scaling`.
3. The comment says "tuned", which invites using it as a fudge factor. The right levers
   for matching a reference aircraft are the physical values: mass, motor constant,
   maximum rotor speed.
4. The value 667 has no recorded source.
5. USOIT-32 used to plan settling the value by comparing with the Noetic simulation.
   Noetic uses the same numbers, so that comparison checks the port, not the value.
   USOIT-32 was rewritten on 2026-10-08 to do exactly that: same hover throttle as Noetic.

## Fix

In `ardupilot_gazebo_description` (the ROS 2 package in uav_ros_simulation; Noetic
branches stay untouched):

1. The `ardupilot` macro takes `max_rot_velocity` instead of `thrust_multiplier`, and
   the kopterworx xacro passes `${max_rot_velocity}`, the property that already feeds
   the four motor models. One number, one place.
2. Comments say what it is: rotor speed at full throttle, rad/s.
3. ~~The value of `max_rot_velocity` is checked against the real aircraft~~ Dropped
   2026-10-13: there is no real aircraft. 667 stays, its origin (Noetic model, no
   hardware source) is written next to it. See "Part B outcome".

Step 1 and 2 change no behaviour. Step 3 would need one of these, should a physical
kopterworx exist one day:

- measured maximum rpm of the motor with the 22x8 propeller at full battery, or
- mean PWM of the four motors in a steady hover, from a flight log, with the take-off
  mass of that flight.

From the hover log: `max_rot_velocity = sqrt(m * 9.81 / (4 * motor_constant)) / p`, with
`p = (pwm - 1000) / 1000`. Example: 9 kg and 1500 give 601 rad/s.

The PoC generator `ros2_sitl/kopterworx_gz/scripts/gen_model.py` has the same two
constants (`MAX_ROT_VELOCITY`, `THRUST_MULTIPLIER`, both 667). It is reference material
and was left as it is.

## Part B outcome (2026-10-13): 667 stays

- There is no physical kopterworx. `MOT_THST_HOVER 0.290` in `kopterworx_v432.params`
  came from a simulation, not from a flight. So there is no hardware number to match,
  and "22 % lower than the real aircraft" above has no reference.
- The only reference left is the Noetic sim, the one the stack and its gains were
  developed on. It uses 667 with the same motor constant and mass: same plant. Changing
  the value would break that parity for nothing.
- Decision: `max_rot_velocity` stays 667. USOIT-36 is the rename only.
- Open, optional: where 0.290 came from. The Jazzy sim at 667 learns 0.225. One hover in
  the Noetic sim (`param show MOT_THST_HOVER` after a minute, or `mavros/rc/out`) tells
  whether the two sims agree. 0.225 there means the file value is stale. 0.290 there
  means the two sims differ for another reason (mass, Gazebo classic motor plugin), a
  parity item, not a multiplier item.

### Derivation kept for a future hardware number

The procedure, should a hover number from a physical aircraft ever exist. It was run on
2026-10-13 with the sim-derived 0.290 as input, so its result, 600, is **not applied**.

Input: take-off mass `m = 9 kg`. Constants: `k = 2.4407e-4 N s^2` (thrust per rotor `T = k w^2`), `g = 9.81`. Parameter file: `MOT_THST_EXPO e = 0.65`, `MOT_SPIN_MIN 0.13`, `MOT_SPIN_MAX 0.95`, `MOT_THST_HOVER 0.290`.

1. Rotor speed at hover, from the motor model. Independent of the multiplier.

    `w_h = sqrt(m g / (4 k)) = sqrt(9 * 9.81 / (4 * 2.4407e-4)) = 301 rad/s`

2. Motor output of the reference aircraft at hover. ArduPilot learns `MOT_THST_HOVER` in its linearised thrust domain and converts it to a 0..1 output with its thrust curve (`AP_Motors_Thrust_Linearization.cpp`, `thrust_to_actuator`):

    `r = ((e - 1) + sqrt((1 - e)^2 + 4 e T)) / (2 e) = (-0.35 + sqrt(0.1225 + 2.6 * 0.290)) / 1.3 = 0.451`

    `p = 0.13 + (0.95 - 0.13) * r = 0.500`, PWM 1500.

    Check on the PoC runs: `T = 0.225` gives `p = 0.440` (measured 0.452), `T = 0.275` gives `p = 0.487` (measured 0.501). Within 15 PWM.

3. The plugin sets the rotor speed as `w = p * max_rot_velocity`. At hover both sides must give `w_h`:

    `max_rot_velocity = w_h / p = 301 / 0.500 = 602`

4. Measured with 600 (`kopterworx_flat`, headless, clean storage, 50 s hover at 3 m):

    * mean motor output `p = 0.502`, PWM 1502
    * plugin rotor speed 301.2 rad/s, equal to `0.502 * 600` and to `w_h`
    * learned `MOT_THST_HOVER` 0.2775

    The learned value is below the input 0.290 because ArduPilot stores it corrected for air density (`get_compensation_gain`, `T_stored = T * rho / rho_0`) and SITL takes off at CMAC, 584 m above sea level, `rho / rho_0 = 0.945`. At the site: `T = 0.2775 / 0.945 = 0.294`. Equation 2 run forward from `p = 0.502` gives `T = 0.293`, so the two agree. Battery voltage plays no part: SITL reports none on `BATT_VOLT_PIN` 14, ArduPilot then uses `lift_max = 1`.

Thrust to weight at 600 would be `4 k (600)^2 / (m g) = 4.0` (4.9 with 667).

Measurement note: the PoC container is on the host network and Jazzy discovers the whole subnet by default, so a Jazzy simulation on another machine in the LAN appears on the same topics; the first run mixed two vehicles. Run gates with `ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST` (USOIT-49 puts it in the image).

## Modelling a UAV: which numbers, where they come from, how to update them

Everything the sim needs is in two files. In `ardupilot_gazebo_description` (after
USOIT-25) that is the vehicle's base xacro (`kopterworx_base.urdf.xacro`) and its
parameter file. In the PoC it is `kopterworx_gz/scripts/gen_model.py` (constants at the
top) and `config/kopterworx_v432.params`. Write the source of every number as a comment
next to it; a number without a source is the problem this document exists for.

### Gazebo model (xacro / `gen_model.py`)

| name | unit | kopterworx | source |
|---|---|---|---|
| `MASS`, `BODY_INERTIA` | kg, kg m^2 | 9.0, see file | take-off mass with battery and payload (scale), inertia from CAD or a bifilar pendulum. Inertia only shapes the rate response, mass sets hover. |
| `ARM`, rotor positions, `cw`/`ccw` | m | 0.52 at 45 deg | geometry. Order and spin direction must match `FRAME_TYPE` and the plugin channel mapping below. |
| `MOTOR_CONSTANT` k | N s^2 | 2.4407e-4 | static thrust table of motor + propeller: `polyfit(rad_s, thrust_N, 2)[0]` (`motor_parameters/22x8.mat`, see "Reproduce"). |
| `MOMENT_CONSTANT` | m | 0.0441 | same table: `polyfit(thrust_N, torque_Nm, 1)[0]`. Sets yaw authority. |
| `MAX_ROT_VELOCITY` = plugin `multiplier` | rad/s | 667 | rotor speed at full throttle, see "Updating `max_rot_velocity`" below. |
| `TIME_CONSTANT_UP/DOWN` | s | 0.0125 | motor + ESC step response. Leave unless measured. |
| `ROTOR_DRAG`, `ROLLING_MOMENT` | | 8.06e-5, 1e-6 | rotors_simulator defaults. Leave unless measured. |
| plugin `servo_min`/`servo_max` | PWM | 1000/2000 | must equal `MOT_PWM_MIN`/`MOT_PWM_MAX` in the parameter file; the 0..1 output is relative to these. |
| plugin `<control channel=N>` to joint | | 0,2,1,3 | ArduPilot motor numbering for `FRAME_CLASS`/`FRAME_TYPE` (quad X: 1 front right, 2 back left, 3 front left, 4 back right, channels are 0-based). Wrong mapping: the vehicle flips at take-off. |

### ArduPilot parameter file

| parameter | kopterworx | source |
|---|---|---|
| `FRAME_CLASS`, `FRAME_TYPE` | 1, 1 (quad X) | airframe. Must agree with the rotor table above. |
| `MOT_PWM_MIN/MAX` | 1000/2000 | ESC range; same numbers as plugin `servo_min/max`. |
| `MOT_SPIN_ARM/MIN/MAX` | 0.11/0.13/0.95 | ESC: lowest output that keeps the motors turning, highest usable. From the ESC or the ArduPilot motor-range setup. |
| `MOT_THST_EXPO` | 0.65 | thrust-vs-PWM curvature of motor + propeller. From the static thrust table (ArduPilot wiki "Motor thrust scaling"), 0.65 is the ArduPilot default for 20 to 30 in props. |
| `MOT_THST_HOVER`, `MOT_HOVER_LEARN` | 0.29, 2 | learned in flight, saved at disarm. Only the first flight uses the stored value. |
| `MOT_BAT_VOLT_MIN/MAX` | 9.9/12.6 | battery. No effect in SITL (no voltage on `BATT_VOLT_PIN` 14, `lift_max` = 1). |
| `ATC_*`, `PSC_*` gains | see file | tuned per vehicle. The sim's plant gain depends on k, mass and `max_rot_velocity`, so retune or re-check after changing any of them. |

### Updating `max_rot_velocity`

Pick by what data exists, best first.

1. **Thrust stand data for motor + propeller at full battery** (thrust and torque vs rpm,
   max rpm). Set k and `MOMENT_CONSTANT` from the fit and `max_rot_velocity` to the max
   rpm converted to rad/s (`rpm * 2 pi / 60`). Fit `MOT_THST_EXPO` from the same table.
   Nothing is derived from a hover.
2. **A hover from the physical aircraft** (hover PWM from a log, or learned
   `MOT_THST_HOVER`, plus take-off mass). Keep k, use the four equations in "Derivation
   kept for a future hardware number": `w_h = sqrt(m g / (4 k))`, `p` from the thrust
   curve (or `p = (pwm - MOT_PWM_MIN) / (MOT_PWM_MAX - MOT_PWM_MIN)` directly from the
   log), `max_rot_velocity = w_h / p`. Limitation: a hover fixes only the product of k
   and `max_rot_velocity^2`; the full-throttle thrust, and so the thrust-to-weight ratio
   and climb performance, stay unverified without a second point (max climb rate or
   stand data).
3. **Motor KV and battery cell count only.** `max_rot_velocity` is roughly
   `0.8 * KV * V_pack * 2 pi / 60` (loaded rpm is 15 to 25 % below no-load). Mark it as an
   estimate.
4. **Nothing.** Keep the Noetic number (667). Do not tune it to make a controller behave.

Sanity checks after any change, before flying:

- hover output `p = sqrt(m g / (4 k)) / max_rot_velocity` must lie between `MOT_SPIN_MIN`
  and about 0.6; outside that ArduPilot either cannot hover or has no headroom.
- thrust to weight `4 k max_rot_velocity^2 / (m g)` between 2 and 5 for a multirotor.

Flight check: "Reproduce" below. The mean normalised output must equal the predicted `p`
within 0.02, and the learned `MOT_THST_HOVER` must give `p` back through the thrust
curve after dividing by 0.945 (air density at the 584 m SITL home).

## Reproduce

Inside the container (`ros2_sitl/docker_run.sh -d`, then `ros2_sitl/docker_run.sh`):

```bash
# clean SITL storage, otherwise the learned hover value of the last run is loaded
mv /root/ros2_sitl/logs/sitl_kopterworx/eeprom.bin /tmp/ 2>/dev/null
cd /root/ros2_sitl/startup/kopterworx_flat && GUI=false HEADLESS=true ./start.sh --no-attach
source /root/ros2_sitl/startup/shell_helpers.sh && waitForArmable
python3 /root/ros2_sitl/scripts/hover_test.py --hover-s 50 &     # prints the mean normalised motor output
sleep 50; gz topic -e -n 1 -t /kopterworx/command/motor_speed    # rotor speed the plugin publishes, rad/s
wait
ros2 service call /mavros/param/pull mavros_msgs/srv/ParamPull "{force_pull: true}"
ros2 param get /mavros/param MOT_THST_HOVER                      # learned value, saved at disarm
/root/ros2_sitl/kill_sim.sh
```

Motor constants: load `motor_parameters/22x8.mat` from `larics/ardupilot_gazebo`
(`rpm`, `thrust_lbf`, `torque_lbf`), convert to rad/s, N and Nm, then
`polyfit(rad_s, thrust, 2)[0]` and `polyfit(thrust, torque, 1)[0]`.

## Jira

USOIT-36 "5a. Kopterworx model: replace thrust_multiplier with max_rot_velocity", subtask
of USOIT-11. The rename only, no behaviour change. Part B (the value) was dropped on
2026-10-13: 667 stays, there is no real aircraft. USOIT-25 item 4 ("multiplier 667")
remains correct. USOIT-32 no longer mentions the value.
