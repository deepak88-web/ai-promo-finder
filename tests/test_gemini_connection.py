
import os
from dotenv import load_dotenv
from google import genai

# Load API key from .env
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("GEMINI_API_KEY not found in .env")

# Initialize Gemini client
client = genai.Client(api_key=api_key)

# Test a simple request
try:
    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents="Reply with exactly: Gemini connection successful"
    )

    print("SUCCESS:")
    print(response.text)

except Exception as e:
    print("FAILED:")
    print(type(e).__name__, e)
