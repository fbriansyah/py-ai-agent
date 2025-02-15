import uvicorn
import logging
import models
import pprint

from fastapi import FastAPI
from fastapi.responses import FileResponse
from routers import default_webhook, rag_webhook, chat
from databases.memory import engine
from dotenv import load_dotenv, get_key
from pathlib import Path
from databases.mongo import MongoClient
from services.file_processor import FileProcessor

# load the config from dot env file
load_dotenv()

# setup fastapi
app = FastAPI()
app.include_router(default_webhook.router)
app.include_router(rag_webhook.router)
app.include_router(chat.router)

models.Base.metadata.create_all(bind=engine)

THIS_DIR = Path(__file__).parent

# setup logging
logging.basicConfig(level=logging.INFO)
@app.get('/')
async def index() -> FileResponse:
    return FileResponse((THIS_DIR / "public" / 'index.html'), media_type='text/html')


@app.get('/chat_app.ts')
async def main_ts() -> FileResponse:
    """Get the raw typescript code, it's compiled in the browser, forgive me."""
    return FileResponse((THIS_DIR / "public" / 'chat_app.ts'), media_type='text/plain')

class DocSection:
    slug: str
    title: str
    content: str
    
    def __init__(self, slug: str, title: str, content: str):
        self.slug = slug
        self.title = title
        self.content = content

@app.get("/test-mongo")
async def test_mongo():
    mongo_uri = get_key(".env", "MONGO_URI")
    if mongo_uri is None:
        logging.error("MONGO_URI not found in .env file")
        return
    mongo_client = MongoClient(mongo_uri, "pyAgent")
    mongo_client.ping()
    col = mongo_client.get_collection("doc_sections")
    data = col.find({})
    
    list_docs: list[DocSection] = []
    
    async for doc in data:
        list_docs.append(DocSection(slug=doc["slug"], title=doc["title"], content=doc["content"]))
    
    return {
        "data": list_docs
    }

def main():
    port = get_key(".env", "PORT")
    # FileProcessor("./uploads/ocbc-doc-tech.pdf").process_file()
    if port is None:
        port = 8000
    else:
        port = int(port)
    logging.info("Starting Service at port %s", port)
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
