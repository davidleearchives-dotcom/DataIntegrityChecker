from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from . import models, database, auth, crud, schemas
from .routers import auth as auth_router, dashboard, history, settings

models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="BMS Data Verification Tool")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

app.include_router(auth_router.router)
app.include_router(dashboard.router)
app.include_router(history.router)
app.include_router(settings.router)

@app.on_event("startup")
def startup_event():
    # Create default admin if not exists
    db = database.SessionLocal()
    try:
        user = crud.get_user_by_username(db, "admin")
        if not user:
            admin_user = schemas.UserCreate(
                username="admin",
                password="!admin12345",
                full_name="Administrator",
                department="IT",
                contact="00000000000",
                role="admin"
            )
            crud.create_user(db, admin_user)
            print("Default admin created.")
    finally:
        db.close()

# Page Routes (Frontend)

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/history_page", response_class=HTMLResponse)
async def history_page(request: Request):
    return templates.TemplateResponse("history.html", {"request": request})

@app.get("/settings_page", response_class=HTMLResponse)
async def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request})
