import requests

url = "http://127.0.0.1:8000/example/"

data = {
    "name": "Niilo",
    "task": "Test API"
}

response = requests.post(url, json=data)

print("Status:", response.status_code)
print("Response:", response.json())