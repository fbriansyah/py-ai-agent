import spacy
import logfire

from spacy_layout import spaCyLayout
from databases.mongo import MongoClient

from openai import AsyncOpenAI
from langchain_text_splitters import SpacyTextSplitter

class FileProcessor:
    mongo_client: MongoClient | None
    openai: AsyncOpenAI | None
    def __init__(self, file_path: str):
        self.file_path = file_path
    
    def with_open_ai(self, client: AsyncOpenAI):
        self.openai = client
        return self
    
    def with_mongo(self, client: MongoClient):
        self.mongo_client = client
        return self
        
    def process_file(self):
        nlp = spacy.blank("en")
        layout = spaCyLayout(nlp)
        logfire.info(f"Reading file {self.file_path}")
        # Process a document and create a spaCy Doc object
        doc = layout(self.file_path)
        logfire.info(f"Done reading file {self.file_path}")
        
        # Markdown representation of the document
        with logfire.span('process_file'):
            content = doc._.markdown
            chunks = SpacyTextSplitter(chunk_size=1000, chunk_overlap=200).split_text(content)
            for chunk in chunks:
                print(chunk)