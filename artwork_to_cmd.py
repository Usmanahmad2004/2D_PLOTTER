#LOADS SVG
#FLATTENS PATH INTO LINE SEGMENTS
#SCALES INTO DRAWING AREA
#SORTS PATHS BY NEAREST DIST. TO REDUCE PEN-UP TRAVEL
#WRITES .cmd FILE FOR ARDUINO SENDER

import math
import argparse
from svgpathtools import svg2paths2


DEFAULT_CURVE_STEP_MM = 1.5   # smaller = more points, smoother curves
MIN_SAMPLES_PER_SEG = 8


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def flatten_path(path, curve_step_mm=DEFAULT_CURVE_STEP_MM):
    
    #Turns svgpathtools Path into a list of (x, y) points.

    pts = []

    for seg in path:
        seg_len = max(seg.length(error=1e-4), 0.001)
        samples = max(MIN_SAMPLES_PER_SEG, int(math.ceil(seg_len / curve_step_mm)))

        for i in range(samples + 1):
            t = i / samples
            p = seg.point(t)
            x = float(p.real)
            y = float(p.imag)

            if not pts or (abs(pts[-1][0] - x) > 1e-9 or abs(pts[-1][1] - y) > 1e-9):
                pts.append((x, y))

    return pts

def get_bounds(polylines):
    xs = []
    ys = []
    for line in polylines:
        for x, y in line:
            xs.append(x)
            ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)

def scale_and_fit(polylines, width_mm, height_mm, margin_mm):
   
    #Preserves aspect ratio and fits drawing inside the usable area.
    #Origin is top-left.
  
    min_x, min_y, max_x, max_y = get_bounds(polylines)
    art_w = max_x - min_x
    art_h = max_y - min_y

    usable_w = width_mm - 2 * margin_mm
    usable_h = height_mm - 2 * margin_mm

    if art_w <= 0 or art_h <= 0:
        raise ValueError("Artwork bounds are invalid.")

    scale = min(usable_w / art_w, usable_h / art_h)

    scaled = []
    for line in polylines:
        new_line = []
        for x, y in line:
            nx = (x - min_x) * scale + margin_mm
            ny = (y - min_y) * scale + margin_mm
            new_line.append((nx, ny))
        scaled.append(new_line)

    return scaled

def sort_paths_nearest_neighbor(polylines):
    
    #Reorders paths to reduce pen-up travel.
    #Also reverses a path if its end is closer than its start.

    if not polylines:
        return []

    remaining = polylines[:]
    ordered = []
    current = (0.0, 0.0)

    while remaining:
        best_idx = None
        best_reverse = False
        best_d = float("inf")

        for i, line in enumerate(remaining):
            d_start = dist(current, line[0])
            d_end = dist(current, line[-1])

            if d_start < best_d:
                best_d = d_start
                best_idx = i
                best_reverse = False

            if d_end < best_d:
                best_d = d_end
                best_idx = i
                best_reverse = True

        chosen = remaining.pop(best_idx)
        if best_reverse:
            chosen = list(reversed(chosen))

        ordered.append(chosen)
        current = chosen[-1]

    return ordered

def write_cmd_file(polylines, output_path):
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# plotter cmd file\n")
        f.write("PU\n")
        for line in polylines:
            if len(line) < 2:
                continue

            sx, sy = line[0]
            f.write(f"M {sx:.3f} {sy:.3f}\n")
            f.write("PD\n")

            for x, y in line[1:]:
                f.write(f"D {x:.3f} {y:.3f}\n")

            f.write("PU\n")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_svg", help="Input SVG file")
    parser.add_argument("output_cmd", help="Output .cmd file")
    parser.add_argument("--width", type=float, required=True, help="Drawing width in mm")
    parser.add_argument("--height", type=float, required=True, help="Drawing height in mm")
    parser.add_argument("--margin", type=float, default=10.0, help="Margin in mm")
    parser.add_argument("--curve-step", type=float, default=DEFAULT_CURVE_STEP_MM,
                        help="Approx point spacing for curves in mm")
    args = parser.parse_args()

    paths, attributes, svg_attributes = svg2paths2(args.input_svg)

    polylines = []
    for path in paths:
        pts = flatten_path(path, curve_step_mm=args.curve_step)
        if len(pts) >= 2:
            polylines.append(pts)

    if not polylines:
        raise RuntimeError("No drawable paths found in SVG.")

    polylines = scale_and_fit(polylines, args.width, args.height, args.margin)
    polylines = sort_paths_nearest_neighbor(polylines)
    write_cmd_file(polylines, args.output_cmd)

    print(f"Wrote: {args.output_cmd}")
    print(f"Paths: {len(polylines)}")
    print(f"Area: {args.width}mm x {args.height}mm")
    print(f"Margin: {args.margin}mm")

if __name__ == "__main__":
    main()

#python artwork_to_cmd.py Tung-Tung-Tung-Sahur.svg art.cmd --width 180 --height 180 --margin 10