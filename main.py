import os
import uuid
from flask import Flask, request, render_template, jsonify, send_file
import redis

app = Flask(__name__)

# --- GOLD STANDARD: Configuration ---
UPLOAD_FOLDER = '/data/uploads'
PROCESSED_FOLDER = '/data/processed'
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

r = redis.Redis(host=REDIS_HOST, port=6379, db=0)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if file:
        job_id = str(uuid.uuid4())
        filename = f"{job_id}.pdf"
        save_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(save_path)

        r.hset(f"job:{job_id}", mapping={"percent": 0, "status": "Queued"})
        r.lpush("pdf_queue", f"{job_id}::{save_path}")

        return jsonify({"job_id": job_id})

@app.route('/status/<job_id>', methods=['GET'])
def check_status(job_id):
    key = f"job:{job_id}"
    if not r.exists(key):
        return jsonify({"percent": 0, "status": "Unknown Job"}), 404

    data = r.hgetall(key)
    percent = int(data.get(b'percent', 0))
    status = data.get(b'status', b'Unknown').decode('utf-8')
    return jsonify({"percent": percent, "status": status})

@app.route('/download/<job_id>', methods=['GET'])
def download_file(job_id):
    filename = f"{job_id}_compressed.pdf"
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True, download_name="compressed.pdf")
    else:
        return "File not found.", 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
