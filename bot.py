import os
import openai
import requests
from config import OPENAI_API_KEY, YOUTUBE_API_KEY

openai.api_key = OPENAI_API_KEY

def chat_with_gpt(prompt):
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )
    return response['choices'][0]['message']['content']

def search_youtube(query):
    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={query}&key={YOUTUBE_API_KEY}&type=video&maxResults=1"
    res = requests.get(url).json()
    if res['items']:
        video = res['items'][0]
        video_id = video['id']['videoId']
        title = video['snippet']['title']
        return f"🎵 {title}\nhttps://www.youtube.com/watch?v={video_id}"
    else:
        return "No results found."

def main():
    print("🤖 Welcome to AI Music Chat Bot!")
    while True:
        user_input = input("\nYou: ")
        if user_input.lower().startswith("play "):
            query = user_input[5:]
            print(search_youtube(query))
        else:
            print("ChatGPT:", chat_with_gpt(user_input))

if __name__ == "__main__":
    main()
