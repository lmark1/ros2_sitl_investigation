"""Arming helper shared by the test scripts."""
import time

import rclpy
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from mavros_msgs.msg import StatusText
from mavros_msgs.srv import CommandBool


def arm_with_retry(node, arm_cli, is_armed, timeout=60.0, period=3.0):
    """Arm, retrying until the autopilot accepts.

    ArduPilot refuses to arm for a while after boot (simulated IMUs settling: "Accels
    inconsistent", EKF without a position in GUIDED: "Need Position Estimate"). That is
    normal, so retry every `period` seconds for up to `timeout` seconds and print the
    autopilot's own reason for each refusal. Returns True when armed.
    """
    reasons = []
    qos = QoSProfile(depth=20, reliability=ReliabilityPolicy.BEST_EFFORT, history=HistoryPolicy.KEEP_LAST)
    sub = node.create_subscription(StatusText, "/mavros/statustext/recv", lambda m: reasons.append(m.text), qos)
    arm_cli.wait_for_service(timeout_sec=10.0)
    t0 = time.time()
    attempt = 0
    try:
        while time.time() - t0 < timeout:
            attempt += 1
            del reasons[:]
            fut = arm_cli.call_async(CommandBool.Request(value=True))
            rclpy.spin_until_future_complete(node, fut, timeout_sec=5.0)
            t1 = time.time()
            while time.time() - t1 < period:
                rclpy.spin_once(node, timeout_sec=0.05)
                if is_armed():
                    print(f"armed after {time.time() - t0:.0f} s, attempt {attempt}", flush=True)
                    return True
            why = "; ".join(r for r in reasons if "rm" in r) or "no reason reported"
            print(f"arm attempt {attempt} refused: {why}", flush=True)
        print(f"NOT armed after {timeout:.0f} s", flush=True)
        return False
    finally:
        node.destroy_subscription(sub)
