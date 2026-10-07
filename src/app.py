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
Then open http://127.0.0.1:5001
"""

import base64
import io
import binascii
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
app.config["MAX_CONTENT_LENGTH"] = 27 * 1024 * 1024  # 20 MB upload or base64 rerun
CURRENCIES = ("INR", "USD", "EUR", "GBP", "RM", "SGD", "JPY", "AUD", "CAD", "AED")
ACCEPTED_MIME = {"image/jpeg", "image/png", "image/webp", "image/bmp", "image/tiff"}
MAX_IMAGE_BYTES = 20 * 1024 * 1024


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
  .uploader { background: white; border-radius: 8px; padding: 20px;
              box-shadow: 0 2px 10px rgba(0,0,0,.08); }
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
  .intro { margin: 10px 0 20px; color: #526173; }
  details { margin: 16px 0 20px; color: #35465c; font-size: 14px; }
  details p { max-width: 760px; line-height: 1.5; }
  .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px 20px; }
  .form-field label { display: block; font-weight: 700; margin-bottom: 7px; }
  .form-field input, .form-field select { width: 100%; height: 42px; padding: 8px 10px;
    border: 1px solid #b8c3d1; border-radius: 5px; background: white; font: inherit; }
  .form-field input:focus, .form-field select:focus { outline: none; border-color: #3478c5;
    box-shadow: 0 0 0 3px rgba(52,120,197,.2); }
  .hint, .file-meta { display: block; color: #687687; font-size: 12px; margin-top: 6px; }
  .error-text { display: block; color: #b00020; font-size: 13px; margin-top: 6px; }
  .currency-label { display: flex !important; align-items: center; gap: 7px; }
  .info { position: relative; display: inline-grid; place-items: center; width: 16px; height: 16px;
    border-radius: 50%; background: #e3edf8; color: #1a3d6d; font-size: 11px; cursor: help; }
  .info:hover::after { content: attr(data-tip); position: absolute; z-index: 3; top: 22px; left: 0;
    width: 230px; padding: 9px; border-radius: 5px; background: #25364a; color: white;
    font-size: 12px; font-weight: 400; }
  .form-actions { grid-column: 1 / -1; display: flex; justify-content: flex-end; }
  button:disabled { background: #91a3b8; cursor: not-allowed; }
  .error-card { background: #fff0f0; border: 1px solid #e4a2a2; color: #8a0000;
    border-radius: 8px; padding: 18px; margin: 18px 0; }
  .error-card a { color: #8a0000; font-weight: 600; }
  .loading-shimmer { height: 5px; margin: 0 0 16px; overflow: hidden; background: #e8edf3; }
  .loading-shimmer.pending { display: none; }
  .loading-shimmer.pending.active { display: block; }
  .spinner { display: inline-block; margin-right: 6px; animation: spin .8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .loading-shimmer::after { content: ""; display: block; height: 100%; width: 35%;
    background: linear-gradient(90deg,#d8e7f8,#5b9be0,#d8e7f8); animation: shimmer 1.2s infinite; }
  @keyframes shimmer { from { transform: translateX(-110%); } to { transform: translateX(310%); } }
  .result-meta { color: #59697b; font-size: 13px; margin: -8px 0 14px; line-height: 1.7; }
  .rerun { margin-top: 18px; border-top: 1px solid #e7ebf0; padding-top: 14px; }
  .rerun label { display: block; font-weight: 700; font-size: 13px; margin-bottom: 6px; }
  .rerun select { height: 40px; width: 100%; border: 1px solid #b8c3d1; border-radius: 5px; padding: 7px; }
  @media (max-width: 699px) { main { margin: 18px auto; padding: 0 14px; }
    .form-grid { grid-template-columns: 1fr; } .form-actions button { width: 100%; }
    header { padding: 16px 18px; } }
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

{% if error %}<div class="error-card"><strong>Error:</strong> {{ error }}<br><a href="/">Try again</a></div>{% endif %}

{% if not result %}
<div class="uploader">
  <div id="pending-bar" class="loading-shimmer pending" aria-hidden="true"></div>
  <h2>Upload a document image</h2>
  <p class="intro">Upload a receipt or invoice. The system will OCR it, extract fields, and identify which uncertain values could change the decision.</p>
  <details><summary>What does this do?</summary><p>This portal reads a document image and extracts information from it. It estimates whether uncertain values could change the decision. It highlights fields that may need review so you can focus verification effort.</p></details>
  <form id="analyze-form" method="post" enctype="multipart/form-data">
    <div class="form-grid">
      <div class="form-field">
        <label for="image">Document image</label>
        <input id="image" type="file" name="image" accept="image/jpeg,image/png,image/webp,image/bmp,image/tiff" required>
        <span class="file-meta" id="file-meta">Choose an image up to 20 MB.</span>
        <span class="error-text" id="file-error">{% if error %}{{ error }}{% endif %}</span>
      </div>
      <div class="form-field">
        <label for="threshold">Threshold</label>
        <input id="threshold" type="number" name="threshold" step="any" min="0" value="{{ threshold_value or '' }}" required>
        <span class="hint">The value above which the document requires review.</span>
        <span class="error-text" id="threshold-error"></span>
      </div>
      <div class="form-field">
        <label class="currency-label" for="currency">Currency <span class="info" tabindex="0" data-tip="Currency is metadata only. It does not affect the decision arithmetic." aria-label="Currency is metadata only. It does not affect the decision arithmetic.">i</span></label>
        <select id="currency" name="currency">{% for item in currencies %}<option value="{{ item }}" {% if item == currency %}selected{% endif %}>{{ item }}</option>{% endfor %}</select>
      </div>
      <div class="form-field">
        <label for="document_type">Document type</label>
        <select id="document_type" name="document_type"><option value="Receipt" {% if document_type == 'Receipt' %}selected{% endif %}>Receipt</option><option value="Generic" {% if document_type == 'Generic' %}selected{% endif %}>Generic</option></select>
        <span class="hint">Receipt mode extracts company/date/address/total. Generic mode uses the configured extraction pipeline.</span>
      </div>
      <div class="form-actions"><button id="submit-button" type="submit" name="submit" disabled>Analyze document</button></div>
    </div>
  </form>
</div>
<script>
(() => {
  const form = document.getElementById('analyze-form');
  const file = document.getElementById('image');
  const threshold = document.querySelector("#analyze-form input[name='threshold']");
  const button = document.getElementById('submit-button');
  const fileMeta = document.getElementById('file-meta');
  const fileError = document.getElementById('file-error');
  const thresholdError = document.getElementById('threshold-error');
  const allowed = ['image/jpeg','image/png','image/webp','image/bmp','image/tiff'];
  const validate = () => {
    const f = file.files[0];
    fileError.textContent = '';
    if (f && !allowed.includes(f.type)) fileError.textContent = 'Select a JPEG, PNG, WEBP, BMP, or TIFF image.';
    else if (f && f.size > 20 * 1024 * 1024) fileError.textContent = 'Image must be 20 MB or smaller.';
    const n = threshold.valueAsNumber;
    const okThreshold = Number.isFinite(n) && n > 0;
    thresholdError.textContent = okThreshold ? '' : 'Threshold must be a positive number';
    const okFile = f && allowed.includes(f.type) && f.size <= 20 * 1024 * 1024;
    const currency = document.querySelector("#analyze-form select[name='currency']").value;
    const documentType = document.querySelector("#analyze-form select[name='document_type']").value;
    const okSettings = ['INR','USD','EUR','GBP','RM','SGD','JPY','AUD','CAD','AED'].includes(currency)
      && ['Receipt','Generic'].includes(documentType);
    const valid = Boolean(okFile && okThreshold && okSettings);
    button.disabled = !valid;
    return valid;
  };
  file.addEventListener('change', () => {
    const f = file.files[0];
    fileMeta.textContent = f ? `${f.name} · ${(f.size / (1024 * 1024)).toFixed(2)} MB` : 'Choose an image up to 20 MB.';
    validate();
  });
  threshold.addEventListener('input', validate);
  form.addEventListener('submit', event => {
    if (!validate()) { event.preventDefault(); return; }
    button.disabled = true;
    button.innerHTML = '<span class="spinner">◌</span> Analyzing…';
    document.getElementById('pending-bar').classList.add('active');
  });
  validate();
})();
</script>
{% endif %}

{% if result %}
<div class="loading-shimmer" aria-hidden="true"></div>
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
    <div class="result-meta">Threshold: {{ result.threshold }} {{ result.currency }}<br>Document type: {{ result.document_type }}</div>

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
    <form class="rerun" method="post" action="/">
      <input type="hidden" name="image_data" value="{{ result.original_b64 }}">
      <input type="hidden" name="image_name" value="{{ result.image_name }}">
      <input type="hidden" name="threshold" value="{{ result.threshold }}">
      <input type="hidden" name="currency" value="{{ result.currency }}">
      <label for="rerun-type">Document type</label>
      <select id="rerun-type" name="document_type"><option value="Receipt" {% if result.document_type == 'Receipt' %}selected{% endif %}>Receipt</option><option value="Generic" {% if result.document_type == 'Generic' %}selected{% endif %}>Generic</option></select>
      <button type="submit" style="margin-top:10px;">Re-run</button>
    </form>
  </div>

</div>

<div style="text-align:center; margin-top:30px;">
  <a href="/" style="text-decoration:none; color:#1a3d6d;">Upload another document</a>
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
        return render_template_string(PAGE, currency="INR", document_type="Receipt", currencies=CURRENCIES)

    f = request.files.get("image")
    currency = request.form.get("currency", "INR")
    document_type = request.form.get("document_type", "Receipt")
    threshold_text = request.form.get("threshold", "").strip()
    form_context = {"currency": currency, "document_type": document_type, "currencies": CURRENCIES,
                    "threshold_value": threshold_text}
    if currency not in CURRENCIES:
        return render_template_string(PAGE, error="Unsupported currency.", **form_context)
    if document_type not in ("Receipt", "Generic"):
        return render_template_string(PAGE, error="Unsupported document type.", **form_context)

    if not threshold_text:
        return render_template_string(PAGE, error="Threshold must be a positive number", **form_context)
    try:
        threshold = float(threshold_text)
        if threshold <= 0:
            raise ValueError
    except (ValueError, OverflowError):
        return render_template_string(PAGE, error="Threshold must be a positive number", **form_context)

    image_data = request.form.get("image_data", "")
    if f and f.filename:
        filename = secure_filename(f.filename) or "document"
        if f.mimetype not in ACCEPTED_MIME:
            return render_template_string(PAGE, error="Unsupported image type.", **form_context)
        raw = f.read(MAX_IMAGE_BYTES + 1)
        if len(raw) > MAX_IMAGE_BYTES:
            return render_template_string(PAGE, error="Image must be 20 MB or smaller.", **form_context)
    elif image_data:
        try:
            raw = base64.b64decode(image_data, validate=True)
        except (binascii.Error, ValueError):
            return render_template_string(PAGE, error="Could not restore the uploaded image.", **form_context)
        if len(raw) > MAX_IMAGE_BYTES:
            return render_template_string(PAGE, error="Image must be 20 MB or smaller.", **form_context)
        filename = secure_filename(request.form.get("image_name", "document.png")) or "document.png"
    else:
        return render_template_string(PAGE, error="No file uploaded.", **form_context)

    policy = upload_policy(threshold)
    policy["currency"] = currency

    tmpdir = Path(tempfile.mkdtemp())
    path = tmpdir / filename
    path.write_bytes(raw)

    try:
        image, words, n_lines = run_ocr(path)
        boxes_img = draw_boxes(image, words)
        ocr_result = {"id": path.stem, "image_path": str(path), "words": words,
                      "currency": currency, "document_type": document_type}
        fields, provenance, uncertain, impacts, decision, lines = compute_pipeline(ocr_result, policy)
    except Exception as e:
        return render_template_string(
            PAGE, error=f"Pipeline failed: {e}", **form_context,
        )

    ocr_text = "\n".join(w["text"] for w in words)
    result = build_result(fields, provenance, impacts, decision, lines, words,
                          image, boxes_img, ocr_text)
    result["threshold"] = threshold_text
    result["currency"] = currency
    result["document_type"] = document_type
    result["image_name"] = filename
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
    app.run(debug=True, host="127.0.0.1", port=5001)
