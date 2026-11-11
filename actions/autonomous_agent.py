"""
actions/autonomous_agent.py — AMATYA Autonomous Decision Making & Gaming Action.
==============================================================================
Provides end-to-end autonomous capabilities:
  1. Autonomous Chess Player:
     - 'chess_play': compute best move and execute physical mouse move on screen
     - 'chess_move': play a specific move or record opponent's move
     - 'chess_reset': start a new game (White or Black)
     - 'chess_status': inspect current board state, FEN, and evaluation
  2. Autonomous GitHub Repository Evaluation:
     - 'audit_repo': inspects local or remote GitHub repositories, reads README,
       evaluates architecture, tests, commits, and outputs a decisive recommendation.
"""
from __future__ import annotations

from typing import Any

try:
    import chess
except ImportError:
    chess = None

from core import outcome
from core.autonomous_agent import (
    GitHubRepoAuditor,
    get_chess_agent,
)

SKILL_METADATA = {
    "name": "autonomous_agent",
    "version": "1.0.0",
    "description": (
        "Autonomous decision-making engine: visual chess playing (evaluates positions, "
        "calculates best moves, and moves mouse physically) and autonomous GitHub "
        "repository auditing (evaluates README, code quality, and decides usefulness)."
    ),
    "capabilities": [
        "autonomous_chess_playing",
        "mouse_move_execution",
        "opponent_move_analysis",
        "github_repo_evaluation",
        "code_usefulness_decision",
    ],
    "permissions": ["screen_control", "mouse_control", "network"],
    "dependencies": ["chess"],
    "supported_actions": [
        "chess_play",
        "chess_move",
        "chess_reset",
        "chess_status",
        "audit_repo",
    ],
    "security_level": "normal",
}

TOOL = {
    "name": "autonomous_agent",
    "description": (
        "Autonomous operations and decisions. Actions: "
        "'chess_play' (calculate next best chess move and execute via mouse), "
        "'chess_move' (record move, e.g. move='e7e5'), "
        "'chess_reset' (start new game with player_color='white'|'black'), "
        "'chess_status' (get current board FEN and evaluation), "
        "'audit_repo' (analyze GitHub repository URL or folder and decide usefulness)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Action: 'chess_play', 'chess_move', 'chess_reset', 'chess_status', or 'audit_repo'.",
            },
            "move": {
                "type": "STRING",
                "description": "Move string in UCI (e.g. 'e2e4') or SAN (e.g. 'Nf3') for chess_move.",
            },
            "player_color": {
                "type": "STRING",
                "description": "Player color: 'white' or 'black' (default: white).",
            },
            "repo": {
                "type": "STRING",
                "description": "Local repository folder path or GitHub repository URL (e.g. 'https://github.com/owner/repo').",
            },
            "depth": {
                "type": "INTEGER",
                "description": "Search depth for chess evaluation (default: 3).",
            },
            "board_rect": {
                "type": "OBJECT",
                "description": "Optional board screen coordinates: {'x': int, 'y': int, 'width': int, 'height': int}.",
            },
        },
        "required": ["action"],
    },
    "handler": None,
}


def autonomous_agent(parameters: dict[str, Any] | None = None, **kwargs: Any) -> str:
    params = dict(parameters or {})
    if kwargs:
        params.update(kwargs)

    action = str(params.get("action", "chess_status") or "chess_status").strip().lower()

    # ── 1. GitHub Repository Auditing & Decision Making ───────────────────────
    if action in ("audit_repo", "analyze_repo", "evaluate_repo", "github_audit"):
        repo_target = str(params.get("repo") or params.get("target") or params.get("url") or ".").strip()
        audit_res = GitHubRepoAuditor.audit_repository(repo_target)
        if not audit_res.get("ok"):
            return outcome.failed("autonomous_agent", audit_res.get("error", "Repo audit failed"))

        report_lines = [
            f"✦ AUTONOMOUS REPOSITORY AUDIT: {audit_res['target']} ✦",
            f"• Decision: {audit_res['decision']} (Score: {audit_res['score']}/100)",
            f"• Recommendation: {audit_res['recommendation']}",
            f"• Stack: {', '.join(audit_res['languages']) or 'Unidentified'} | Total Files: {audit_res['total_files']}",
            f"• Tests Present: {'Yes' if audit_res['has_tests'] else 'No'} | Open Source License: {'Yes' if audit_res['has_license'] else 'No'}",
            "",
            "Key Strengths:",
        ]
        for s in audit_res["strengths"]:
            report_lines.append(f"  + {s}")
        if audit_res["risks"]:
            report_lines.append("Identified Risks:")
            for r in audit_res["risks"]:
                report_lines.append(f"  - {r}")

        return outcome.done("autonomous_agent", result="\n".join(report_lines), data=audit_res)

    # ── 2. Autonomous Chess Player ────────────────────────────────────────────
    chess_ag = get_chess_agent()

    if "board_rect" in params and isinstance(params["board_rect"], dict):
        br = params["board_rect"]
        chess_ag.set_board_rect(
            int(br.get("x", 480)),
            int(br.get("y", 200)),
            int(br.get("width", 640)),
            int(br.get("height", 640)),
        )

    if action in ("chess_reset", "reset_chess", "new_game"):
        color = str(params.get("player_color", "white") or "white")
        chess_ag.reset_game(player_color=color)
        return outcome.done(
            "autonomous_agent",
            result=f"Chess board reset. Playing as {color.upper()}. Ready for moves.",
            data={"fen": chess_ag.state.board.fen(), "color": color},
        )

    if action in ("chess_move", "record_move", "opponent_move"):
        mv_text = str(params.get("move", "") or "").strip()
        if not mv_text:
            return outcome.failed("autonomous_agent", "Please provide 'move' parameter (e.g. 'e7e5' or 'Nf6').")
        res_mv = chess_ag.record_opponent_move(mv_text)
        if not res_mv.get("ok"):
            return outcome.failed("autonomous_agent", res_mv.get("error", "Move recording failed"))
        return outcome.done(
            "autonomous_agent",
            result=f"Recorded move {res_mv['move']}. Current turn: {res_mv['turn'].upper()}.",
            data=res_mv,
        )

    if action in ("chess_play", "play_move", "best_move", "next_move"):
        d = int(params.get("depth", 3))
        res_play = chess_ag.play_best_move(depth=d, execute_mouse=True)
        if not res_play.get("ok"):
            return outcome.failed("autonomous_agent", res_play.get("error", "Failed to compute best move"))

        msg = (
            f"✦ AUTONOMOUS CHESS MOVE EXECUTED ✦\n"
            f"• Selected Move: {res_play['move_san']} ({res_play['move_uci']})\n"
            f"• From: {res_play['from_square']} -> To: {res_play['to_square']}\n"
            f"• Position Evaluation: {res_play['centipawn_eval']} centipawns (depth {d})\n"
            f"• Mouse Input: {'Executed successfully' if res_play.get('mouse_executed') else 'Simulation only'}"
        )
        return outcome.done("autonomous_agent", result=msg, data=res_play)

    # Status
    bd = chess_ag.state.board
    white_const = getattr(chess, "WHITE", True) if chess else True
    turn_is_white = getattr(bd, "turn", None) == white_const
    player_is_white = getattr(chess_ag.state, "player_color", None) == white_const
    status_msg = (
        f"✦ CHESS STATUS ✦\n"
        f"• Turn: {'White' if turn_is_white else 'Black'} | Playing as: {'White' if player_is_white else 'Black'}\n"
        f"• FEN: {bd.fen()}\n"
        f"• Moves: {' '.join(chess_ag.state.moves_history) or 'None'}\n"
        f"• Game Over: {bd.is_game_over()}"
    )
    return outcome.done("autonomous_agent", result=status_msg, data={"fen": bd.fen(), "history": chess_ag.state.moves_history})


TOOL["handler"] = autonomous_agent

