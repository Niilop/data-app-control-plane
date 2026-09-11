"""Shared registry pagination and mutation feedback."""

import streamlit as st
from api_client import APIClient


def page(client: APIClient, path: str, key: str) -> list[dict]:
    cursor_key = f"registry_cursor_{key}"
    data = client.request(
        "GET", path, params={"limit": 20, "cursor": st.session_state.get(cursor_key)}
    )
    left, right = st.columns(2)
    if left.button(
        "First page", key=f"{key}_first", disabled=not st.session_state.get(cursor_key)
    ):
        st.session_state.pop(cursor_key, None)
        st.rerun()
    if right.button("Next page", key=f"{key}_next", disabled=not data["next_cursor"]):
        st.session_state[cursor_key] = data["next_cursor"]
        st.rerun()
    return data["items"]


def changed(message: str) -> None:
    st.session_state.registry_message = message
    st.rerun()
