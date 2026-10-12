from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from supabase import create_client, Client
from . import config

supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
bearer_scheme = HTTPBearer(auto_error=False)
router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    email: str
    password: str


def get_token(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Access token required")
    return credentials.credentials


def get_current_user(token: str = Depends(get_token)):
    try:
        response = supabase.auth.get_user(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if response is None or response.user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return response.user


@router.post("/signup", status_code=201)
def signup(creds: Credentials):
    if not creds.email.strip() or not creds.password:
        raise HTTPException(status_code=400, detail="Email and password are required")
    try:
        res = supabase.auth.sign_up({"email": creds.email, "password": creds.password})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "User created", "user_id": res.user.id if res.user else None}


@router.post("/login")
def login(creds: Credentials):
    try:
        res = supabase.auth.sign_in_with_password({"email": creds.email, "password": creds.password})
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid login credentials")
    return {"access_token": res.session.access_token, "token_type": "bearer"}