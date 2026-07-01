from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import uuid
import subprocess
import glob

app = FastAPI(title="Audio/Video Converter API")

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


@app.get("/")
def read_root():
    return {"message": "Audio/Video Converter API jalan!", "status": "ok"}


def cleanup_files(*paths):
    for path in paths:
        if path and os.path.exists(path):
            os.remove(path)


# ============ KONVERSI FILE UPLOAD ============
@app.post("/convert/media")
async def convert_media(
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
        with open(input_path, "wb") as f:
            content = await file.read()
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
async def download_from_url_get(url: str, target_format: str = "mp3"):
    """Endpoint GET untuk kompatibilitas dengan FileSystem.downloadAsync di React Native"""
    return await _process_download(url, target_format)


@app.post("/download/url")
async def download_from_url(request: UrlDownloadRequest):
    """Endpoint POST untuk request biasa"""
    return await _process_download(request.url, request.target_format)


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
            # Download lalu extract audio dengan format target
            cmd = [
                "yt-dlp",
                "-x",
                "--audio-format", target_format,
                "-o", output_template,
                "--no-playlist",
                request.url
            ]
        else:
            # Download video, lalu convert ke format target via ffmpeg merge
            cmd = [
                "yt-dlp",
                "-f", "bestvideo+bestaudio/best",
                "--merge-output-format", target_format,
                "-o", output_template,
                "--no-playlist",
                request.url
            ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600  # max 10 menit untuk download
        )

        if result.returncode != 0:
            raise HTTPException(
                status_code=400,
                detail=f"Download gagal: {result.stderr[-400:]}"
            )

        # Cari file hasil download (ekstensi sudah pasti sesuai target_format)
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
