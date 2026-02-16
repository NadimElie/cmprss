import os
import sys
import time
import shutil
import subprocess
import redis
from redis.exceptions import RedisError, ConnectionError

def connect_redis() -> redis.Redis:
    """NIST Zero-Trust: Require valid environment, fail explicitly."""
    host = os.environ.get("REDIS_HOST")
    if not host:
        sys.stderr.write("CRITICAL: REDIS_HOST environment variable missing. Halting.\n")
        sys.exit(1)
    
    try:
        # socket_timeout strictly bounded to 15s to safely exceed the 10s brpop block
        client = redis.Redis(host=host, port=6379, db=0, decode_responses=True, socket_timeout=15)
        client.ping()
        return client
    except RedisError as e:
        sys.stderr.write(f"CRITICAL: Initial Redis connection failed: {str(e)}\n")
        sys.exit(1)

def release_concurrency_lock(client: redis.Redis, job_id: str) -> None:
    """State Containment: Strictly remove the active job flag so the user can upload again."""
    try:
        client_id = client.hget(f"job:{job_id}", "client_id")
        if client_id:
            client.srem(f"active_jobs:{client_id}", job_id)
    except RedisError as e:
        sys.stderr.write(f"ERROR: Failed to release concurrency lock for job {job_id}: {str(e)}\n")

def process_job(client: redis.Redis, job_data: str) -> None:
    """
    NASA JPL Deterministic Execution: Strict execution limits.
    DoD JSF Explicit Error Handling: Verify system states.
    """
    if "::" not in job_data:
        sys.stderr.write(f"ERROR: Malformed job payload received: {job_data}\n")
        return

    job_id, input_path = job_data.split("::", 1)
    output_path = input_path.replace(".pdf", "_compressed.pdf")
    
    try:
        client.hset(f"job:{job_id}", mapping={"percent": 5, "status": "processing"})
        
        if not os.path.exists(input_path):
            sys.stderr.write(f"ERROR: Target file missing: {input_path}\n")
            client.hset(f"job:{job_id}", mapping={"percent": 0, "status": "error: file missing"})
            return

        input_size = os.path.getsize(input_path)

        # Ghostscript Command
        gs_command = [
            "gs", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.4",
            "-dPDFSETTINGS=/ebook",
            "-dNOPAUSE", "-dBATCH", 
            "-dDetectDuplicateImages=true",
            "-dCompressFonts=true",
            "-r150",
            f"-sOutputFile={output_path}", input_path
        ]

        try:
            # NASA JPL: Bounded execution. 300 seconds maximum.
            subprocess.run(
                gs_command,
                timeout=300,
                check=True,
                capture_output=True,
                text=True
            )
        except subprocess.TimeoutExpired:
            sys.stderr.write(f"CRITICAL: Ghostscript timed out after 300s. File: {input_path}\n")
            client.hset(f"job:{job_id}", mapping={"percent": 0, "status": "error: timeout"})
            if os.path.exists(output_path):
                os.remove(output_path)
            return
        except subprocess.CalledProcessError as e:
            sys.stderr.write(f"ERROR: Ghostscript failed. Code: {e.returncode}. Stderr: {e.stderr}\n")
            client.hset(f"job:{job_id}", mapping={"percent": 0, "status": "error: process failed"})
            if os.path.exists(output_path):
                os.remove(output_path)
            return

        # Size guard logic
        if not os.path.exists(output_path):
            sys.stderr.write(f"ERROR: Ghostscript succeeded but output file missing: {output_path}\n")
            client.hset(f"job:{job_id}", mapping={"percent": 0, "status": "error: output missing"})
            return

        output_size = os.path.getsize(output_path)
        if output_size >= input_size:
            sys.stdout.write(f"WARNING: Compression ineffective ({output_size} >= {input_size}). Reverting.\n")
            shutil.copy(input_path, output_path)
            
        client.hset(f"job:{job_id}", mapping={"percent": 100, "status": "done"})

    except OSError as e:
        sys.stderr.write(f"SYSTEM ERROR: OS interaction failed for {job_id}: {e.strerror}\n")
        client.hset(f"job:{job_id}", mapping={"percent": 0, "status": "error: system failure"})
    except RedisError as e:
        sys.stderr.write(f"DATABASE ERROR: Failed to update status for {job_id}: {str(e)}\n")
    finally:
        # Crucial State Containment: Release the lock regardless of success or failure.
        release_concurrency_lock(client, job_id)

def main() -> None:
    """NASA JPL: Deterministic bounded main loop."""
    sys.stdout.write("Worker initializing...\n")
    redis_client = connect_redis()
    sys.stdout.write("Worker listening on 'pdf_queue'...\n")
    
    while True:
        try:
            # 10s block, perfectly encapsulated by 15s socket timeout
            job = redis_client.brpop("pdf_queue", timeout=10)
            if job:
                process_job(redis_client, job[1])
        except ConnectionError as e:
            sys.stderr.write(f"NETWORK ERROR: Redis connection dropped: {str(e)}\n")
            time.sleep(5)
            # Reconnect on drop
            redis_client = connect_redis() 
        except RedisError as e:
            sys.stderr.write(f"DATABASE ERROR: Redis poll failed: {str(e)}\n")
            time.sleep(2)
        except KeyboardInterrupt:
            sys.stdout.write("Worker shutting down safely.\n")
            break

if __name__ == "__main__":
    main()
