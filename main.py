import uvicorn
import logging
import models

from fastapi import FastAPI
from routers import default_webhook, rag_webhook
from databases.memory import engine
from dotenv import load_dotenv, get_key

# load the config from dot env file
load_dotenv()

# setup fastapi
app = FastAPI()
app.include_router(default_webhook.router)
app.include_router(rag_webhook.router)

models.Base.metadata.create_all(bind=engine)

# setup logging
logging.basicConfig(level=logging.INFO)
@app.get("/")
def read_root():
    return {"app_name": "AI Agent", "version": "0.0.1"}

def main():
    port = get_key(".env", "PORT")
    if port is None:
        port = 8000
    else:
        port = int(port)
    logging.info("Starting Service at port %s", port)
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
