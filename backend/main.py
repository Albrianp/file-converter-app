from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from PIL import Image
import io

app = FastAPI(title="File Converter API")


@app.get("/")
def read_root():
    return {"message": "File Converter API jalan!", "status": "ok"}


@app.post("/convert/image")
async def convert_image(
    file: UploadFile = File(...),
    target_format: str = "png"
):
    """
    Konversi gambar ke format lain.
    target_format bisa: png, jpeg, webp
    """
    # Validasi format yang didukung
    allowed_formats = ["png", "jpeg", "jpg", "webp"]
    if target_format.lower() not in allowed_formats:
        raise HTTPException(
            status_code=400,
            detail=f"Format tidak didukung. Pilih: {allowed_formats}"
        )

    # Baca file yang diupload
    contents = await file.read()

    try:
        image = Image.open(io.BytesIO(contents))
    except Exception:
        raise HTTPException(status_code=400, detail="File bukan gambar yang valid")

    # Convert ke RGB jika perlu (untuk JPEG yang tidak support transparansi)
    if target_format.lower() in ["jpeg", "jpg"] and image.mode in ["RGBA", "P"]:
        image = image.convert("RGB")

    # Simpan hasil konversi ke buffer memory
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
