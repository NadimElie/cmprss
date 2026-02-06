import os
import time
import subprocess
import redis
from rq import Worker

# CONFIG
REDIS_HOST = os.getenv('REDIS_HOST', 'redis-service')
REDIS_PORT = 6379

def compress_pdf(file_path, job_id):
    output_path = file_path.replace("/uploads/", "/processed/")
    
    # The "Safe" Command for Slim Containers
    # -dPDFSETTINGS=/ebook : Good quality (150dpi), usually 50-80% reduction
    cmd = [
        "gs", 
        "-sDEVICE=pdfwrite", 
        "-dCompatibilityLevel=1.4", 
        "-dPDFSETTINGS=/ebook",
        "-dNOPAUSE", "-dQUIET", "-dBATCH", "-dSAFER",
        f"-sOutputFile={output_path}",
        file_path
    ]
    
    print(f"Starting Job {job_id}...")
    
    try:
        # Run Ghostscript
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Check if GS failed
        if result.returncode != 0:
            print(f"❌ CRASH: {result.stderr}")
            with open(output_path, "w") as f:
                f.write(f"Error: Compression failed. {result.stderr}")
        else:
            # Check for silent failures (Empty files)
            if os.path.exists(output_path) and os.path.getsize(output_path) < 1000:
                 print(f"❌ FILE TOO SMALL (Likely Corrupt)")
                 with open(output_path, "w") as f:
                    f.write("Error: Resulting file was empty/corrupt.")
            else:
                print(f"Job {job_id} Done. Output saved to {output_path}")

    except Exception as e:
        print(f"❌ PYTHON ERROR: {str(e)}")

    if os.path.exists(file_path):
        os.remove(file_path)
    
    return output_path

if __name__ == '__main__':
    print("Worker initializing...")
    redis_conn = None
    while redis_conn is None:
        try:
            r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)
            if r.ping():
                print("Connected to Redis!")
                redis_conn = r
        except Exception:
            time.sleep(5)

    print("Starting Worker Loop...")
    worker = Worker(['default'], connection=redis_conn)
    worker.work()
