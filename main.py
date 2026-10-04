from fastapi import FastAPI

from api.charts import router as chart_router


app = FastAPI(
    title="Pet Natal Chart",
    version="0.1.0",
)

app.include_router(chart_router)


@app.get("/")
def root():
    return {
        "message": "Pet Natal Chart API 🐾🌙"
    }