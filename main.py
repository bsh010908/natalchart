from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.charts import router as chart_router


app = FastAPI(
    title="Pet Natal Chart",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chart_router)


@app.get("/")
def root():
    return {
        "message": "Pet Natal Chart API 🐾🌙"
    }