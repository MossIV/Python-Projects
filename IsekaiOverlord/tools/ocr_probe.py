import sys
from rapidocr_onnxruntime import RapidOCR

engine = RapidOCR()
path = sys.argv[1]
result, elapse = engine(path)
if not result:
    print("NO TEXT DETECTED")
    raise SystemExit(0)
print(f"{len(result)} text boxes, elapse={elapse}")
for box, text, score in result:
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    try:
        s = f"{float(score):.2f}"
    except (TypeError, ValueError):
        s = str(score)
    print(f"  [{int(min(xs)):4d},{int(min(ys)):4d} {int(max(xs)):4d},{int(max(ys)):4d}] {s}  {text!r}")
