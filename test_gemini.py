import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()  # load GEMINI_API_KEY from .env

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")

response = model.generate_content("Hello world")
print(response.text)
