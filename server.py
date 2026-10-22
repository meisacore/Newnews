import os
from contextlib import asynccontextmanager
from pathlib import Path
import jwt
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StrictInt
from economy import Market

market = Market(os.getenv("NORX_DB", "data/norx.sqlite3"))
DEV = os.getenv("NORX_DEV_AUTH") == "1"


@asynccontextmanager
async def lifespan(app):
    # Simulation runs in the separate worker, never once per API process.
    yield


app = FastAPI(title="NORX simulated USD market", lifespan=lifespan)


@app.middleware("http")
async def fresh_api(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(ValueError)
async def invalid(request, exc):
    from fastapi.responses import JSONResponse

    return JSONResponse({"detail": str(exc)}, status_code=400)


def identity(authorization: str = Header(default="")):
    if DEV and authorization == "Bearer local-demo":
        return "local:demo"
    app_id = os.getenv("PRIVY_APP_ID")
    key = os.getenv("PRIVY_VERIFICATION_KEY", "").replace("\\n", "\n")
    if not app_id or not key:
        raise HTTPException(503, "Privy authentication is not configured")
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sign in to trade")
    try:
        claims = jwt.decode(
            authorization[7:],
            key,
            algorithms=["ES256"],
            audience=app_id,
            issuer="privy.io",
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
        sub = claims["sub"]
        if not isinstance(sub, str) or not sub.startswith("did:privy:"):
            raise ValueError("Invalid identity")
        return sub
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(401, "Invalid or expired session")


@app.get("/api/config")
def config():
    return {
        "dev_auth": DEV,
        "privy_configured": bool(
            os.getenv("PRIVY_APP_ID") and os.getenv("PRIVY_VERIFICATION_KEY")
        ),
    }


@app.get("/api/state")
def state(selected: str | None = None):
    return market.state(selected)


@app.get("/api/me")
def me(user=Depends(identity)):
    return market.account(user)


@app.get("/api/candles/{coin}")
def candles(coin: str, interval: int = 60):
    if interval not in (60, 300, 3600):
        raise HTTPException(400, "Unsupported candle interval")
    return market.candles(coin, interval)


class Quote(BaseModel):
    coin: str = Field(max_length=32)
    side: str = Field(pattern="^(buy|sell)$")
    budget: StrictInt | None = None
    qty: StrictInt | None = None


class Execute(BaseModel):
    quote_id: str = Field(max_length=64)
    request_id: str = Field(min_length=8, max_length=64)


@app.post("/api/quote")
def quote(body: Quote, user=Depends(identity)):
    market.account(user)
    return market.quote(user, body.coin, body.side, body.budget, body.qty)


@app.post("/api/trade")
def trade(body: Execute, user=Depends(identity)):
    return market.execute(user, body.quote_id, body.request_id)


DIST = Path(__file__).parent / "frontend" / "dist"
if DIST.is_dir():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")
