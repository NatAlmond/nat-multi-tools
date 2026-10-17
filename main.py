import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
import yt_dlp

# ====================== KONFIGURASI ======================
DOWNLOAD_DIR = Path("/tmp/downloads")   # Vercel hanya izinkan /tmp
DOWNLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI(
    title="Nat-Multi Tools",
    description="AIO Media Downloader (Vercel version)",
    version="1.3.0-vercel"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ====================== MODEL ======================
class DownloadRequest(BaseModel):
    url: str
    type: str = "video"
    quality: str = "best"

class DownloadResponse(BaseModel):
    status: str
    message: str
    filename: Optional[str] = None
    download_url: Optional[str] = None
    title: Optional[str] = None

# ====================== FUNGSI ======================
def get_ydl_opts(download_type: str, quality: str, output_path: str) -> dict:
    if download_type == "audio":
        return {
            "format": "bestaudio/best",
            "outtmpl": output_path,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "128",
            }],
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }

    # Untuk Vercel kita pakai format yang lebih ringan
    format_map = {
        "best": "best[ext=mp4]/best",
        "1080": "best[height<=1080][ext=mp4]/best",
        "720":  "best[height<=720][ext=mp4]/best",
        "480":  "best[height<=480][ext=mp4]/best",
        "360":  "best[height<=360][ext=mp4]/best",
    }

    return {
        "format": format_map.get(quality, "best[ext=mp4]/best"),
        "outtmpl": output_path,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

def download_media(url: str, download_type: str, quality: str) -> dict:
    file_id = str(uuid.uuid4())[:8]
    outtmpl = str(DOWNLOAD_DIR / f"{file_id}.%(ext)s")

    ydl_opts = get_ydl_opts(download_type, quality, outtmpl)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "Unknown")

            downloaded_file = None
            for f in DOWNLOAD_DIR.glob(f"{file_id}.*"):
                downloaded_file = f
                break

            if not downloaded_file or not downloaded_file.exists():
                raise Exception("File tidak ditemukan setelah unduhan")

            safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip()
            safe_title = safe_title[:60] or "download"
            ext = downloaded_file.suffix
            final_name = f"{safe_title}{ext}"
            final_path = DOWNLOAD_DIR / final_name

            counter = 1
            while final_path.exists():
                final_name = f"{safe_title}_{counter}{ext}"
                final_path = DOWNLOAD_DIR / final_name
                counter += 1

            downloaded_file.rename(final_path)

            return {
                "filename": final_name,
                "title": title,
            }

    except Exception as e:
        raise Exception(str(e))

# ====================== ENDPOINTS ======================

@app.get("/", response_class=HTMLResponse)
def serve_frontend():
    html_path = Path(__file__).parent / "nat-multi-tools-1.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>nat-multi-tools.html tidak ditemukan</h1>", status_code=404)

@app.get("/health")
def health():
    return {"status": "ok", "platform": "vercel"}

@app.post("/download", response_model=DownloadResponse)
def create_download(req: DownloadRequest):
    if not req.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL tidak valid")

    try:
        result = download_media(req.url, req.type, req.quality)
        return DownloadResponse(
            status="success",
            message="Unduhan berhasil",
            filename=result["filename"],
            download_url=f"/file/{result['filename']}",
            title=result["title"]
        )
    except Exception as e:
        error_msg = str(e)
        if "ffmpeg" in error_msg.lower() or "ffprobe" in error_msg.lower():
            error_msg = "FFmpeg tidak tersedia di Vercel. Coba type Audio atau quality lebih rendah."
        raise HTTPException(status_code=500, detail=error_msg)

@app.get("/file/{filename}")
def get_file(filename: str):
    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Nama file tidak valid")

    file_path = DOWNLOAD_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File tidak ditemukan")

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream"
    )
