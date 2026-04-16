import time
import serial
import argparse
import sys

def read_until_ready(ser, timeout=10):
    start = time.time()
    while time.time() - start < timeout:
        if ser.in_waiting:
            line = ser.readline().decode(errors="ignore").strip()
            if line:
                print("[ARDUINO]", line)
                if line == "READY":
                    return True
    return False

def send_and_wait_ok(ser, cmd, timeout=20):
    ser.write((cmd + "\n").encode())
    ser.flush()

    start = time.time()
    while time.time() - start < timeout:
        if ser.in_waiting:
            line = ser.readline().decode(errors="ignore").strip()
            if line:
                print("[ARDUINO]", line)
                if line == "OK":
                    return True
                if line == "ABORTED":
                    raise RuntimeError("Job aborted by hardware button.")
                if line.startswith("ERR"):
                    raise RuntimeError(line)
    raise TimeoutError(f"Timeout waiting for OK after: {cmd}")

def stream_job(ser, cmd_file):
    with open(cmd_file, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            send_and_wait_ok(ser, line, timeout=60)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, help="COM port, e.g. COM5 or /dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--cmd", required=True, help="Path to .cmd job file")
    parser.add_argument("--width", type=float, required=True, help="Draw area width in mm")
    parser.add_argument("--height", type=float, required=True, help="Draw area height in mm")
    parser.add_argument("--steps-per-mm-x", type=float, required=True)
    parser.add_argument("--steps-per-mm-y", type=float, required=True)
    parser.add_argument("--pen-up-angle", type=int, default=90)
    parser.add_argument("--pen-down-angle", type=int, default=35)
    parser.add_argument("--feed-us", type=int, default=700, help="Smaller = faster")
    args = parser.parse_args()

    with serial.Serial(args.port, args.baud, timeout=0.2) as ser:
        time.sleep(2.5)

        ser.reset_input_buffer()
        ser.write(b"HELLO\n")
        ser.flush()

        if not read_until_ready(ser):
            print("Did not receive READY from Arduino.")
            sys.exit(1)

        cfg = (
            f"CFG {args.width:.3f} {args.height:.3f} "
            f"{args.steps_per_mm_x:.6f} {args.steps_per_mm_y:.6f} "
            f"{args.pen_up_angle} {args.pen_down_angle} {args.feed_us}"
        )
        send_and_wait_ok(ser, cfg)

        print("\nCALIBRATING")
        print("Manually move the pen carriage to the TOP-LEFT corner of the paper.")
        input("When you are exactly at top-left, press Enter here...")
        send_and_wait_ok(ser, "FREE_MOTORS")
        print("Move carriage now...")
        input("After moving it by hand to top-left, press Enter to set origin...")
        send_and_wait_ok(ser, "SET_ORIGIN")

        print("\n=== SANITY CHECK ===")
        print("Arduino will draw the boundary square, return to origin, and lift pen.")
        send_and_wait_ok(ser, "SANITY", timeout=180)

        confirm = input("Did the square land correctly on the paper corners? (y/n): ").strip().lower()
        if confirm != "y":
            print("Stopped. Adjust mechanics/config and run again.")
            return

        print("\n=== PRINT START ===")
        print("Use the hardware abort button any time to cancel.")
        stream_job(ser, args.cmd)

        print("\n=== FINISHED ===")
        send_and_wait_ok(ser, "PU")
        send_and_wait_ok(ser, "M 0 0", timeout=120)

if __name__ == "__main__":
    main()

#python run_plotter.py --port COM5 --cmd art.cmd --width 180 --height 180 --steps-per-mm-x 80 --steps-per-mm-y 80