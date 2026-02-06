import os
import time
import redis
import subprocess
import logging

# --- GOLD STANDARD: Load Config from Vault ---
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

# Connect to Redis
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)
logging.basicConfig(level=logging.INFO)

def update_job_status(job_id, percent, status_text):
    key = f"job:{job_id}"
    r.hset(key, mapping={"percent": percent, "status": status_text})
    r.expire(key, 600)

def compress_pdf(file_path, job_id):
    try:
        logging.info(f"Starting job {job_id}")
        update_job_status(job_id, 10, "Initializing Worker...")

        output_path = file_path.replace(".pdf", "_compressed.pdf")
        
        # Ghostscript Command
        gs_command = [
            "gs", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.4",
            "-dPDFSETTINGS=/screen", "-dNOPAUSE", "-dQUIET", "-dBATCH",
            f"-sOutputFile={output_path}", file_path
        ]

        update_job_status(job_id, 50, "Compressing PDF (Heavy Lift)...")
        subprocess.run(gs_command, check=True)

        update_job_status(job_id, 90, "Finalizing Output...")
        
        if os.path.exists(output_path):
             update_job_status(job_id, 100, "Done")
             return output_path
        else:
             raise Exception("Output file not generated")

    except Exception as e:
        logging.error(f"Job {job_id} failed: {e}")
        update_job_status(job_id, 0, f"Error: {str(e)}")
        return None

if __name__ == "__main__":
    logging.info(f"Worker started. Listening on {REDIS_HOST}...")
    while True:
        job = r.brpop("pdf_queue", 0)
        if job:
            job_data = job[1].decode('utf-8')
            job_id, file_path = job_data.split("::")
            compress_pdf(file_path, job_id)
