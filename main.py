import uvicorn
import logging
import models
import logfire

from fastapi import FastAPI
from fastapi.responses import FileResponse
from routers import default_webhook, rag_webhook, chat, learning
from databases.memory import engine
from dotenv import load_dotenv, get_key
from pathlib import Path
from databases.mongo import MongoClient
from databases.rabbitmq import RabbitClient
from services.file_processor import FileProcessor
from langchain_text_splitters import MarkdownTextSplitter
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

# load the config from dot env file
load_dotenv()

logfire.configure(send_to_logfire='if-token-present', token=get_key(".env", "LOGFIRE_KEY"))

# setup fastapi
app = FastAPI()
app.include_router(default_webhook.router)
app.include_router(rag_webhook.router)
app.include_router(chat.router)
app.include_router(learning.router)

models.Base.metadata.create_all(bind=engine)

THIS_DIR = Path(__file__).parent


rabbit_client = RabbitClient(
    host=get_key(".env", "RABBIT_HOST"),
    port=get_key(".env", "RABBIT_PORT"),
    username=get_key(".env", "RABBIT_USER"),
    password=get_key(".env", "RABBIT_PASS")
)

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
    embedding: list[float]
    
    def __init__(self, slug: str, title: str, content: str, embedding: list[float]):
        self.slug = slug
        self.title = title
        self.content = content
        self.embedding = embedding
    def to_dict(self):
        return {
            "slug": self.slug,
            "title": self.title,
            "content": self.content,
            "embedding": self.embedding
        }

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

@app.get("/test-rabbit")
def test_rabbit():
    rabbit_client.publish("ai.upload", "./uploads/ocbc-doc-tech.pdf")
    return {
        "message": "success"
    }
    
@app.get("/test-split")
async def test_split():
    list_docs: list[DocSection] = []
    content = ""
    open_ai = AsyncOpenAI()
    logfire.instrument_openai(open_ai)
    mongo_uri = get_key(".env", "MONGO_URI")
    if mongo_uri is None:
        logging.error("MONGO_URI not found in .env file")
        return
    mongo_client = MongoClient(mongo_uri, "pyAgent")
    mongo_client.ping()
    col = mongo_client.get_collection("doc_sections")
    # open the file
    with open("./uploads/ocbc-doc-tech.md", "r") as f:
            content = f.read()
    with logfire.span('split_file'):
        md_splitter = MarkdownTextSplitter(chunk_size=1000, chunk_overlap=200)
        chunks = md_splitter.split_text(content)
        for chunk in chunks:
            try:
                embedding = await open_ai.embeddings.create(
                    input=chunk,
                    model='text-embedding-3-small',
                )
                list_docs.append(DocSection(slug="ocbc-doc-tech.md", title="SNAP OCBC Doc Tech", content=chunk, embedding=embedding.data[0].embedding))
            except Exception as e:
                logfire.error(e)
    # with logfire.span('insert'):
        list_docs_dict = [doc.to_dict() for doc in list_docs]
        await col.insert_many(list_docs_dict)
    return {
        "message": "success"
    }

class SearchRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    
@app.post("/test-search")
async def test_search(payload: SearchRequest):
    mongo_uri = get_key(".env", "MONGO_URI")
    if mongo_uri is None:
        logging.error("MONGO_URI not found in .env file")
        return
    mongo_client = MongoClient(mongo_uri, "pyAgent")
    mongo_client.ping()
    open_ai = AsyncOpenAI()
    col = mongo_client.get_collection("doc_sections")
    # open the file
    embedding = await open_ai.embeddings.create(
        input=payload.message,
        model='text-embedding-3-small',
    )
    query_embedding = embedding.data[0].embedding
    pipeline = [
        {
            '$vectorSearch': {
                'index': 'embedding_index', 
                'path': 'embedding', 
                'filter': {}, 
                'queryVector': query_embedding, 
                'numCandidates': 150, 
                'limit': 20
            }
        }, 
        {
            '$project': {
                '_id': 0, 
                'slug': 1, 
                'title': 1, 
                'content': 1
            }
        }
    ]
    results = await col.aggregate(pipeline)
    doc_list = []
    async for doc in results:
        obj = {
            "slug": doc["slug"],
            "title": doc["title"],
            "content": doc["content"]
        }
        doc_list.append(obj)
    
    return {
        "data": doc_list
    }

def main():
    port = get_key(".env", "PORT")
    try:
        logging.info("Try to settup RabbitMQ...")
        rabbit_client.setup()
    except Exception as e:
        logging.error("Failed to connect to RabbitMQ: %s", e)
        return
    
    # FileProcessor("./uploads/ocbc-doc-tech.pdf").process_file()
    if port is None:
        port = 8000
    else:
        port = int(port)
    logging.info("Starting Service at port %s", port)
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
