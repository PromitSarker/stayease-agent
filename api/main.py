from fastapi import FastAPI

from api.routers.chat import router as chat_router


def create_app() -> FastAPI:
	app = FastAPI(
		title="StayEase Chat API",
		version="1.0.0",
		description="Minimal chat API backed by StayEase LangGraph agent.",
	)

	app.include_router(chat_router, prefix="/api")
	return app


app = create_app()
