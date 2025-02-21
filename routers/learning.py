import os
import logfire

from fastapi import APIRouter
from starlette import status
from openai import AsyncOpenAI
from dotenv import get_key
from langchain_text_splitters import MarkdownTextSplitter

from databases.mongo import MongoClient
from databases.rabbitmq import RabbitClient
from models import DocSection
from utils.embedding import Embedding

router = APIRouter(
    prefix="/learning",
)

async def create_embbeding(file_path: str, filename: str):
    content = ""
    list_docs: list[DocSection] = []
    open_ai = AsyncOpenAI()
    # open the file
    with open(file_path, "r") as f:
            content = f.read()

    # splitting file
    with logfire.span('split_file'):
        md_splitter = MarkdownTextSplitter(chunk_size=1000, chunk_overlap=200)
        chunks = md_splitter.split_text(content)
        for chunk in chunks:
            chunk = f"{filename} {chunk}"
            try:
                # create embedding for each chunk
                embedding = await open_ai.embeddings.create(
                    input=chunk,
                    model='text-embedding-3-small',
                )
                list_docs.append(DocSection(group="ocbc-doc-tech", title=filename, content=chunk, embedding=embedding.data[0].embedding))
            except Exception as e:
                logfire.error(e)
        list_docs_dict = [doc.to_dict() for doc in list_docs]
        return list_docs_dict

@router.get("/sync", status_code=status.HTTP_200_OK)
async def get_learning():
    """Learing all documents in folder uploads/ocbc-doc-tech

    Returns:
        _type_: _description_
    """
    file_path = "./uploads/ocbc-doc-tech/01.intro.md"
    mongo_uri = get_key(".env", "MONGO_URI")
    if mongo_uri is None:
        logfire.error("MONGO_URI not found in .env file")
        return
    mongo_client = MongoClient(mongo_uri, "pyAgent")
    mongo_client.ping()
    emmbedding_pkg = Embedding()
    embeding_file = await emmbedding_pkg.generate_from_file(file_path, "01.intro.md")
    
    # col = mongo_client.get_collection("doc_sections")
    
    
    return {"message": "Learning", "file": file_path, "embeding_file": embeding_file}


@router.get("/async", status_code=status.HTTP_200_OK)
async def async_learning():
    """Learing all documents in folder asynchronously
    """
    folder_path = "./uploads/ocbc-doc-tech"
    mongo_uri = get_key(".env", "MONGO_URI")
    if mongo_uri is None:
        logfire.error("MONGO_URI not found in .env file")
        return
    mongo_client = MongoClient(mongo_uri, "pyAgent")
    mongo_client.ping()
    rabbit_client = RabbitClient(
        host=get_key(".env", "RABBIT_HOST"),
        port=get_key(".env", "RABBIT_PORT"),
        username=get_key(".env", "RABBIT_USER"),
        password=get_key(".env", "RABBIT_PASS")
    )
    
    # collection = mongo_client.get_collection("doc_sections")
    
    learning_files = [folder_path]
    
    # Itterate through the folder and its subfolders
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            file_path = os.path.join(root, file)
            rabbit_client.publish("learning.async",file_path)
            learning_files.append(file_path)
    
    
    return {"message": "Learning", "files": learning_files}