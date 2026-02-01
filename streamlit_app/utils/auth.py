"""Authentication utilities for Streamlit"""
import streamlit as st
import json
import base64
from datetime import datetime, timezone
from pathlib import Path

# Session persistence file (enabled so browser refresh does not log out)
SESSION_FILE = Path.home() / ".macad_session"
ENABLE_SESSION_PERSISTENCE = True


def save_session():
    """Save session to file for persistence across browser refreshes"""
    if not ENABLE_SESSION_PERSISTENCE:
        return
    token = st.session_state.get("access_token")
    if token:
        session_data = {
            "access_token": token,
            "user_email": st.session_state.get("user_email"),
            "user_role": st.session_state.get("user_role"),
            "user_id": st.session_state.get("user_id")
        }
        try:
            with open(SESSION_FILE, 'w') as f:
                json.dump(session_data, f)
            print(f"Session saved: {session_data['user_email']}")
        except Exception as e:
            print(f"Failed to save session: {e}")


def load_session():
    """Load session from file if exists"""
    if not ENABLE_SESSION_PERSISTENCE:
        if SESSION_FILE.exists():
            try:
                SESSION_FILE.unlink()
            except Exception as e:
                print(f"Failed to delete session file: {e}")
        return
    if SESSION_FILE.exists():
        try:
            with open(SESSION_FILE, 'r') as f:
                session_data = json.load(f)
            # Restore to session state - use attribute assignment
            st.session_state.access_token = session_data.get("access_token")
            st.session_state.user_email = session_data.get("user_email")
            st.session_state.user_role = session_data.get("user_role")
            st.session_state.user_id = session_data.get("user_id")
            # If role missing or stale, set from JWT so admin works (e.g. role stored as ADMIN)
            token = session_data.get("access_token")
            if token:
                payload = _decode_jwt_payload(token)
                if payload and payload.get("role"):
                    st.session_state.user_role = (payload.get("role") or "").strip()
            print(f"Session loaded for: {session_data.get('user_email')}")
        except Exception as e:
            print(f"Failed to load session: {e}")


def is_authenticated() -> bool:
    """Check if user is authenticated"""
    token = st.session_state.get("access_token")
    if not token:
        return False
    return not is_token_expired(token)


def _decode_jwt_payload(token: str) -> dict:
    """Decode JWT payload without verifying signature."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        payload_segment = parts[1]
        padding = "=" * (-len(payload_segment) % 4)
        payload_segment += padding
        decoded = base64.urlsafe_b64decode(payload_segment.encode("utf-8"))
        return json.loads(decoded.decode("utf-8"))
    except Exception:
        return {}


def is_token_expired(token: str) -> bool:
    """Check if JWT token is expired based on exp claim."""
    payload = _decode_jwt_payload(token)
    exp = payload.get("exp")
    if not exp:
        return False
    try:
        expiry = datetime.fromtimestamp(exp, tz=timezone.utc)
        return datetime.now(timezone.utc) >= expiry
    except Exception:
        return False


def is_admin() -> bool:
    """Check if current user is admin (case-insensitive: admin, ADMIN)."""
    role = (st.session_state.get("user_role") or "").strip()
    return role.upper() == "ADMIN"


def logout():
    """Logout user and clear saved session"""
    if "access_token" in st.session_state:
        del st.session_state.access_token
    if "user_email" in st.session_state:
        del st.session_state.user_email
    if "user_role" in st.session_state:
        del st.session_state.user_role
    if "user_id" in st.session_state:
        del st.session_state.user_id
    
    # Clear saved session file
    if SESSION_FILE.exists():
        try:
            SESSION_FILE.unlink()
        except Exception as e:
            print(f"Failed to delete session file: {e}")
