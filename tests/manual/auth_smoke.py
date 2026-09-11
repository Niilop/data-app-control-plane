#!/usr/bin/env python3
import requests
import json
from datetime import datetime

BASE_URL = "http://127.0.0.1:8000"

# Test register
timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
user_data = {
    "email": f"test{timestamp}@example.com",
    "username": f"testuser{timestamp}",
    "password": "pass123"
}

print("Testing registration...")
print(f"Payload: {json.dumps(user_data, indent=2)}")

try:
    response = requests.post(f"{BASE_URL}/auth/register", json=user_data)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
except Exception as e:
    print(f"Error: {e}")

# If registration successful, test login
if response.status_code == 200:
    print("\nTesting login...")
    
    # OAuth2 standard uses 'username' as the key, even if you are passing an email
    login_payload = {
        "username": user_data["email"], 
        "password": user_data["password"]
    }
    
    try:
        # Change 'json=login_data' to 'data=login_payload'
        response = requests.post(f"{BASE_URL}/auth/login", data=login_payload)
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    except Exception as e:
        print(f"Error: {e}")

if response.status_code == 200:
    token = response.json().get("access_token")
    print("\nTesting 'Get Me' endpoint...")
    
    # We must pass the token in the Headers, not the Body
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    try:
        response = requests.get(f"{BASE_URL}/auth/me", headers=headers)
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    except Exception as e:
        print(f"Error: {e}")