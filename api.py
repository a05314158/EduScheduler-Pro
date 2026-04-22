"""api.py — FastAPI backend for EduScheduler."""
import os
import shutil
import sys

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from main import run_scheduler  # noqa: E402

app = FastAPI(title="EduScheduler API")


@app.post("/upload")
async def upload_files(
    groups: UploadFile = File(...),
    weekdays: UploadFile = File(...),
):
    try:
        with open(os.path.join(BASE_DIR, "groups-2.xlsx"), "wb") as f:
            shutil.copyfileobj(groups.file, f)
        with open(os.path.join(BASE_DIR, "weekdays.xlsx"), "wb") as f:
            shutil.copyfileobj(weekdays.file, f)
        return JSONResponse(content={
            "status": "ok",
            "groups": groups.filename,
            "weekdays": weekdays.filename,
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate")
async def generate_schedule():
    try:
        result = run_scheduler(
            config_path=os.path.join(BASE_DIR, "institution_config.json"),
            groups_file=os.path.join(BASE_DIR, "groups-2.xlsx"),
            weekdays_file=os.path.join(BASE_DIR, "weekdays.xlsx"),
            api_mode=True,
        )
        return JSONResponse(content=result)
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Файл не найден: {e}. Сначала загрузите файлы через /upload.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/download")
async def download_excel():
    path = os.path.join(BASE_DIR, "schedule.xlsx")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Файл не найден. Сначала запустите генерацию.")
    return FileResponse(
        path=path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="schedule.xlsx",
    )


# Статика монтируется ПОСЛЕДНЕЙ — иначе перекроет API-маршруты
STATIC_DIR = os.path.join(BASE_DIR, "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")