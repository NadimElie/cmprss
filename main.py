from fastapi import FastAPI, UploadFile, File, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import shutil
import os
import uuid
from redis import Redis
from rq import Queue

app = FastAPI()

# Setup Folders
UPLOAD_DIR = "/data/uploads"
PROCESSED_DIR = "/data/processed"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)

# Templates
templates = Jinja2Templates(directory="templates")

# Redis Queue
redis_conn = Redis(host=os.getenv("REDIS_HOST", "redis-service"), port=6379)
q = Queue(connection=redis_conn)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    # Generate unique ID
    job_id = str(uuid.uuid4())
    filename = f"{job_id}.pdf"
    file_path = os.path.join(UPLOAD_DIR, filename)
    
    # Save Upload
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Send to Worker
    q.enqueue("worker.compress_pdf", file_path, job_id, job_id=job_id)
    
    return {"job_id": job_id, "status": "processing"}

@app.get("/status/{job_id}")
async def check_status(job_id: str):
    job = q.fetch_job(job_id)
    if job and job.get_status() == "finished":
        return {"status": "done", "download_url": f"/download/{job_id}"}
    return {"status": "processing"}

@app.get("/download/{job_id}")
async def download(job_id: str):
    file_path = os.path.join(PROCESSED_DIR, f"{job_id}.pdf")
    if os.path.exists(file_path):
        return FileResponse(file_path, filename="compressed.pdf")
    return {"error": "File not found"}

# --- THE LAUNCHER BLOCK ---
if __name__ == "__main__":
    import uvicorn
    # This tells Python to start the server on Port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)
