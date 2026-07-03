from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import uuid
import subprocess
import glob

# === IMPORT UNTUK RATE LIMITING (POIN 2) ===
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

app = FastAPI(title="Audio/Video Converter API")

# === INISIALISASI RATE LIMITER ===
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_DIR = "/tmp/converter"
os.makedirs(TEMP_DIR, exist_ok=True)

ALLOWED_FORMATS = ["mp3", "wav", "mp4", "avi", "mov", "ogg", "m4a", "webm"]
AUDIO_FORMATS = ["mp3", "wav", "ogg", "m4a"]

# === KONFIGURASI FILE SIZE LIMIT (POIN 3) ===
# 50 MB dalam satuan bytes (Anda bisa ubah angka 50 sesuai keinginan)
MAX_FILE_SIZE = 50 * 1024 * 1024 


@app.get("/")
def read_root():
    return {"message": "Audio/Video Converter API jalan!", "status": "ok"}


def cleanup_files(*paths):
    for path in paths:
        if path and os.path.exists(path):
            os.remove(path)


# ============ KONVERSI FILE UPLOAD ============
@app.post("/convert/media")
@limiter.limit("5/minute")  # Batasi 5 request per menit per IP (Poin 2)
async def convert_media(
    request: Request,       # Wajib ditambahkan untuk Slowapi
    file: UploadFile = File(...),
    target_format: str = "mp3"
):
    if target_format.lower() not in ALLOWED_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Format tidak didukung. Pilih: {ALLOWED_FORMATS}"
        )

    file_id = str(uuid.uuid4())
    input_ext = os.path.splitext(file.filename)[1] or ".tmp"
    input_path = os.path.join(TEMP_DIR, f"{file_id}_input{input_ext}")
    output_path = os.path.join(TEMP_DIR, f"{file_id}_output.{target_format.lower()}")

    try:
        # --- VALIDASI UKURAN FILE SEBELUM DI-WRITE (POIN 3) ---
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413, 
                detail=f"File terlalu besar! Maksimal ukuran file adalah {MAX_FILE_SIZE // (1024*1024)} MB."
            )

        with open(input_path, "wb") as f:
            f.write(content)

        result = subprocess.run(
            ["ffmpeg", "-i", input_path, "-y", output_path],
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode != 0 or not os.path.exists(output_path):
            cleanup_files(input_path, output_path)
            raise HTTPException(
                status_code=500,
                detail=f"Konversi gagal: {result.stderr[-300:]}"
            )

        def iterfile():
            with open(output_path, "rb") as f:
                yield from f
            cleanup_files(input_path, output_path)

        media_type = "audio" if target_format.lower() in AUDIO_FORMATS else "video"

        return StreamingResponse(
            iterfile(),
            media_type=f"{media_type}/{target_format.lower()}",
            headers={
                "Content-Disposition": f"attachment; filename=converted.{target_format.lower()}"
            }
        )

    except subprocess.TimeoutExpired:
        cleanup_files(input_path, output_path)
        raise HTTPException(status_code=408, detail="Konversi terlalu lama, file mungkin terlalu besar")
    except HTTPException:
        raise
    except Exception as e:
        cleanup_files(input_path, output_path)
        raise HTTPException(status_code=500, detail=str(e))


# ============ DOWNLOAD + CONVERT DARI URL ============
class UrlDownloadRequest(BaseModel):
    url: str
    target_format: str = "mp3"


@app.get("/download/url")
@limiter.limit("5/minute")  # Batasi 5 request per menit per IP (Poin 2)
async def download_from_url_get(
    request: Request,       # Wajib ditambahkan untuk Slowapi
    url: str, 
    target_format: str = "mp3"
):
    """Endpoint GET untuk kompatibilitas dengan FileSystem.downloadAsync di React Native"""
    return await _process_download(url, target_format)


@app.post("/download/url")
@limiter.limit("5/minute")  # Batasi 5 request per menit per IP (Poin 2)
async def download_from_url(
    request: Request,       # Wajib ditambahkan untuk Slowapi
    payload: UrlDownloadRequest  # Diubah dari 'request' agar tidak bentrok nama variable
):
    """Endpoint POST untuk request biasa"""
    return await _process_download(payload.url, payload.target_format)


async def _process_download(url: str, target_format: str):
    target_format = target_format.lower()
    if target_format not in ALLOWED_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Format tidak didukung. Pilih: {ALLOWED_FORMATS}"
        )

    file_id = str(uuid.uuid4())
    output_template = os.path.join(TEMP_DIR, f"{file_id}_output.%(ext)s")
    is_audio_only = target_format in AUDIO_FORMATS

    try:
        if is_audio_only:
            cmd = [
                "yt-dlp",
                "-x",
                "--audio-format", target_format,
                # --- BATASI UKURAN DOWNLOAD YT-DLP (POIN 3) ---
                "--max-filesize", f"{MAX_FILE_SIZE}", 
                "-o", output_template,
                "--no-playlist",
                url
            ]
        else:
            cmd = [
                "yt-dlp",
                "-f", "bestvideo+bestaudio/best",
                # --- BATASI UKURAN DOWNLOAD YT-DLP (POIN 3) ---
                "--max-filesize", f"{MAX_FILE_SIZE}",
                "--merge-output-format", target_format,
                "-o", output_template,
                "--no-playlist",
                url
            ]

        result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # max 10 menit untuk download
        )

        if result.returncode != 0:
            # Jika gagal karena ukuran file melebihi batas yt-dlp
            if "File is larger than max-filesize" in result.stderr:
                raise HTTPException(status_code=413, detail="File di URL tersebut terlalu besar (Maks 50MB)")
                
            raise HTTPException(
                status_code=400,
                detail=f"Download gagal: {result.stderr[-400:]}"
            )

        # Cari file hasil download
        matches = glob.glob(os.path.join(TEMP_DIR, f"{file_id}_output.*"))
        if not matches:
            raise HTTPException(status_code=500, detail="File hasil download tidak ditemukan")

        output_path = matches[0]

        def iterfile():
            with open(output_path, "rb") as f:
                yield from f
            cleanup_files(output_path)

        media_type = "audio" if is_audio_only else "video"

        return StreamingResponse(
            iterfile(),
            media_type=f"{media_type}/{target_format}",
            headers={
                "Content-Disposition": f"attachment; filename=downloaded.{target_format}"
            }
        )

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="Download terlalu lama, coba lagi")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
