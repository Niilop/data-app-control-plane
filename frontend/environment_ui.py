"""Explicit simulated environments and versioned application bindings."""

import streamlit as st
from api_client import APIClient
from registry_widgets import changed, page


def render_environments(client: APIClient, profile: dict) -> None:
    st.subheader("Environments")
    st.info(
        "Simulated environments — no workspace connection or deployment is performed."
    )
    environments = page(client, "/api/v1/environments", "environments")
    if environments:
        environment = st.selectbox(
            "Environment", environments, format_func=lambda row: row["name"]
        )
        st.json(environment)
        if profile["is_platform_admin"]:
            environment_id = environment["id"]
            version_key = f"registry_environment_version_{environment_id}"
            st.session_state.setdefault(version_key, environment["version"])
            with st.form(f"environment_edit_{environment_id}"):
                name = st.text_input("Environment name", value=environment["name"])
                workspace = st.text_input(
                    "Simulated workspace reference", value=environment["workspace_ref"]
                )
                targets = st.text_input(
                    "Approved bundle targets (comma separated)",
                    value=", ".join(environment["allowed_bundle_targets"]),
                )
                enabled = st.checkbox(
                    "Enabled for bindings", value=environment["enabled"]
                )
                self_approval = st.checkbox(
                    "Allow local self-approval",
                    value=environment["allow_self_approval"],
                )
                st.caption(
                    "Saving changes increments the environment and all affected binding versions. Removed targets remain in history but become unusable."
                )
                if st.form_submit_button("Save environment"):
                    client.request(
                        "PATCH",
                        f"/api/v1/environments/{environment_id}",
                        data={
                            "expected_version": st.session_state[version_key],
                            "name": name,
                            "workspace_ref": workspace,
                            "allowed_bundle_targets": [
                                target.strip() for target in targets.split(",")
                            ],
                            "enabled": enabled,
                            "allow_self_approval": self_approval,
                        },
                    )
                    st.session_state.pop(version_key, None)
                    changed(
                        "Environment policy saved; affected binding versions updated."
                    )
            if st.button("Reload environment version"):
                st.session_state.pop(version_key, None)
                st.rerun()
    else:
        st.info(
            "No visible environments. An administrator can create a simulated environment and bind it to an application."
        )
    if profile["is_platform_admin"]:
        with st.expander("Create simulated environment", expanded=not environments):
            with st.form("create_environment"):
                name = st.text_input("New environment name", value="local-sandbox")
                workspace = st.text_input(
                    "New simulated workspace reference",
                    value="simulated://local-sandbox",
                )
                targets = st.text_input("New approved bundle targets", value="sandbox")
                self_approval = st.checkbox(
                    "Allow self-approval in this local simulation", value=False
                )
                if st.form_submit_button("Create simulated environment"):
                    client.request(
                        "POST",
                        "/api/v1/environments",
                        data={
                            "name": name,
                            "workspace_ref": workspace,
                            "allowed_executor": "simulated",
                            "enabled": True,
                            "allow_self_approval": self_approval,
                            "allowed_bundle_targets": [
                                target.strip() for target in targets.split(",")
                            ],
                        },
                    )
                    changed("Simulated environment created.")


def config_fields(config: dict) -> dict:
    rows = st.number_input(
        "Synthetic row count",
        min_value=1,
        max_value=10000,
        value=config.get("synthetic_row_count", 100),
    )
    timeout = st.number_input(
        "Maximum runtime (seconds)",
        min_value=1,
        max_value=3600,
        value=config.get("max_runtime_seconds", 300),
    )
    return {
        "schema_version": 1,
        "synthetic_row_count": rows,
        "max_runtime_seconds": timeout,
    }


def render_bindings(client: APIClient, application_id: str, profile: dict) -> None:
    st.subheader("Environment bindings")
    st.caption(
        "Simulated only. Configuration records preparation settings; nothing runs yet."
    )
    path = f"/api/v1/applications/{application_id}/bindings"
    bindings = page(client, path, f"bindings_{application_id}")
    for binding in bindings:
        environment = binding["environment"]
        with st.expander(
            f"{environment['name']} / {binding['bundle_target']} · simulated",
            expanded=True,
        ):
            st.caption(
                f"Binding ID: {binding['id']} · Version {binding['version']} · Environment version {environment['version']}"
            )
            st.write(f"Workspace reference: {environment['workspace_ref']}")
            st.write(
                f"Local self-approval: {'allowed' if environment['allow_self_approval'] else 'disabled'}"
            )
            st.json(binding["config"])
            if not binding["usable"]:
                st.warning(
                    "Binding is unavailable: the environment is disabled, its target was removed, or the application is archived."
                )
            if profile["is_platform_admin"]:
                key = f"registry_binding_version_{binding['id']}"
                st.session_state.setdefault(key, binding["version"])
                with st.form(f"edit_binding_{binding['id']}"):
                    targets = environment["allowed_bundle_targets"]
                    index = (
                        targets.index(binding["bundle_target"])
                        if binding["bundle_target"] in targets
                        else 0
                    )
                    target = st.selectbox(
                        "Approved bundle target", targets, index=index
                    )
                    config = config_fields(binding["config"])
                    if st.form_submit_button(
                        "Save binding", disabled=not environment["enabled"]
                    ):
                        client.request(
                            "PATCH",
                            path + f"/{binding['id']}",
                            data={
                                "expected_version": st.session_state[key],
                                "bundle_target": target,
                                "config": config,
                            },
                        )
                        st.session_state.pop(key, None)
                        changed("Binding saved.")
                if st.button(
                    "Reload binding version", key=f"reload_binding_{binding['id']}"
                ):
                    st.session_state.pop(key, None)
                    st.rerun()
    if profile["is_platform_admin"]:
        with st.expander("Bind an environment"):
            environments = page(
                client, "/api/v1/environments", f"binding_environments_{application_id}"
            )
            enabled = [
                environment for environment in environments if environment["enabled"]
            ]
            if not enabled:
                st.info(
                    "No enabled environments on this page. Create one in Environments or advance to another page."
                )
                return
            # The selector lives outside the form so changing environments refreshes targets.
            environment = st.selectbox(
                "Environment to bind",
                enabled,
                format_func=lambda row: row["name"],
                key=f"bind_environment_{application_id}",
            )
            with st.form(f"create_binding_{application_id}"):
                target = st.selectbox(
                    "Bundle target", environment["allowed_bundle_targets"]
                )
                config = config_fields({})
                if st.form_submit_button("Create binding"):
                    client.request(
                        "POST",
                        path,
                        data={
                            "environment_id": environment["id"],
                            "bundle_target": target,
                            "config": config,
                        },
                    )
                    changed("Simulated environment binding created.")
