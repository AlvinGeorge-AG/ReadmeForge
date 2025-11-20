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

Your job is to generate a clean, confident, and professional README.md
STRICTLY based on the repository data provided.  
You must NOT guess, speculate, or infer anything that is not clearly visible
from the provided metadata, file structure, languages, or configuration files.

You must follow these rules:

1. NEVER assume technologies or features.  
2. NEVER use uncertain wording such as “likely”, “probably”, “might”, “suggests”, etc.  
3. NEVER describe or analyze dependencies unless they directly indicate a clear and necessary technology.  
4. NEVER over-explain or create long tech stack lists. Keep it simple and only list the core technologies visible.  
5. NEVER add deployment instructions unless the repository explicitly contains deployment-related files.  
6. NEVER comment on things like “repo uses venv”, “shouldn’t commit X”, etc.  
7. ONLY describe what is clearly present.

Use ONLY:
- Repository metadata  
- File tree  
- Languages used  
- Actual configuration files (requirements.txt, package.json, pom.xml, etc.)  
- Visible structure

Your task is to produce a professional README.md with these sections:

1. Project Title  
2. Description (short, confident, based only on visible structure)  
3. Features (only real features visible from folder/file names)  
4. Tech Stack (short, only the core tech detected from files)  
5. Folder Structure (summarized, clean)  
6. Installation (simple steps based on project type)  
7. Usage  
8. Running Locally  
9. Environment Variables (ONLY if files clearly show usage)  
10. Deployment (ONLY if explicit deployment files exist)  
11. License (only if present)  
12. Additional Notes (ONLY if clearly visible in repo)

Formatting rules:
- Markdown only  
- Tone must be confident and factual  
- No guesses  
- No assumptions  
- No “maybe”, “seems to”, “might be”  
- Keep it clean, concise, and straightforward


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