"""Owned application registration, detail/history and local administration."""

import streamlit as st
from api_client import APIClient, APIError
from environment_ui import render_bindings, render_environments
from registry_widgets import changed, page


def application_detail(client: APIClient, application_id: str, profile: dict) -> None:
    path = f"/api/v1/applications/{application_id}"
    application = client.request("GET", path)
    st.subheader(application["name"])
    st.caption(
        f"Application ID: {application['id']} · Version {application['version']} · {application['lifecycle']}"
    )
    st.write(application["description"])
    st.write(f"Owning team: {application['owning_team_id']}")
    st.write(
        f"Owner user ID: {application['owner_user_id']} · Data owner user ID: {application['data_owner_user_id']}"
    )
    st.write(
        f"Repository: {application['repository_url']} · Bundle root: {application['bundle_root']}"
    )
    st.warning(
        "Repository unverified — registration does not check repository access or contents."
    )
    with st.expander("Edit metadata (developer role required)"):
        with st.form(f"metadata_{application_id}"):
            # Keep the version from when the form was displayed, across submit reruns.
            version_key = f"registry_version_{application_id}"
            st.session_state.setdefault(version_key, application["version"])
            name = st.text_input("Application name", value=application["name"])
            description = st.text_area("Description", value=application["description"])
            repository = st.text_input(
                "Repository URL", value=application["repository_url"]
            )
            root = st.text_input("Bundle root", value=application["bundle_root"])
            if st.form_submit_button("Save metadata"):
                client.request(
                    "PATCH",
                    path,
                    data={
                        "expected_version": st.session_state[version_key],
                        "name": name,
                        "description": description,
                        "repository_url": repository,
                        "bundle_root": root,
                    },
                )
                st.session_state.pop(version_key, None)
                changed("Metadata saved.")
        if st.button("Reload metadata version", key=f"reload_{application_id}"):
            st.session_state.pop(version_key, None)
            st.rerun()
    manager = (
        profile["is_platform_admin"] or profile["id"] == application["owner_user_id"]
    )
    if manager:
        with st.expander("Manage ownership"):
            with st.form(f"ownership_{application_id}"):
                ownership_version_key = f"registry_ownership_version_{application_id}"
                st.session_state.setdefault(
                    ownership_version_key, application["version"]
                )
                team_id = st.text_input(
                    "Owning team ID", value=application["owning_team_id"]
                )
                owner = st.number_input(
                    "Owner user ID", min_value=1, value=application["owner_user_id"]
                )
                data_owner = st.number_input(
                    "Data owner user ID",
                    min_value=1,
                    value=application["data_owner_user_id"],
                )
                if st.form_submit_button("Save ownership"):
                    client.request(
                        "PATCH",
                        path,
                        data={
                            "expected_version": st.session_state[ownership_version_key],
                            "owning_team_id": team_id,
                            "owner_user_id": owner,
                            "data_owner_user_id": data_owner,
                        },
                    )
                    st.session_state.pop(ownership_version_key, None)
                    changed("Ownership saved.")
            if st.button(
                "Reload ownership version", key=f"reload_owner_{application_id}"
            ):
                st.session_state.pop(ownership_version_key, None)
                st.rerun()
    st.subheader("Role assignments")
    roles = page(client, path + "/roles", f"roles_{application_id}")
    st.dataframe(roles, hide_index=True)
    if manager:
        with st.form(f"grant_{application_id}"):
            kind = st.selectbox("Subject kind", ["user", "team"])
            subject = st.text_input("Subject ID")
            role = st.selectbox(
                "Platform role", ["viewer", "developer", "approver", "operator"]
            )
            if st.form_submit_button("Assign role"):
                value = int(subject) if kind == "user" else subject
                client.request(
                    "POST", path + "/roles", data={f"{kind}_id": value, "role": role}
                )
                changed("Role assigned.")
        if roles:
            assignment = st.selectbox(
                "Assignment to revoke",
                roles,
                format_func=lambda row: (
                    f"{row['role']} · user {row['user_id']} · team {row['team_id']}"
                ),
            )
            if st.button("Revoke assignment"):
                client.request("DELETE", path + f"/roles/{assignment['id']}")
                changed(
                    "Assignment revoked. Other direct or team assignments may still grant access."
                )
    render_bindings(client, application_id, profile)
    st.subheader("Application history")
    st.json(page(client, path + "/audit-events", f"audit_{application_id}"))


def register_application(client: APIClient, profile: dict) -> None:
    st.caption(
        "Choose one of your teams. Account IDs are shown on each user's profile; an administrator manages membership."
    )
    teams = page(client, "/api/v1/teams", "registration_teams")
    if not teams:
        st.info("Ask a platform administrator to create a team and add your user ID.")
        return
    with st.form("register_application"):
        slug = st.text_input("Slug")
        name = st.text_input("Name")
        description = st.text_area("Application description")
        team = st.selectbox("Owning team", teams, format_func=lambda row: row["name"])
        owner = st.number_input(
            "Accountable owner user ID", min_value=1, value=profile["id"]
        )
        data_owner = st.number_input(
            "Accountable data owner user ID", min_value=1, value=profile["id"]
        )
        repository = st.text_input(
            "GitHub repository URL", placeholder="https://github.com/owner/repository"
        )
        root = st.text_input("Relative bundle root", value=".")
        st.caption(
            "The repository will be recorded as unverified. You receive developer and viewer roles."
        )
        if st.form_submit_button("Register application"):
            created = client.request(
                "POST",
                "/api/v1/applications",
                data={
                    "slug": slug,
                    "name": name,
                    "description": description,
                    "owning_team_id": team["id"],
                    "owner_user_id": owner,
                    "data_owner_user_id": data_owner,
                    "repository_url": repository,
                    "bundle_root": root,
                },
            )
            changed(
                f"Application registered: {created['id']}. Find it under Applications."
            )


def team_admin(client: APIClient, profile: dict) -> None:
    teams = page(client, "/api/v1/teams", "teams")
    st.dataframe(teams, hide_index=True)
    if teams:
        team = st.selectbox("Team", teams, format_func=lambda row: row["name"])
        st.dataframe(
            page(
                client, f"/api/v1/teams/{team['id']}/members", f"members_{team['id']}"
            ),
            hide_index=True,
        )
    if not profile["is_platform_admin"]:
        return
    with st.form("create_team"):
        name = st.text_input("New team name")
        if st.form_submit_button("Create team"):
            client.request("POST", "/api/v1/teams", data={"name": name})
            changed("Team created.")
    if teams:
        with st.form("membership"):
            user_id = st.number_input("Member user ID", min_value=1, step=1)
            action = st.selectbox("Membership action", ["Add", "Remove"])
            if st.form_submit_button("Apply membership change"):
                path = f"/api/v1/teams/{team['id']}/members"
                if action == "Add":
                    client.request("POST", path, data={"user_id": user_id})
                else:
                    client.request("DELETE", path + f"/{user_id}")
                changed("Membership updated.")
    st.subheader("Administration history")
    st.json(page(client, "/api/v1/audit-events", "admin_audit"))


def render_registry(api_url: str, token: str) -> None:
    client = APIClient(api_url, token)
    try:
        profile = client.request("GET", "/auth/me")
        st.caption(f"Signed in as {profile['username']} · User ID: {profile['id']}")
        if "registry_message" in st.session_state:
            st.success(st.session_state.pop("registry_message"))
        view = st.radio(
            "Registry",
            ["Applications", "Register application", "Teams", "Environments"],
            horizontal=True,
        )
        if view == "Register application":
            register_application(client, profile)
        elif view == "Teams":
            team_admin(client, profile)
        elif view == "Environments":
            render_environments(client, profile)
        else:
            applications = page(client, "/api/v1/applications", "applications")
            if not applications:
                st.info("No visible applications on this page.")
            else:
                application = st.selectbox(
                    "Application",
                    applications,
                    format_func=lambda row: f"{row['name']} ({row['slug']})",
                )
                application_detail(client, application["id"], profile)
    except (APIError, ValueError) as exc:
        st.error(
            str(exc) if isinstance(exc, APIError) else "Enter a valid numeric user ID."
        )
