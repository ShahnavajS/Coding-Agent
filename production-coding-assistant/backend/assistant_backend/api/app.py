from __future__ import annotations

import logging
from datetime import datetime

from flask import Flask, jsonify, request
from flask_cors import CORS

from assistant_backend.config import get_cached_settings, update_app_settings
from assistant_backend.core.checkpoints import rollback_checkpoint
from assistant_backend.core.orchestrator import run_agent
from assistant_backend.storage.database import (
    create_session,
    delete_session,
    get_messages,
    get_pending_diff,
    list_sessions,
)
from assistant_backend.tools.filesystem_tool import (
    create_path,
    delete_path,
    list_files_flat,
    read_text_file,
)
from assistant_backend.tools.shell_tool import execute_command
from assistant_backend.tools.ast_editor import structured_update
from assistant_backend.tools.structured_editor import apply_pending_diff, preview_file_update

logger = logging.getLogger(__name__)


def _bad_request(message: str):
    """Return a 400 JSON error response."""
    return jsonify({"success": False, "error": message}), 400


def _server_error(message: str):
    """Return a 500 JSON error response."""
    return jsonify({"success": False, "error": message}), 500


def create_app() -> Flask:
    settings = get_cached_settings()
    app = Flask(__name__)
    CORS(app, origins=settings.cors_origins)

    # ------------------------------------------------------------------ health

    @app.route("/api/health", methods=["GET"])
    def health_check():
        return jsonify({
            "success": True,
            "message": "Backend server is running",
            "timestamp": datetime.now().isoformat(),
            "architecture": "modular-plan-execute",
        })

    # ------------------------------------------------------------------ files

    @app.route("/api/files/list", methods=["GET"])
    def files_list():
        return jsonify({"success": True, "data": list_files_flat()})

    @app.route("/api/files/read", methods=["POST"])
    def files_read():
        payload = request.get_json(force=True) or {}
        path = payload.get("path", "").strip()
        if not path:
            return _bad_request("'path' is required")
        try:
            content = read_text_file(path)
        except ValueError as exc:
            return _bad_request(str(exc))
        except FileNotFoundError:
            return jsonify({"success": False, "error": f"File not found: {path}"}), 404
        return jsonify({"success": True, "data": {"path": path, "content": content}})

    @app.route("/api/files/delete", methods=["POST"])
    def files_delete():
        payload = request.get_json(force=True) or {}
        path = payload.get("path", "").strip()
        if not path:
            return _bad_request("'path' is required")
        try:
            delete_path(path)
        except ValueError as exc:
            return _bad_request(str(exc))
        logger.info("Deleted path: %s", path)
        return jsonify({"success": True, "message": f"Deleted {path}"})

    @app.route("/api/files/create", methods=["POST"])
    def files_create():
        payload = request.get_json(force=True) or {}
        path = payload.get("path", "").strip()
        if not path:
            return _bad_request("'path' is required")
        try:
            result = create_path(path, payload.get("type", "file"), payload.get("content", ""))
        except ValueError as exc:
            return _bad_request(str(exc))
        return jsonify({"success": True, "data": result})

    # ------------------------------------------------------------------ diffs

    @app.route("/api/diff/preview", methods=["POST"])
    def diff_preview():
        payload = request.get_json(force=True) or {}
        path = payload.get("path", "").strip()
        if not path:
            return _bad_request("'path' is required")
        try:
            diff = preview_file_update(path, payload.get("content", ""))
        except ValueError as exc:
            return _bad_request(str(exc))
        return jsonify({"success": True, "data": diff})

    @app.route("/api/diff/structured", methods=["POST"])
    def diff_structured():
        payload = request.get_json(force=True) or {}
        path = payload.get("path", "").strip()
        if not path:
            return _bad_request("'path' is required")
        try:
            diff = structured_update(path, payload.get("operation", {}))
        except ValueError as exc:
            return _bad_request(str(exc))
        return jsonify({"success": True, "data": diff})

    @app.route("/api/diff/apply", methods=["POST"])
    def diff_apply():
        payload = request.get_json(force=True) or {}
        diff_id = payload.get("diffId", "").strip()
        if not diff_id:
            return _bad_request("'diffId' is required")
        try:
            result = apply_pending_diff(diff_id)
        except ValueError as exc:
            return _bad_request(str(exc))
        return jsonify({"success": True, "data": result})

    @app.route("/api/diff/<diff_id>", methods=["GET"])
    def diff_get(diff_id: str):
        diff = get_pending_diff(diff_id)
        if diff is None:
            return jsonify({"success": False, "error": "Diff not found"}), 404
        return jsonify({"success": True, "data": diff})

    # --------------------------------------------------------------- checkpoints

    @app.route("/api/checkpoints/<checkpoint_id>/rollback", methods=["POST"])
    def checkpoints_rollback(checkpoint_id: str):
        try:
            result = rollback_checkpoint(checkpoint_id)
        except ValueError as exc:
            return _bad_request(str(exc))
        logger.info("Rolled back checkpoint: %s", checkpoint_id)
        return jsonify({"success": True, "data": result})

    # ---------------------------------------------------------------- sessions

    @app.route("/api/sessions", methods=["GET", "POST"])
    def sessions():
        if request.method == "POST":
            payload = request.get_json(silent=True) or {}
            return jsonify({"success": True, "data": create_session(payload.get("title"))})
        return jsonify({"success": True, "data": list_sessions()})

    @app.route("/api/sessions/<session_id>/messages", methods=["GET"])
    def session_messages(session_id: str):
        return jsonify({"success": True, "data": get_messages(session_id)})

    @app.route("/api/sessions/<session_id>", methods=["DELETE"])
    def session_delete(session_id: str):
        deleted = delete_session(session_id)
        if not deleted:
            return jsonify({"success": False, "error": "Session not found"}), 404
        return jsonify({"success": True, "data": {"id": session_id}})

    # ------------------------------------------------------------------ agent

    @app.route("/api/agent/ask", methods=["POST"])
    def agent_ask():
        payload = request.get_json(force=True) or {}
        message = payload.get("message", "").strip()
        if not message:
            return _bad_request("'message' is required")
        session_id = payload.get("sessionId")
        if not session_id:
            session = create_session("Ad-hoc Session")
            session_id = session["id"]
        try:
            response = run_agent(message, session_id, payload.get("context", {}))
        except Exception as exc:
            logger.exception("Agent error for session %s: %s", session_id, exc)
            return _server_error(f"Agent encountered an error: {exc}")
        response["sessionId"] = session_id
        return jsonify({"success": True, "data": response})

    @app.route("/api/agent/status", methods=["GET"])
    def agent_status():
        return jsonify({
            "success": True,
            "data": {
                "status": "ready",
                "busy": False,
                "architecture": "planner-executor-debugger-foundation",
            },
        })

    # --------------------------------------------------------------- terminal

    @app.route("/api/terminal/execute", methods=["POST"])
    def terminal_execute():
        payload = request.get_json(force=True) or {}
        command = payload.get("command", "").strip()
        if not command:
            return _bad_request("'command' is required")
        result = execute_command(command, approved=bool(payload.get("approved", False)))
        return jsonify({"success": result.get("success", False), "data": result})

    # --------------------------------------------------------------- settings

    @app.route("/api/settings", methods=["GET", "POST"])
    def app_settings():
        if request.method == "POST":
            payload = request.get_json(force=True) or {}
            try:
                settings_obj = update_app_settings(payload)
            except (ValueError, KeyError) as exc:
                return _bad_request(str(exc))
            return jsonify({"success": True, "data": settings_obj.to_public_dict()})
        return jsonify({"success": True, "data": get_cached_settings().to_public_dict()})

    # --------------------------------------------------------- error handlers

    @app.errorhandler(404)
    def not_found(exc):
        return jsonify({"success": False, "error": "Route not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(exc):
        return jsonify({"success": False, "error": "Method not allowed"}), 405

    @app.errorhandler(500)
    def internal_error(exc):
        logger.exception("Unhandled server error: %s", exc)
        return jsonify({"success": False, "error": "Internal server error"}), 500

    return app
