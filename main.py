import uvicorn
import logging
# setup fastapi
from fastapi import FastAPI

# load the config from dot env file
from dotenv import load_dotenv, get_key
load_dotenv()

app = FastAPI()
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
