from fastapi import FastAPI ,HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
import httpx
import os
import json

load_dotenv()

API_KEY = os.getenv("API_KEY")
MODEL = os.getenv("MODEL")

if not API_KEY or not MODEL :
    raise RuntimeError("API KEY OR MODEL NOT FOUND!")

GEMINI_URL = f"https://generativelanguage.googleapis.com/v1/models/{MODEL}:generateContent?key={API_KEY}"

app = FastAPI(title="FastAPI BACKEND",version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class GitHubLink(BaseModel):
    link : str

GITHUB_SYSTEM_PROMPT = """
You are an expert technical writer and GitHub repository analyzer.

Your ONLY job is to analyze the repository data PROVIDED TO YOU in the input.
Do NOT analyze the user’s GitHub profile.
Do NOT infer anything that is not explicitly present in the provided repository structure or metadata.
Do NOT search the internet or assume external information.

Use ONLY the following inputs:
- Repository metadata (description, stars, topics, default branch, etc.)
- File tree structure (full recursive list)
- Languages used
- File names and directory organization
- Configuration files if included (requirements.txt, package.json, etc.)

Your task is to understand:
- What the project most likely does (based on file/folder names)
- What tech stack it uses
- How it works internally
- Features visible from code structure
- Installation and setup steps (based on typical patterns)
- Deployment steps (infer ONLY from files present)
- How to run the project locally (based on common conventions)

Using this analysis, generate a clean, professional, COMPLETE `README.md` with the following sections:

1. Project Title
2. Description (based only on repo content)
3. Features
4. Tech Stack
5. Folder Structure (summarized from file tree)
6. Installation
7. Usage
8. Environment Variables (only if detectable)
9. Running Locally
10. Build/Deploy (only if detectable)
11. Contributing
12. License (if present in repo)
13. Any additional important notes

Rules:
- DO NOT hallucinate technologies or features not directly visible.
- DO NOT rely on README.md because it is intentionally not provided.
- BASE ALL ANSWERS strictly on file names, structure, and metadata.
- Format the entire output in valid Markdown.


"""



@app.get("/")
async def home():
    return {"prompt":"Yesss FASTAPI is running!!!"}

def extract_user_repo(link: str):
    # Normalize missing schema
    if not link.startswith("http"):
        link = "https://" + link

    link = link.rstrip("/")
    link = link.replace(".git", "")

    parts = link.split("/")

    if len(parts) < 2:
        raise ValueError("Invalid GitHub URL")

    user = parts[-2]
    repo = parts[-1]

    return user, repo




async def analyser(link:str):
    username , repo = extract_user_repo(link)
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            basic_data = await client.get(f"https://api.github.com/repos/{username}/{repo}")
            user_json = basic_data.json()
            repo_data = await client.get(f"https://api.github.com/repos/{username}/{repo}/git/trees/{user_json['default_branch']}?recursive=1")
            lang = await client.get(f"https://api.github.com/repos/{username}/{repo}/languages")


            
            repo_json = repo_data.json()
            lang_json = lang.json()
            return {
                "basic_data": user_json,
                "repo":repo_json,
                "lang":lang_json
            }
    except Exception as e:
        print("ERROR DETAILS:", str(e))
        raise HTTPException(status_code=500, detail=str(e))   


@app.post("/chat")
async def chat(data:GitHubLink):
    git_data = await analyser(data.link)
    payload = {
        "contents": [
            {   
                
                "parts": [
                    {"text": GITHUB_SYSTEM_PROMPT},
                     {"text": "Here is the GitHub Repository data:\n"
                        + "Basic_data:\n\n" + json.dumps(git_data["basic_data"], indent=2) +
                         "\n\nRepo data : \n\n"+json.dumps(git_data["repo"],indent=2)+
                        "\n\nLanguages used : \n\n"+json.dumps(git_data["lang"],indent=2)}

                ]
            }
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                GEMINI_URL,
                json=payload,
                headers={"Content-Type": "application/json"}
                )
            
            response.raise_for_status()
            result = response.json()

        reply = result["candidates"][0]["content"]["parts"][0]["text"]

        #print("GEMINI RAW RESPONSE:", reply)
        return {"readme": reply}

        

    except Exception as e:
        print("ERROR DETAILS:", str(e))
        print("RAW RESPONSE:", response.text if 'response' in locals() else 'no response')
        raise HTTPException(status_code=500, detail=str(e))