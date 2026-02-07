import os
import uuid
import logging
from flask import Flask, request, render_template, jsonify, send_file
import redis

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
app = Flask(__name__)

# --- Configuration ---
UPLOAD_FOLDER = '/data/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
REDIS_HOST = os.getenv("REDIS_HOST", "redis-service")

r = redis.Redis(
    host=REDIS_HOST,
    port=6379,
    db=0,
    decode_responses=True,
    socket_timeout=5
)

@app.route('/')
def index():
    # Download via root path so tunnel/proxy that only forwards "/" still works
    if request.args.get('action') == 'download' and request.args.get('job_id'):
        job_id = request.args.get('job_id', '').strip()
        response = _send_compressed_file_if_exists(job_id)
        if response is not None:
            return response
        return jsonify({"error": "File not found"}), 404
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    job_id = str(uuid.uuid4())
    filename = f"{job_id}.pdf"
    save_path = os.path.join(UPLOAD_FOLDER, filename)

    try:
        file.save(save_path)
        r.hset(f"job:{job_id}", mapping={"percent": 0, "status": "Queued"})
        r.lpush("pdf_queue", f"{job_id}::{save_path}")
        return jsonify({"job_id": job_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def _send_compressed_file_if_exists(job_id):
    """Serve compressed file from /data/uploads (single source of truth)."""
    job_id = (job_id or "").strip()
    if not job_id:
        return None
    filename = f"{job_id}_compressed.pdf"
    file_path = os.path.abspath(os.path.join(UPLOAD_FOLDER, filename))
    upload_abs = os.path.abspath(UPLOAD_FOLDER)
    if not file_path.startswith(upload_abs) or os.path.dirname(file_path) != upload_abs:
        return None
    if os.path.isfile(file_path):
        return send_file(file_path, as_attachment=True, download_name="compressed.pdf")
    return None


@app.route('/status/<job_id>', methods=['GET'])
def check_status(job_id):
    # Fallback: ?download=1 serves the file (works if /download/ is not routed by tunnel)
    if request.args.get("download"):
        response = _send_compressed_file_if_exists(job_id)
        if response is not None:
            return response
        return jsonify({"error": "File not found"}), 404

    key = f"job:{job_id}"
    data = r.hgetall(key)
    if not data:
        return jsonify({"percent": 0, "status": "Unknown Job"}), 404

    status = (data.get('status') or 'Processing').strip()
    percent = int(data.get('percent') or 0)
    status_lower = status.lower()

    # Handshake: when status is "done", always send download_url so frontend never gets undefined
    download_url = f"/download/{job_id}" if status_lower == 'done' else None

    return jsonify({
        "percent": percent,
        "status": status,
        "download_url": download_url
    })

@app.route('/download/<path:job_id>', methods=['GET'])
def download_file(job_id):
    job_id = (job_id or "").split('/')[0].strip()
    if not job_id:
        return jsonify({"error": "Missing job id"}), 400
    log.info("Download: job_id=%s", job_id)
    response = _send_compressed_file_if_exists(job_id)
    if response is not None:
        return response
    log.warning("Download: file not found for job_id=%s path=%s", job_id, os.path.join(UPLOAD_FOLDER, f"{job_id}_compressed.pdf"))
    return jsonify({"error": "File not found"}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
