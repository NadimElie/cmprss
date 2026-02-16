import os
import sys
import uuid
import logging
import magic
from flask import Flask, request, render_template, jsonify, send_file
import redis
from redis.exceptions import RedisError

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
app = Flask(__name__)

def get_config() -> dict:
    """State Containment: Localize configuration retrieval."""
    return {
        "UPLOAD_FOLDER": os.getenv("CMPRSS_UPLOAD_FOLDER", "/data/uploads"),
        "REDIS_HOST": os.getenv("REDIS_HOST"),
        "MAX_FILE_SIZE": 50 * 1024 * 1024,  # Strict 50 MB hard limit for all users
    }

def validate_environment(config: dict) -> None:
    """NIST Zero-Trust: Ensure OS environment is valid before starting."""
    if not config["REDIS_HOST"]:
        sys.stderr.write("CRITICAL: REDIS_HOST environment variable missing. Halting.\n")
        sys.exit(1)
        
    try:
        os.makedirs(config["UPLOAD_FOLDER"], exist_ok=True)
    except OSError as e:
        sys.stderr.write(f"CRITICAL: Failed to create upload directory {config['UPLOAD_FOLDER']}. Reason: {e.strerror}\n")
        sys.exit(1)

# Initialize environment check immediately
_startup_config = get_config()
validate_environment(_startup_config)

def get_redis_client() -> redis.Redis:
    """State Containment: Dynamic credential request, no global mutable Redis client."""
    host = os.getenv("REDIS_HOST")
    try:
        client = redis.Redis(
            host=host,
            port=6379,
            db=0,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5
        )
        client.ping()
        return client
    except RedisError as e:
        sys.stderr.write(f"CRITICAL: Redis connection failed. Reason: {str(e)}\n")
        sys.exit(1)

@app.route('/')
def index():
    if request.args.get('action') == 'download' and request.args.get('job_id'):
        job_id = request.args.get('job_id', '').strip()
        response = _send_compressed_file_if_exists(job_id)
        if response is not None:
            return response
        return jsonify({"error": "File not found"}), 404
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """DISA STIG Hostile Input Assumption: Trust nothing. Enforce limits."""
    client_id = request.headers.get("X-Client-ID")
    if not client_id:
        return jsonify({"error": "Missing client identifier"}), 400

    if 'file' not in request.files:
        return jsonify({"error": "No file payload"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Empty filename"}), 400

    config = get_config()
    r_client = get_redis_client()

    # 1. Verification of Concurrency Limits (Abuse Protection)
    try:
        active_jobs = r_client.scard(f"active_jobs:{client_id}")
        
        if active_jobs >= 1:
            sys.stderr.write(f"REJECTED: Client {client_id} attempted concurrent upload.\n")
            return jsonify({"error": "Rate limit exceeded: You may only process one file at a time."}), 429
            
    except RedisError as e:
        sys.stderr.write(f"ERROR: Redis failure during concurrency check: {str(e)}\n")
        return jsonify({"error": "Internal state validation failed"}), 500

    # 2. Payload Validation
    file_bytes = file.read()
    file_size = len(file_bytes)
    
    if file_size > config["MAX_FILE_SIZE"]:
        sys.stderr.write(f"REJECTED: File size {file_size} exceeds {config['MAX_FILE_SIZE']} limit.\n")
        return jsonify({"error": "File exceeds the 50MB maximum size limit."}), 413

    try:
        mime = magic.Magic(mime=True)
        detected_type = mime.from_buffer(file_bytes[:2048])
        if detected_type != "application/pdf":
            sys.stderr.write(f"REJECTED: Invalid mime type detected: {detected_type}\n")
            return jsonify({"error": "Invalid file type. Only standard PDFs are allowed."}), 415
    except magic.MagicException as e:
        sys.stderr.write(f"ERROR: MIME validation failed. Reason: {str(e)}\n")
        return jsonify({"error": "File validation failed"}), 500

    # 3. Execution & State Update
    job_id = str(uuid.uuid4())
    save_path = os.path.join(config["UPLOAD_FOLDER"], f"{job_id}.pdf")

    try:
        with open(save_path, 'wb') as f:
            f.write(file_bytes)
            
        r_client.sadd(f"active_jobs:{client_id}", job_id)
        r_client.hset(f"job:{job_id}", mapping={"percent": 0, "status": "Queued", "client_id": client_id})
        r_client.lpush("pdf_queue", f"{job_id}::{save_path}")
        return jsonify({"job_id": job_id})
        
    except OSError as e:
        sys.stderr.write(f"SYSTEM ERROR: Disk write failed for job {job_id}: {e.strerror}\n")
        return jsonify({"error": "Storage subsystem failure"}), 500
    except RedisError as e:
        sys.stderr.write(f"DATABASE ERROR: Redis push failed for job {job_id}: {str(e)}\n")
        if os.path.exists(save_path):
            os.remove(save_path) # Rollback
        return jsonify({"error": "Queue subsystem failure"}), 500

def _send_compressed_file_if_exists(job_id):
    config = get_config()
    job_id = (job_id or "").strip()
    if not job_id:
        return None
    filename = f"{job_id}_compressed.pdf"
    file_path = os.path.abspath(os.path.join(config["UPLOAD_FOLDER"], filename))
    upload_abs = os.path.abspath(config["UPLOAD_FOLDER"])
    if not file_path.startswith(upload_abs) or os.path.dirname(file_path) != upload_abs:
        return None
    if os.path.isfile(file_path):
        return send_file(file_path, as_attachment=True, download_name="compressed.pdf")
    return None

@app.route('/status/<job_id>', methods=['GET'])
def check_status(job_id):
    if request.args.get("download"):
        response = _send_compressed_file_if_exists(job_id)
        if response is not None:
            return response
        return jsonify({"error": "File not found"}), 404

    r_client = get_redis_client()
    try:
        key = f"job:{job_id}"
        data = r_client.hgetall(key)
        if not data:
            return jsonify({"percent": 0, "status": "Unknown Job"}), 404

        status = (data.get('status') or 'Processing').strip()
        percent = int(data.get('percent') or 0)
        status_lower = status.lower()

        download_url = f"/download/{job_id}" if status_lower == 'done' else None

        return jsonify({
            "percent": percent,
            "status": status,
            "download_url": download_url
        })
    except RedisError as e:
        sys.stderr.write(f"ERROR: Failed to fetch status for {job_id}: {str(e)}\n")
        return jsonify({"error": "State retrieval failed"}), 500

@app.route('/download/<path:job_id>', methods=['GET'])
def download_file(job_id):
    job_id = (job_id or "").split('/')[0].strip()
    if not job_id:
        return jsonify({"error": "Missing job id"}), 400
    
    response = _send_compressed_file_if_exists(job_id)
    if response is not None:
        return response
    
    sys.stderr.write(f"WARNING: Invalid download request. File not found for job_id={job_id}\n")
    return jsonify({"error": "File not found"}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
