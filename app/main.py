from fastapi import FastAPI

app = FastAPI(titl= "Cubico Ai Assistant")

@app.get("/")
def read_root():
    return {"status": "ok",
            "message":"Cubico  assistant esta vivo"}

