from fastapi import FastAPI, File, UploadFile
import json

app = FastAPI()

@app.post("/upload-json")
async def upload_json(file: UploadFile = File(...)):
    contents = await file.read()
    data = json.loads(contents.decode("utf-8"))  # parse JSON file
    return {"status": "ok", "parsed": data}