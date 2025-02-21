import logfire

from openai import AsyncOpenAI
from langchain_text_splitters import MarkdownTextSplitter

from models import DocSection

class Embedding:
    open_ai: AsyncOpenAI
    def __init__(self):
        self.open_ai = AsyncOpenAI()
    
    async def generate_from_file(self, file_path: str, filename: str):
        content = ""
        list_docs: list[DocSection] = []
        # open the file
        with open(file_path, "r") as f:
            if filename == "":
                filename = f.name
            content = f.read()

        # splitting file
        with logfire.span('split_file'):
            md_splitter = MarkdownTextSplitter(chunk_size=1000, chunk_overlap=200)
            chunks = md_splitter.split_text(content)
            for chunk in chunks:
                try:
                    # create embedding for each chunk
                    embedding = await self.open_ai.embeddings.create(
                        input=f"{filename} {chunk}",
                        model='text-embedding-3-small',
                    )
                    list_docs.append(DocSection(group="ocbc-doc-tech", title=filename, content=chunk, embedding=embedding.data[0].embedding))
                except Exception as e:
                    logfire.error(e)
            list_docs_dict = [doc.to_dict() for doc in list_docs]
            return list_docs_dict