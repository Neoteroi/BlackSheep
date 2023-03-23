from pprint import pprint

from blacksheep import Application

app = Application()


@app.after_start
async def log_routes(_):
    pprint(app.router.routes)


@app.router.get("/")
def home():
    return "Home"


@app.router.get("/", headers={"X-Area": "51"})
def secret_home():
    return "Boo"


@app.router.get("/another")
def another():
    return "Another"


@app.router.get("/{param}")
def echo(param):
    return param


@app.router.get("/another", headers={"X-Area": "51"})
def secret_another():
    return "Another Secret"


@app.router.get("/{param}", headers={"X-Area": "51"})
def echo2(param):
    return param + " 51"


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=44777, log_level="debug", lifespan="on")
