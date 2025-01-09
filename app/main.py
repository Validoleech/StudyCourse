from fastapi import FastAPI

from recipe import recipe_service 
from auth import auth_service

app = FastAPI()

app.include_router(recipe_service.router)
app.include_router(auth_service.router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="localhost", port=9000)