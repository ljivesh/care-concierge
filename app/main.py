from fastapi import FastAPI

app = FastAPI(title="Care Concierge")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
