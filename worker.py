import os
import time
import redis
import subprocess
import logging
import threading

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
REDIS_HOST = os.getenv("REDIS_HOST", "redis-service")

def get_redis():
    for i in range(1, 11):
        try:
            client = redis.Redis(host=REDIS_HOST, port=6379, db=0, decode_responses=True)
            client.ping()
            logging.info(f"Connected to Redis at {REDIS_HOST}")
            return client
        except Exception as e:
            logging.warning(f"Attempt {i}: Waiting for Redis... {e}")
            time.sleep(3)
    raise Exception("Critical: Could not connect to Redis.")

r = get_redis()

def update_status(job_id, percent, status):
    r.hset(f"job:{job_id}", mapping={"percent": percent, "status": status})

def process_pdf(job_data):
    job_id = None
    try:
        job_id, input_path = job_data.split("::")
        output_path = input_path.replace(".pdf", "_compressed.pdf")

        logging.info(f"[*] Processing {job_id}")
        update_status(job_id, 15, "processing")

        gs_command = [
            "gs", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.4",
            "-dPDFSETTINGS=/screen", "-dNOPAUSE", "-dBATCH", "-dQUIET",
            f"-sOutputFile={output_path}", input_path
        ]

        proc = subprocess.Popen(gs_command)

        def bump_progress():
            pct = 15
            going_up = True
            while proc.poll() is None:
                time.sleep(2)
                if proc.poll() is not None:
                    break
                if pct < 85:
                    pct = min(85, pct + 12)
                elif pct < 96:
                    pct += 1
                else:
                    # oscillate 96↔97 so bar never looks stuck at 99%
                    pct = 97 if going_up else 96
                    going_up = not going_up
                update_status(job_id, pct, "processing")

        t = threading.Thread(target=bump_progress, daemon=True)
        t.start()
        proc.wait()
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, gs_command)

        if os.path.exists(output_path):
            logging.info(f"[!] {job_id} Done!")
            update_status(job_id, 100, "done")  # lowercase so web app status.lower() == 'done' matches
        else:
            raise Exception("Output file missing")

    except Exception as e:
        logging.error(f"Job {job_data} failed: {e}")
        if job_id is not None:
            update_status(job_id, 0, f"error: {str(e)}")

if __name__ == "__main__":
    logging.info("Worker listening to 'pdf_queue'...")
    while True:
        try:
            job = r.brpop("pdf_queue", timeout=0)
            if job:
                process_pdf(job[1])
        except Exception as e:
            logging.error(f"Loop error: {e}")
            time.sleep(2)
