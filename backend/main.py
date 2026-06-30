from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import io
import os
import uuid
import subprocess
import shutil

app = FastAPI(title="File Converter API")

# Izinkan akses dari mobile app manapun
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_DIR = "/tmp/converter"
os.makedirs(TEMP_DIR, exist_ok=True)


@app.get("/")
def read_root():
    return {"message": "File Converter API jalan!", "status": "ok"}


# ============ KONVERSI GAMBAR ============
@app.post("/convert/image")
async def convert_image(
    file: UploadFile = File(...),
    target_format: str = "png"
):
    allowed_formats = ["png", "jpeg", "jpg", "webp"]
    if target_format.lower() not in allowed_formats:
        raise HTTPException(
            status_code=400,
            detail=f"Format tidak didukung. Pilih: {allowed_formats}"
        )

    contents = await file.read()

    try:
        image = Image.open(io.BytesIO(contents))
    except Exception:
        raise HTTPException(status_code=400, detail="File bukan gambar yang valid")

    if target_format.lower() in ["jpeg", "jpg"] and image.mode in ["RGBA", "P"]:
        image = image.convert("RGB")

    output_buffer = io.BytesIO()
    save_format = "JPEG" if target_format.lower() in ["jpeg", "jpg"] else target_format.upper()
    image.save(output_buffer, format=save_format)
    output_buffer.seek(0)

    return StreamingResponse(
        output_buffer,
        media_type=f"image/{target_format.lower()}",
        headers={
            "Content-Disposition": f"attachment; filename=converted.{target_format.lower()}"
        }
    )


# ============ KONVERSI AUDIO/VIDEO (FFmpeg) ============
@app.post("/convert/media")
async def convert_media(
    file: UploadFile = File(...),
    target_format: str = "mp3"
):
    allowed_formats = ["mp3", "wav", "mp4", "avi", "mov", "ogg", "m4a", "webm"]
    if target_format.lower() not in allowed_formats:
        raise HTTPException(
            status_code=400,
            detail=f"Format tidak didukung. Pilih: {allowed_formats}"
        )

    # Simpan file upload sementara
    file_id = str(uuid.uuid4())
    input_ext = os.path.splitext(file.filename)[1] or ".tmp"
    input_path = os.path.join(TEMP_DIR, f"{file_id}_input{input_ext}")
    output_path = os.path.join(TEMP_DIR, f"{file_id}_output.{target_format.lower()}")

    try:
        with open(input_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # Jalankan FFmpeg untuk konversi
        result = subprocess.run(
            ["ffmpeg", "-i", input_path, "-y", output_path],
            capture_output=True,
            text=True,
            timeout=300  # max 5 menit
        )

        if result.returncode != 0 or not os.path.exists(output_path):
            raise HTTPException(
                status_code=500,
                detail=f"Konversi gagal: {result.stderr[-300:]}"
            )

        def iterfile():
            with open(output_path, "rb") as f:
                yield from f
            # Bersihkan file temporary setelah selesai dikirim
            os.remove(input_path) if os.path.exists(input_path) else None
            os.remove(output_path) if os.path.exists(output_path) else None

        media_type = "audio" if target_format.lower() in ["mp3", "wav", "ogg", "m4a"] else "video"

        return StreamingResponse(
            iterfile(),
            media_type=f"{media_type}/{target_format.lower()}",
            headers={
                "Content-Disposition": f"attachment; filename=converted.{target_format.lower()}"
            }
        )

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="Konversi terlalu lama, file mungkin terlalu besar")
    except Exception as e:
        # Bersihkan file kalau error
        if os.path.exists(input_path):
            os.remove(input_path)
        if os.path.exists(output_path):
            os.remove(output_path)
        raise HTTPException(status_code=500, detail=str(e))

