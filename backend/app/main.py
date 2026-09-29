import logging

from fastapi import FastAPI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="MCVMS")

@app.get("/health")
def health_check():
    return {"status": "ok"}
