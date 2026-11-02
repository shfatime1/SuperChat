
from contextlib import asynccontextmanager
from hashlib import sha256
from secrets import token_urlsafe
from threading import RLock
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.chat import ChatResponse, ChatService
from app.config import PROJECT_ROOT, Settings
from app.fallback import ResilientRouter
from app.repositories import DataSourceError, Repositories
from app.domains.engine import DomainEngine
from app.responses import GeminiResponseFormulator
from app.routing import GeminiRouter, InvalidRouterResponse, Router, RouterUnavailable
from app.schemas import ChatRequest
from app.state import SessionNotFound, SessionState, SessionStore


def create_app(settings: Settings | None = None, router: Router | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    sessions = SessionStore()
    service = ChatService(router or GeminiRouter(settings), sessions, GeminiResponseFormulator(settings))
    owners = {}
    cached_requests, request_locks = {}, {}
    guard = RLock()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        try:
            application.state.repositories = Repositories.from_json(settings.data_dir)
            service.engine = DomainEngine(application.state.repositories)
            if router is None:
                service.router = ResilientRouter(settings, application.state.repositories)
            application.state.data_ready = True
        except DataSourceError:
            application.state.data_ready = False
        yield

    application = FastAPI(title="SuperChat", lifespan=lifespan)
    application.state.sessions = sessions
    application.state.chat_service = service
    application.state.data_ready = False
    application.mount("/static", StaticFiles(directory=PROJECT_ROOT / "app" / "static"), name="static")

    @application.middleware("http")
    async def browser_identity(request: Request, call_next):
        owner = request.cookies.get("superchat_owner")
        if not owner or len(owner) != 43:
            owner = token_urlsafe(32)
        request.state.owner = owner
        response = await call_next(request)
        if request.cookies.get("superchat_owner") != owner:
            response.set_cookie("superchat_owner", owner, httponly=True, samesite="lax",
                                secure=settings.secure_cookies, max_age=60 * 60 * 24 * 30)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.url.path not in {"/docs", "/redoc", "/docs/oauth2-redirect"}:
            response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @application.get("/")
    def home():
        return FileResponse(PROJECT_ROOT / "app" / "static" / "index.html")

    @application.get("/api/client")
    def client_info(request: Request):
        return {"namespace": sha256(request.state.owner.encode()).hexdigest()[:24],
                "routing_mode": settings.routing_mode, "reference_date": "2026-11-02",
                "gemini_configured": bool(settings.api_key),
                "routing_status": service.router.status() if isinstance(service.router, ResilientRouter) else "custom"}

    @application.get("/health")
    def health():
        if not application.state.data_ready:
            raise HTTPException(503, "Mock data is unavailable")
        return {"status": "ok"}

    @application.post("/api/chat", response_model=ChatResponse, response_model_exclude_none=True)
    def chat(body: ChatRequest, request: Request):
        if not application.state.data_ready:
            raise HTTPException(503, "Mock data is unavailable")
        try:
            owner = request.state.owner
            if body.session_id is not None and owners.get(body.session_id) != owner:
                raise SessionNotFound()
            if body.request_id is None:
                result = service.chat(body.message, body.session_id)
                owners[result.session_id] = owner
                return result
            key = (owner, body.request_id)
            fingerprint = (body.message, body.session_id)
            with guard:
                lock = request_locks.setdefault(key, RLock())
            with lock:
                if key in cached_requests:
                    previous, result = cached_requests[key]
                    if previous != fingerprint:
                        raise HTTPException(409, "Request ID was already used for another message")
                    return result
                result = service.chat(body.message, body.session_id)
                owners[result.session_id] = owner
                cached_requests[key] = (fingerprint, result)
                return result
        except SessionNotFound:
            raise HTTPException(404, "Session not found") from None
        except RouterUnavailable as exc:
            raise HTTPException(503, str(exc)) from None
        except InvalidRouterResponse:
            raise HTTPException(502, "Routing service returned an invalid result") from None

    @application.get("/api/session/{session_id}", response_model=SessionState,
                     response_model_exclude_none=True)
    def session(session_id: UUID, request: Request):
        try:
            if owners.get(session_id) != request.state.owner:
                raise SessionNotFound()
            return sessions.get(session_id)
        except SessionNotFound:
            raise HTTPException(404, "Session not found") from None

    return application


app = create_app()
