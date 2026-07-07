import requests
import json
import time

GATEWAY_URL = "http://localhost:8000"
API_KEY = "o2to9a1cTd2uYgpsmO3j-qFvsafj9XjpQ_yhTB2Kk_k"

def test_chat_sync():
    print("\n--- Testing Synchronous Chat ---")
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "gpt-3.5-turbo",
        "messages": [{"role": "user", "content": "Hello, gateway!"}],
        "stream": False
    }
    
    response = requests.post(f"{GATEWAY_URL}/v1/chat/completions", headers=headers, json=payload)
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        print(f"Response: {response.json()['choices'][0]['message']['content']}")
    else:
        print(f"Error: {response.text}")

def test_chat_stream():
    print("\n--- Testing Streaming Chat ---")
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "gpt-3.5-turbo",
        "messages": [{"role": "user", "content": "Tell me a long story."}],
        "stream": True
    }
    
    response = requests.post(f"{GATEWAY_URL}/v1/chat/completions", headers=headers, json=payload, stream=True)
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        for line in response.iter_lines():
            if line:
                print(f"Stream Chunk: {line.decode('utf-8')}")
    else:
        print(f"Error: {response.text}")

def test_gemini_routing():
    print("\n--- Testing Gemini Routing ---")
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "gemini-1.5-pro",
        "messages": [{"role": "user", "content": "Hi Gemini!"}],
        "stream": False
    }
    
    response = requests.post(f"{GATEWAY_URL}/v1/chat/completions", headers=headers, json=payload)
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        print(f"Response: {response.json()['choices'][0]['message']['content']}")

if __name__ == "__main__":
    test_chat_sync()
    test_chat_stream()
    test_gemini_routing()
