"""
app.py

Decision-Aware Document Review Portal.

A web interface for the OCR Decision System. Upload any image,
see everything Tesseract reads, the extracted fields, the
decision-impact analysis, and the minimum verification set.

The reviewer can accept or correct the flagged fields, and the
decision updates immediately.

Run:
    python3 app.py
Then open http://127.0.0.1:5000
"""

import base64
import io
import tempfile
from pathlib import Path

from flask import Flask, request, render_template_string
from werkzeug.utils import secure_filename

import pytesseract
from PIL import Image, ImageDraw

from src.field_extractor import extract_fields
from src.uncertainty import detect_uncertainty
from src.dependency_graph import build_graph
from src.impact import decision_impact_scores
from src.decision import decision_function, load_policy


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB


def upload_policy(threshold=None):
    policy = load_policy(require_threshold=False)
    if threshold is not None:
        policy["threshold"] = threshold
    return policy


PAGE = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Decision-Aware Document Review Portal</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         margin: 0; padding: 0; background: #f4f6f9; color: #1a1a1a; }
  header { background: #1a3d6d; color: white; padding: 16px 30px; }
  header h1 { font-size: 18px; margin: 0; font-weight: 600; }
  header .sub { font-size: 13px; opacity: 0.85; }
  main { max-width: 1400px; margin: 30px auto; padding: 0 20px; }
  .uploader { background: white; border-radius: 10px; padding: 40px;
              text-align: center; border: 2px dashed #c4d0e0; }
  .uploader h2 { margin: 0 0 10px 0; color: #1a3d6d; }
  .uploader p { color: #666; margin: 0 0 24px 0; }
  button { background: #1a3d6d; color: white; padding: 12px 28px;
           font-size: 15px; border: none; border-radius: 6px;
           cursor: pointer; font-weight: 600; }
  button:hover { background: #0f2a4d; }
  button.secondary { background: #4a6fa5; }
  .grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px;
          margin-top: 20px; }
  .panel { background: white; border-radius: 10px; padding: 20px;
           box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
  .panel h3 { margin: 0 0 14px 0; font-size: 14px; text-transform: uppercase;
              letter-spacing: 0.5px; color: #666; font-weight: 700; }
  .panel img { max-width: 100%; border-radius: 6px; border: 1px solid #e0e6ee; }
  .decision-badge { padding: 12px 20px; border-radius: 8px;
                    font-weight: 700; font-size: 20px;
                    display: inline-block; margin-bottom: 16px; }
  .auto { background: #d4f5d4; color: #1e6b1e; }
  .manager { background: #ffe8b3; color: #8a5c00; }
  .review { background: #ffd4d4; color: #8a0000; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; margin-top: 8px; }
  th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #eef1f5; }
  th { background: #f8fafc; font-size: 12px; text-transform: uppercase;
       letter-spacing: 0.5px; color: #666; }
  td.impact { font-weight: 600; }
  td.impact.high { color: #b00020; }
  td.impact.zero { color: #888; }
  .tag { display: inline-block; padding: 2px 8px; border-radius: 4px;
         font-size: 11px; font-weight: 600; }
  .tag.verify { background: #ffe0e0; color: #b00020; }
  .tag.skip { background: #e8f0e8; color: #1e6b1e; }
  .tag.unc { background: #fff4d8; color: #8a5c00; }
  .tag.conf { background: #e0e8f5; color: #1a3d6d; }
  .verify-list { margin-top: 20px; padding: 16px; background: #fbf5f5;
                 border-left: 4px solid #b00020; border-radius: 6px; }
  .verify-list h4 { margin: 0 0 10px 0; font-size: 14px; color: #b00020;
                    text-transform: uppercase; }
  .verify-list label { display: block; margin: 8px 0; font-size: 14px; }
  .verify-list input { padding: 8px; border: 1px solid #ccc;
                       border-radius: 4px; font-size: 14px;
                       width: 220px; margin-left: 8px; }
  .stable { padding: 16px; background: #eefbf0; border-left: 4px solid #1e6b1e;
            border-radius: 6px; color: #1e6b1e; font-weight: 600; }
  .ocr-text { background: #f8fafc; border: 1px solid #e0e6ee;
              border-radius: 6px; padding: 12px; font-size: 13px;
              font-family: monospace; max-height: 320px; overflow-y: auto;
              white-space: pre-wrap; }
  .stats { display: flex; gap: 20px; font-size: 13px; color: #666;
           margin-bottom: 12px; }
  .stats strong { color: #1a3d6d; }
</style>
</head>
<body>
<header>
  <div>
    <h1>Decision-Aware Document Review Portal</h1>
    <div class="sub">Minimum-cost decision-stabilizing verification for OCR-to-decision pipelines</div>
  </div>
</header>

<main>

{% if not result %}
<div class="uploader">
  <h2>Upload a document image</h2>
  <p>Upload a receipt or invoice. The system will OCR it, extract fields, and identify which uncertain values could change the decision.</p>
  <form method="post" enctype="multipart/form-data">
    <input type="file" name="image" accept="image/*" required>
    <label style="display:block; margin:18px 0;">Decision threshold ({{ currency }}):
      <input type="number" name="threshold" step="any" value="{{ threshold_value or '' }}" required>
    </label>
    <button type="submit">Run pipeline</button>
  </form>
  {% if error %}
  <p style="color:#b00020; margin-top:20px;"><strong>Error:</strong> {{ error }}</p>
  {% endif %}
</div>
{% endif %}

{% if result %}
<div class="grid">

  <div class="panel">
    <h3>Original image</h3>
    <img src="data:image/png;base64,{{ result.original_b64 }}" alt="uploaded">
    <h3 style="margin-top:20px;">OCR word boxes</h3>
    <img src="data:image/png;base64,{{ result.boxes_b64 }}" alt="boxes">
  </div>

  <div class="panel">
    <h3>OCR output</h3>
    <div class="stats">
      <span>Words: <strong>{{ result.n_words }}</strong></span>
      <span>Lines: <strong>{{ result.n_lines }}</strong></span>
    </div>
    <div class="ocr-text">{{ result.ocr_text }}</div>

    <h3 style="margin-top:20px;">Extracted fields</h3>
    <table>
      <tr><th>Field</th><th>Value</th><th>Conf.</th></tr>
      {% for row in result.fields %}
      <tr>
        <td>{{ row.name }}</td>
        <td>{{ row.value }}</td>
        <td>{{ row.confidence }}</td>
      </tr>
      {% endfor %}
    </table>
  </div>

  <div class="panel">
    <h3>Decision</h3>
    <div class="decision-badge {{ result.decision_class }}">{{ result.decision }}</div>

    <h3 style="margin-top:10px;">Decision-impact analysis</h3>
    <table>
      <tr><th>Field</th><th>Status</th><th>Impact</th><th>Action</th></tr>
      {% for row in result.analysis %}
      <tr>
        <td>{{ row.name }}</td>
        <td>
          {% if row.uncertain %}<span class="tag unc">uncertain</span>{% endif %}
          {% if not row.uncertain %}<span class="tag conf">confident</span>{% endif %}
        </td>
        <td class="impact {% if row.impact_high %}high{% elif row.impact_zero %}zero{% endif %}">{{ row.impact }}</td>
        <td>
          {% if row.verify %}<span class="tag verify">VERIFY</span>
          {% else %}<span class="tag skip">skip</span>{% endif %}
        </td>
      </tr>
      {% endfor %}
    </table>

    {% if result.to_verify %}
    <div class="verify-list">
      <h4>Fields requiring verification</h4>
      <p>The system decided that only these fields can change the decision:</p>
      <form method="post" action="/verify">
        <input type="hidden" name="threshold" value="{{ result.threshold }}">
        {% for f in result.to_verify %}
        <label>
          {{ f }}:
          <input type="text" name="verify_{{ f }}" value="{{ result.field_values[f] }}">
        </label>
        {% endfor %}
        <button type="submit" style="margin-top:12px;">Apply verification</button>
      </form>
    </div>
    {% else %}
    <div class="stable">
      No verification needed. The decision is stable under current uncertainty.
    </div>
    {% endif %}
  </div>

</div>

<div style="text-align:center; margin-top:30px;">
  <a href="/" style="text-decoration:none;">
    <button class="secondary">Upload another document</button>
  </a>
</div>
{% endif %}

</main>
</body>
</html>
"""


def run_ocr(image_path):
    image = Image.open(image_path).convert("RGB")
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    words = []
    lines_seen = set()
    for i in range(len(data["text"])):
        text = data["text"][i].strip()
        if not text:
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1.0
        b = (int(data["block_num"][i]), int(data["par_num"][i]), int(data["line_num"][i]))
        lines_seen.add(b)
        words.append({
            "text": text, "confidence": conf,
            "bbox": {"x": int(data["left"][i]), "y": int(data["top"][i]),
                     "width": int(data["width"][i]), "height": int(data["height"][i])},
            "block_num": b[0], "par_num": b[1], "line_num": b[2],
        })
    return image, words, len(lines_seen)


def draw_boxes(image, words):
    img = image.copy()
    draw = ImageDraw.Draw(img)
    for w in words:
        b = w["bbox"]
        draw.rectangle(
            [b["x"], b["y"], b["x"] + b["width"], b["y"] + b["height"]],
            outline=(220, 30, 30), width=2,
        )
    return img


def img_to_b64(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def decision_class(label):
    return {"AUTO_APPROVE": "auto",
            "MANAGER_REVIEW": "manager"}.get(label, "review")


def compute_pipeline(ocr_result, policy):
    fields, lines, provenance = extract_fields(ocr_result)
    graph = build_graph(policy)
    uncertain = detect_uncertainty(fields, provenance)
    impacts = decision_impact_scores(fields, uncertain, provenance, graph, policy)
    decision = decision_function(fields, policy)
    return fields, provenance, uncertain, impacts, decision, lines


def build_result(fields, provenance, impacts, decision, lines, words,
                 image, boxes_img, ocr_text):
    field_rows = []
    for name, value in fields.items():
        prov = provenance.get(name)
        conf = prov["confidence"] if prov else "-"
        field_rows.append({"name": name, "value": value, "confidence": conf})

    analysis_rows = []
    to_verify = []
    for name in ("company", "date", "address", "total"):
        info = impacts.get(name)
        if info is None:
            analysis_rows.append({
                "name": name, "uncertain": False,
                "impact": "0.000", "impact_high": False, "impact_zero": True,
                "verify": False,
            })
            continue
        impact = info.get("impact", 0.0)
        verify = impact > 0
        if verify:
            to_verify.append(name)
        analysis_rows.append({
            "name": name, "uncertain": True,
            "impact": f"{impact:.3f}",
            "impact_high": impact > 0,
            "impact_zero": impact == 0,
            "verify": verify,
        })

    return {
        "original_b64": img_to_b64(image),
        "boxes_b64":    img_to_b64(boxes_img),
        "n_words":      len(words),
        "n_lines":      len(lines),
        "ocr_text":     ocr_text,
        "decision":     decision,
        "decision_class": decision_class(decision),
        "fields":       field_rows,
        "analysis":     analysis_rows,
        "to_verify":    to_verify,
        "field_values": {n: fields.get(n, "") for n in ("company","date","address","total")},
    }


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        policy = upload_policy()
        return render_template_string(PAGE, currency=policy["currency"])

    f = request.files.get("image")
    if not f:
        return render_template_string(PAGE, error="No file uploaded.", currency=upload_policy()["currency"])

    threshold_text = request.form.get("threshold", "").strip()
    if not threshold_text:
        return render_template_string(
            PAGE, error="threshold required", currency=upload_policy()["currency"]
        )
    try:
        threshold = float(threshold_text)
    except ValueError:
        return render_template_string(
            PAGE, error="threshold required", currency=upload_policy()["currency"],
            threshold_value=threshold_text,
        )
    policy = upload_policy(threshold)

    tmpdir = Path(tempfile.mkdtemp())
    path = tmpdir / secure_filename(f.filename)
    f.save(path)

    try:
        image, words, n_lines = run_ocr(path)
        boxes_img = draw_boxes(image, words)
        ocr_result = {"id": path.stem, "image_path": str(path), "words": words}
        fields, provenance, uncertain, impacts, decision, lines = compute_pipeline(ocr_result, policy)
    except Exception as e:
        return render_template_string(
            PAGE, error=f"Pipeline failed: {e}", currency=policy["currency"],
            threshold_value=threshold_text,
        )

    ocr_text = "\n".join(w["text"] for w in words)
    result = build_result(fields, provenance, impacts, decision, lines, words,
                          image, boxes_img, ocr_text)
    result["threshold"] = threshold
    result["currency"] = policy["currency"]
    return render_template_string(PAGE, result=result)


@app.route("/verify", methods=["POST"])
def verify():
    threshold_text = request.form.get("threshold", "").strip()
    if not threshold_text:
        policy = upload_policy()
        return render_template_string(
            PAGE, error="threshold required", currency=policy["currency"]
        )
    try:
        policy = upload_policy()
        policy["threshold"] = float(threshold_text)
    except ValueError:
        return render_template_string(
            PAGE, error="threshold required", currency=upload_policy()["currency"]
        )
    field_values = {
        "company": request.form.get("verify_company", ""),
        "date":    request.form.get("verify_date", ""),
        "address": request.form.get("verify_address", ""),
        "total":   request.form.get("verify_total", ""),
    }
    try:
        field_values["total"] = float(field_values["total"])
    except (TypeError, ValueError):
        field_values["total"] = None

    decision = decision_function(field_values, policy)
    return render_template_string(
        SIMPLE_VERIFY_PAGE,
        decision=decision,
        decision_class=decision_class(decision),
        field_values=field_values,
        threshold=policy["threshold"],
        currency=policy["currency"],
    )


SIMPLE_VERIFY_PAGE = r"""
<!doctype html>
<html><head><meta charset="utf-8">
<title>Verified decision</title>
<style>
 body { font-family: -apple-system, sans-serif; max-width: 700px;
        margin: 60px auto; padding: 0 20px; }
 h1 { color: #1a3d6d; }
 .decision { padding: 14px 20px; border-radius: 8px;
             font-size: 22px; font-weight: 700; display: inline-block; }
 .auto { background: #d4f5d4; color: #1e6b1e; }
 .manager { background: #ffe8b3; color: #8a5c00; }
 .review { background: #ffd4d4; color: #8a0000; }
 table { border-collapse: collapse; width: 100%; margin-top: 20px; }
 th, td { text-align: left; padding: 10px 14px; border-bottom: 1px solid #eee; }
 th { background: #f8fafc; color: #666; text-transform: uppercase;
      font-size: 12px; letter-spacing: 0.5px; }
 button { background: #1a3d6d; color: white; padding: 12px 24px;
          border: none; border-radius: 6px; cursor: pointer;
          font-size: 15px; margin-top: 30px; }
</style></head>
<body>
  <h1>Verified decision</h1>
  <p>After applying the reviewer-supplied values:</p>
  <p>Policy threshold: {{ threshold }} {{ currency }}</p>
  <div class="decision {{ decision_class }}">{{ decision }}</div>
  <table>
    <tr><th>Field</th><th>Value</th></tr>
    {% for k, v in field_values.items() %}
    <tr><td>{{ k }}</td><td>{{ v }}</td></tr>
    {% endfor %}
  </table>
  <a href="/"><button>Process another document</button></a>
</body></html>
"""


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
