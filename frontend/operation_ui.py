"""Operation history, freshness and explicit recovery controls via HTTP."""

from uuid import uuid4

import streamlit as st
from api_client import APIClient
from registry_widgets import changed, page


def render_operations(client: APIClient, application_id: str) -> None:
    st.subheader("Operations")
    st.caption("Simulated execution. Refresh to observe worker progress.")
    if st.button("Refresh operations", key=f"refresh_ops_{application_id}"):
        st.rerun()
    operations = page(
        client,
        f"/api/v1/applications/{application_id}/operations",
        f"ops_{application_id}",
    )
    if not operations:
        st.info("No operations recorded.")
    for operation in operations:
        identifier = operation["id"]
        with st.expander(f"{operation['kind']} · {operation['status']} · {identifier}"):
            # Detail read provides a fresh state even when list pagination is old.
            current = client.request("GET", f"/api/v1/operations/{identifier}")
            st.write(
                f"Status: {current['status']} · Attempts: {current['attempt_count']}/{current['max_attempts']}"
            )
            st.caption(
                f"Observed: {current['observed_at'] or 'Not yet observed'} · Heartbeat: {current['heartbeat_at'] or 'None'} · Lease expires: {current['lease_expires_at'] or 'None'}"
            )
            if current["diagnostic_code"]:
                st.warning(current["diagnostic_code"].replace("_", " "))
            if current["cancel_requested"]:
                st.info(
                    "Cancellation requested. Running or uncertain work needs a worker observation."
                )
            attempts = page(
                client,
                f"/api/v1/operations/{identifier}/attempts",
                f"attempts_{identifier}",
            )
            if attempts:
                st.dataframe(attempts, hide_index=True)
            st.caption("Recovery actions require an explicit operator role.")
            actions = (
                ["cancel"]
                if current["status"]
                in {"queued", "running", "retry_wait", "reconciling"}
                else []
            )
            if current["status"] in {"failed", "cancelled"}:
                actions.append("retry")
            if current["status"] == "needs_attention":
                actions.append("reconcile")
            for action in actions:
                data = {}
                if action == "reconcile":
                    data["evidence"] = st.text_input(
                        "Reason to reconcile (no secrets)", key=f"evidence_{identifier}"
                    )
                if st.button(
                    action.capitalize(),
                    key=f"{action}_{identifier}",
                    disabled=action == "reconcile" and not data["evidence"].strip(),
                ):
                    # Retain key on transport failure; rotate only for a changed payload
                    # or a subsequent command after acknowledged success.
                    key_name = f"operation_command_{identifier}_{action}"
                    saved = st.session_state.get(key_name)
                    if not saved or saved[0] != data:
                        saved = (data, str(uuid4()))
                        st.session_state[key_name] = saved
                    result = client.request(
                        "POST",
                        f"/api/v1/operations/{identifier}/{action}",
                        data=data,
                        idempotency_key=saved[1],
                    )
                    st.session_state.pop(key_name, None)
                    changed(f"Operation {result['operation_id']}: {result['status']}")
