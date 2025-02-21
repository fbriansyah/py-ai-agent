
from pymongo import AsyncMongoClient
# from pymongo.server_api import ServerApi
from openai import AsyncOpenAI

class MongoClient:
    open_ai_client: AsyncOpenAI | None
    db_name: str
    def __init__(self, uri: str, db_name: str):
        self.client = AsyncMongoClient(uri)
        self.db_name = db_name
    def setup_openai(self, client: AsyncOpenAI):
        self.open_ai_client = client
        
    def get_database(self, database_name: str):
        return self.client[database_name]
    
    def get_collection(self, collection_name: str):
        db = self.client[self.db_name]
        return db[collection_name]

    def ping(self):
        try:
            # Send a ping to confirm a successful connection
            self.client.admin.command('ping')
            print("Pinged your deployment. You successfully connected to MongoDB!")
        except Exception as e:
            print(e)

    def vector_search(self, collection_name: str, pipeline: list):
        coll = self.client[collection_name]
        return coll.aggregate(pipeline)

