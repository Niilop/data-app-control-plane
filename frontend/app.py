import json
import streamlit as st
import requests

# Configuration
API_URL = "http://backend:8000/"

# Initialize session state
if "access_token" not in st.session_state:
    st.session_state.access_token = None
if "active_conversation_id" not in st.session_state:
    st.session_state.active_conversation_id = None
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []   # list of {role, content}

def get_headers():
    if st.session_state.access_token:
        return {"Authorization": f"Bearer {st.session_state.access_token}"}
    return {}

st.set_page_config(page_title="DS API Tester", layout="wide")
st.title("🚀 DS API Tester")

# ==========================================
# Sidebar: Authentication
# ==========================================
with st.sidebar:
    st.header("Authentication")
    
    if st.session_state.access_token is None:
        auth_mode = st.radio("Choose Action", ["Login", "Register"])
        
        if auth_mode == "Login":
            with st.form("login_form"):
                email = st.text_input("Email")
                password = st.text_input("Password", type="password")
                submit = st.form_submit_button("Login")
                
                if submit:
                    # Note: OAuth2 expects form data (data=), not JSON
                    response = requests.post(
                        f"{API_URL}/auth/login",
                        data={"username": email, "password": password}
                    )
                    if response.status_code == 200:
                        st.session_state.access_token = response.json().get("access_token")
                        st.success("Logged in successfully!")
                        st.rerun()
                    else:
                        st.error(f"Login failed: {response.text}")
                        
        else:
            with st.form("register_form"):
                new_email = st.text_input("Email")
                new_username = st.text_input("Username")
                new_password = st.text_input("Password", type="password")
                submit = st.form_submit_button("Register")
                
                if submit:
                    response = requests.post(
                        f"{API_URL}/auth/register",
                        json={"email": new_email, "username": new_username, "password": new_password}
                    )
                    if response.status_code == 200:
                        st.success("Registration successful! You can now log in.")
                    else:
                        st.error(f"Registration failed: {response.text}")
    else:
        st.success("You are authenticated.")
        
        # Test the /me endpoint
        if st.button("Get My Profile"):
            response = requests.get(f"{API_URL}/auth/me", headers=get_headers())
            if response.status_code == 200:
                st.json(response.json())
            else:
                st.error("Failed to fetch profile. Token might be expired.")
                
        if st.button("Logout"):
            st.session_state.access_token = None
            st.rerun()

# ==========================================
# Main Content: Endpoint Testing
# ==========================================
tab1, tab2, tab3 = st.tabs(["Test Example Endpoint", "Test LLM Summarizer", "Chat"])

with tab1:
    st.header("Example Logic")
    st.write("Tests the `/example/` endpoint.")
    
    with st.form("example_form"):
        name_input = st.text_input("Your Name", value="Developer")
        task_input = st.text_input("Task", value="Test the connection")
        run_example = st.form_submit_button("Run Example")
        
        if run_example:
            with st.spinner("Processing..."):
                res = requests.post(
                    f"{API_URL}/example/", 
                    json={"name": name_input, "task": task_input}
                )
                if res.status_code == 200:
                    st.success(res.json().get("result"))
                else:
                    st.error(f"Error: {res.text}")

with tab2:
    st.header("AI Summarizer")
    st.write("Tests the `/llm/summarize/stream` endpoint. Note: The backend has a rate limit of 5 requests per minute.")

    with st.form("llm_form"):
        text_to_summarize = st.text_area("Text to summarize", height=150)
        run_llm = st.form_submit_button("Summarize")

    if run_llm:
        if not text_to_summarize:
            st.warning("Please enter some text first.")
        else:
            output = st.empty()
            full_response = ""
            try:
                with requests.post(
                    f"{API_URL}/llm/summarize/stream",
                    json={"text": text_to_summarize},
                    headers=get_headers(),
                    stream=True,
                    timeout=60,
                ) as res:
                    if res.status_code == 429:
                        st.error("Rate limit exceeded! Please wait a minute.")
                    elif res.status_code != 200:
                        st.error(f"Error: {res.text}")
                    else:
                        for line in res.iter_lines():
                            if not line:
                                continue
                            decoded = line.decode("utf-8")
                            if not decoded.startswith("data: "):
                                continue
                            data = decoded[6:]
                            if data == "[DONE]":
                                break
                            chunk = json.loads(data)
                            if chunk.startswith("[ERROR]"):
                                st.error(chunk)
                                break
                            full_response += chunk
                            output.info(full_response + " ▌")
                        output.info(full_response)
            except requests.exceptions.RequestException as e:
                st.error(f"Connection error: {e}")

with tab3:
    st.header("Chat")

    if st.session_state.access_token is None:
        st.info("Please log in from the sidebar to use the chat.")
    else:
        # ── Sidebar conversation list ────────────────────────────────────────
        with st.sidebar:
            st.divider()
            st.subheader("Conversations")

            if st.button("New conversation", use_container_width=True):
                st.session_state.active_conversation_id = None
                st.session_state.chat_messages = []
                st.rerun()

            res = requests.get(f"{API_URL}/chat/", headers=get_headers(), timeout=10)
            if res.status_code == 200:
                for conv in res.json():
                    label = f"{conv['title'][:32]}..." if len(conv["title"]) > 32 else conv["title"]
                    col_title, col_del = st.columns([5, 1])
                    with col_title:
                        if st.button(label, key=f"conv_{conv['id']}", use_container_width=True):
                            detail = requests.get(
                                f"{API_URL}/chat/{conv['id']}",
                                headers=get_headers(),
                                timeout=10,
                            )
                            if detail.status_code == 200:
                                data = detail.json()
                                st.session_state.active_conversation_id = conv["id"]
                                st.session_state.chat_messages = [
                                    {"role": m["role"], "content": m["content"]}
                                    for m in data["messages"]
                                ]
                                st.rerun()
                    with col_del:
                        if st.button("🗑", key=f"del_{conv['id']}"):
                            requests.delete(
                                f"{API_URL}/chat/{conv['id']}",
                                headers=get_headers(),
                                timeout=10,
                            )
                            if st.session_state.active_conversation_id == conv["id"]:
                                st.session_state.active_conversation_id = None
                                st.session_state.chat_messages = []
                            st.rerun()

        # ── Chat history ─────────────────────────────────────────────────────
        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        # ── Input ─────────────────────────────────────────────────────────────
        user_input = st.chat_input("Type a message...")
        if user_input:
            st.session_state.chat_messages.append({"role": "user", "content": user_input})
            with st.chat_message("user"):
                st.markdown(user_input)

            with st.chat_message("assistant"):
                placeholder = st.empty()
                placeholder.markdown("_Thinking..._")
                try:
                    if st.session_state.active_conversation_id is None:
                        # Start new conversation
                        res = requests.post(
                            f"{API_URL}/chat/",
                            json={"message": user_input},
                            headers=get_headers(),
                            timeout=60,
                        )
                    else:
                        res = requests.post(
                            f"{API_URL}/chat/{st.session_state.active_conversation_id}",
                            json={"message": user_input},
                            headers=get_headers(),
                            timeout=60,
                        )

                    if res.status_code == 200:
                        data = res.json()
                        reply = data["reply"]
                        st.session_state.active_conversation_id = data["conversation_id"]
                        st.session_state.chat_messages.append({"role": "assistant", "content": reply})
                        placeholder.markdown(reply)
                    elif res.status_code == 429:
                        placeholder.error("Rate limit exceeded. Please wait a moment.")
                    else:
                        placeholder.error(f"Error: {res.text}")
                except requests.exceptions.RequestException as e:
                    placeholder.error(f"Connection error: {e}")