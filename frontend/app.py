"""Development login and service status for the data application control plane."""

import os
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
API_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
REQUEST_TIMEOUT = 10


def get_headers() -> dict[str, str]:
    """Return the current development session's authorization header."""
    token = st.session_state.get("access_token")
    return {"Authorization": f"Bearer {token}"} if token else {}


st.set_page_config(page_title="Data Application Control Plane", layout="wide")
st.title("Data Application Control Plane")
st.caption("Local development")
st.session_state.setdefault("access_token", None)

with st.sidebar:
    st.header("Development account")
    if st.session_state.access_token is None:
        mode = st.radio("Account action", ["Login", "Register"])
        with st.form("account_form"):
            identifier = st.text_input(
                "Email or username" if mode == "Login" else "Email"
            )
            username = st.text_input("Username") if mode == "Register" else ""
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button(mode)
        if submitted:
            try:
                if mode == "Login":
                    response = requests.post(
                        f"{API_URL}/auth/login",
                        data={"username": identifier, "password": password},
                        timeout=REQUEST_TIMEOUT,
                    )
                    if response.status_code == 200:
                        st.session_state.access_token = response.json()["access_token"]
                        st.rerun()
                    else:
                        st.error("Login failed. Check your credentials.")
                else:
                    response = requests.post(
                        f"{API_URL}/auth/register",
                        json={
                            "email": identifier,
                            "username": username,
                            "password": password,
                        },
                        timeout=REQUEST_TIMEOUT,
                    )
                    if response.status_code == 200:
                        st.success("Account created. Select Login to continue.")
                    else:
                        st.error(
                            "Registration failed. Check the fields or use another account."
                        )
            except (requests.RequestException, ValueError, KeyError):
                st.error("Unable to complete the request. Check the API connection.")
    else:
        st.success("Signed in")
        if st.button("Logout"):
            st.session_state.access_token = None
            st.rerun()

st.header("Service status")
if st.button("Check API health"):
    try:
        response = requests.get(f"{API_URL}/health", timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        if response.json().get("status") == "ok":
            st.success("API is running.")
        else:
            st.error("API returned an unexpected health response.")
    except (requests.RequestException, ValueError):
        st.error("API is unavailable.")

if st.session_state.access_token:
    if st.button("View my profile"):
        try:
            response = requests.get(
                f"{API_URL}/auth/me", headers=get_headers(), timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            st.json(response.json())
        except (requests.RequestException, ValueError):
            st.error(
                "Unable to load your profile. Check the connection or log in again."
            )
else:
    st.info("Sign in using the sidebar.")
