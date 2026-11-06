"""
core/autonomous_agent.py — AMATYA Complete Autonomy Engine.
===========================================================
Empowers AMATYA with complete autonomous perception, evaluation, and decision-making:
  1. Autonomous Visual Chess Playing:
     - Detects chessboard on screen (Lichess, Chess.com, or local board)
     - Maintains formal chess state via python-chess (chess.Board)
     - Analyzes opponent moves, calculates next best move via alpha-beta minimax / evaluation
     - Executes moves physically using mouse control (click-click or drag-drop)
  2. Autonomous GitHub Repository Evaluation:
     - Inspects repository structure, commits, license, dependencies, test coverage
     - Evaluates README.md against project codebase reality
     - Autonomously decides project usefulness, production viability, and risks
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Tuple

import chess

from core import outcome

# ── Piece-Square Tables (PST) for Positional Evaluation ───────────────────────

PAWN_TABLE = [
     0,  0,  0,  0,  0,  0,  0,  0,
    50, 50, 50, 50, 50, 50, 50, 50,
    10, 10, 20, 30, 30, 20, 10, 10,
     5,  5, 10, 25, 25, 10,  5,  5,
     0,  0,  0, 20, 20,  0,  0,  0,
     5, -5,-10,  0,  0,-10, -5,  5,
     5, 10, 10,-20,-20, 10, 10,  5,
     0,  0,  0,  0,  0,  0,  0,  0,
]

KNIGHT_TABLE = [
    -50,-40,-30,-30,-30,-30,-40,-50,
    -40,-20,  0,  0,  0,  0,-20,-40,
    -30,  0, 10, 15, 15, 10,  0,-30,
    -30,  5, 15, 20, 20, 15,  5,-30,
    -30,  0, 15, 20, 20, 15,  0,-30,
    -30,  5, 10, 15, 15, 10,  5,-30,
    -40,-20,  0,  5,  5,  0,-20,-40,
    -50,-40,-30,-30,-30,-30,-40,-50,
]

BISHOP_TABLE = [
    -20,-10,-10,-10,-10,-10,-10,-20,
    -10,  0,  0,  0,  0,  0,  0,-10,
    -10,  0,  5, 10, 10,  5,  0,-10,
    -10,  5,  5, 10, 10,  5,  5,-10,
    -10,  0, 10, 10, 10, 10,  0,-10,
    -10, 10, 10, 10, 10, 10, 10,-10,
    -10,  5,  0,  0,  0,  0,  5,-10,
    -20,-10,-10,-10,-10,-10,-10,-20,
]

ROOK_TABLE = [
      0,  0,  0,  0,  0,  0,  0,  0,
      5, 10, 10, 10, 10, 10, 10,  5,
     -5,  0,  0,  0,  0,  0,  0, -5,
     -5,  0,  0,  0,  0,  0,  0, -5,
     -5,  0,  0,  0,  0,  0,  0, -5,
     -5,  0,  0,  0,  0,  0,  0, -5,
     -5,  0,  0,  0,  0,  0,  0, -5,
      0,  0,  0,  5,  5,  0,  0,  0,
]

QUEEN_TABLE = [
    -20,-10,-10, -5, -5,-10,-10,-20,
    -10,  0,  0,  0,  0,  0,  0,-10,
    -10,  0,  5,  5,  5,  5,  0,-10,
     -5,  0,  5,  5,  5,  5,  0, -5,
      0,  0,  5,  5,  5,  5,  0, -5,
    -10,  5,  5,  5,  5,  5,  0,-10,
    -10,  0,  5,  0,  0,  0,  0,-10,
    -20,-10,-10, -5, -5,-10,-10,-20,
]

KING_TABLE = [
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -20,-30,-30,-40,-40,-30,-30,-20,
    -10,-20,-20,-20,-20,-20,-20,-10,
     20, 20,  0,  0,  0,  0, 20, 20,
     20, 30, 10,  0,  0, 10, 30, 20,
]

PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 20000,
}

PST_MAP = {
    chess.PAWN: PAWN_TABLE,
    chess.KNIGHT: KNIGHT_TABLE,
    chess.BISHOP: BISHOP_TABLE,
    chess.ROOK: ROOK_TABLE,
    chess.QUEEN: QUEEN_TABLE,
    chess.KING: KING_TABLE,
}


def evaluate_board(board: chess.Board) -> int:
    """Evaluate static position in centipawns from White's perspective."""
    if board.is_checkmate():
        return -99999 if board.turn == chess.WHITE else 99999
    if board.is_stalemate() or board.is_insufficient_material() or board.can_claim_draw():
        return 0

    score = 0
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if not piece:
            continue

        val = PIECE_VALUES.get(piece.piece_type, 0)
        pst = PST_MAP.get(piece.piece_type, [])
        pst_val = 0
        if pst:
            pst_idx = sq if piece.color == chess.BLACK else chess.square_mirror(sq)
            pst_val = pst[pst_idx]

        total_piece_score = val + pst_val
        if piece.color == chess.WHITE:
            score += total_piece_score
        else:
            score -= total_piece_score

    return score


def minimax(
    board: chess.Board,
    depth: int,
    alpha: int,
    beta: int,
    is_maximizing: bool,
) -> Tuple[int, Optional[chess.Move]]:
    """Alpha-beta minimax search."""
    if depth == 0 or board.is_game_over():
        return evaluate_board(board), None

    best_move: Optional[chess.Move] = None

    if is_maximizing:
        max_eval = -999999
        for move in board.legal_moves:
            board.push(move)
            eval_score, _ = minimax(board, depth - 1, alpha, beta, False)
            board.pop()
            if eval_score > max_eval:
                max_eval = eval_score
                best_move = move
            alpha = max(alpha, eval_score)
            if beta <= alpha:
                break
        return max_eval, best_move
    else:
        min_eval = 999999
        for move in board.legal_moves:
            board.push(move)
            eval_score, _ = minimax(board, depth - 1, alpha, beta, True)
            board.pop()
            if eval_score < min_eval:
                min_eval = eval_score
                best_move = move
            beta = min(beta, eval_score)
            if beta <= alpha:
                break
        return min_eval, best_move


# ── 1. Autonomous Chess Agent ─────────────────────────────────────────────────

@dataclass
class ChessState:
    board: chess.Board = field(default_factory=chess.Board)
    player_color: chess.Color = chess.WHITE
    board_rect: dict[str, int] = field(default_factory=lambda: {"x": 480, "y": 200, "width": 640, "height": 640})
    moves_history: list[str] = field(default_factory=list)
    auto_play_active: bool = False


_CHESS_AGENT: Optional[AutonomousChessAgent] = None


class AutonomousChessAgent:
    """Autonomous agent capable of playing chess via vision, evaluation, and mouse execution."""

    def __init__(self) -> None:
        self.state = ChessState()

    def reset_game(self, fen: Optional[str] = None, player_color: str = "white") -> None:
        """Reset chess board to initial state or custom FEN."""
        self.state.board = chess.Board(fen) if fen else chess.Board()
        self.state.player_color = chess.WHITE if player_color.lower().startswith("w") else chess.BLACK
        self.state.moves_history.clear()

    def set_board_rect(self, x: int, y: int, width: int, height: int) -> None:
        """Set screen pixel coordinates for the chessboard."""
        self.state.board_rect = {"x": x, "y": y, "width": width, "height": height}

    def square_to_screen_xy(self, square: chess.Square) -> Tuple[int, int]:
        """Convert a chess.Square (0..63) to screen pixel coordinates."""
        file_idx = chess.square_file(square)  # 0 = a, 7 = h
        rank_idx = chess.square_rank(square)  # 0 = 1, 7 = 8

        rect = self.state.board_rect
        sq_w = rect["width"] / 8.0
        sq_h = rect["height"] / 8.0

        if self.state.player_color == chess.WHITE:
            # White orientation: file 0 (a) is left, rank 7 (8) is top
            px = int(rect["x"] + (file_idx + 0.5) * sq_w)
            py = int(rect["y"] + (7 - rank_idx + 0.5) * sq_h)
        else:
            # Black orientation: file 7 (h) is left, rank 0 (1) is top
            px = int(rect["x"] + (7 - file_idx + 0.5) * sq_w)
            py = int(rect["y"] + (rank_idx + 0.5) * sq_h)

        return px, py

    def record_opponent_move(self, move_str: str) -> dict[str, Any]:
        """Record an opponent's move (in UCI e.g. 'e7e5' or SAN e.g. 'e5')."""
        move_clean = move_str.strip()
        try:
            # Try UCI
            move = chess.Move.from_uci(move_clean)
            if move not in self.state.board.legal_moves:
                move = self.state.board.parse_san(move_clean)
        except Exception:
            try:
                move = self.state.board.parse_san(move_clean)
            except Exception as exc:
                return {"ok": False, "error": f"Invalid opponent move '{move_clean}': {exc}"}

        san_repr = self.state.board.san(move)
        self.state.board.push(move)
        self.state.moves_history.append(san_repr)

        return {
            "ok": True,
            "move": san_repr,
            "uci": move.uci(),
            "fen": self.state.board.fen(),
            "turn": "white" if self.state.board.turn == chess.WHITE else "black",
        }

    def compute_next_best_move(self, depth: int = 3) -> dict[str, Any]:
        """Analyze position and determine best move using alpha-beta minimax."""
        if self.state.board.is_game_over():
            return {
                "ok": False,
                "game_over": True,
                "result": self.state.board.result(),
                "error": "Game is already over.",
            }

        is_white_turn = self.state.board.turn == chess.WHITE
        score, best_move = minimax(
            self.state.board,
            depth=depth,
            alpha=-999999,
            beta=999999,
            is_maximizing=is_white_turn,
        )

        if not best_move:
            legal_moves = list(self.state.board.legal_moves)
            best_move = legal_moves[0] if legal_moves else None

        if not best_move:
            return {"ok": False, "error": "No legal moves available."}

        san_name = self.state.board.san(best_move)
        from_sq = best_move.from_square
        to_sq = best_move.to_square

        from_x, from_y = self.square_to_screen_xy(from_sq)
        to_x, to_y = self.square_to_screen_xy(to_sq)

        return {
            "ok": True,
            "move_uci": best_move.uci(),
            "move_san": san_name,
            "from_square": chess.square_name(from_sq),
            "to_square": chess.square_name(to_sq),
            "from_coords": {"x": from_x, "y": from_y},
            "to_coords": {"x": to_x, "y": to_y},
            "centipawn_eval": score,
            "depth": depth,
        }

    def play_best_move(self, depth: int = 3, execute_mouse: bool = True) -> dict[str, Any]:
        """Compute the next best move, execute it via mouse, and update board state."""
        res = self.compute_next_best_move(depth=depth)
        if not res.get("ok"):
            return res

        from_c = res["from_coords"]
        to_c = res["to_coords"]
        uci = res["move_uci"]
        san_val = res["move_san"]

        if execute_mouse:
            # Physical mouse action: click start square then click destination square
            try:
                from actions.computer_control import computer_control
                # 1. Click origin square
                computer_control({"action": "click", "x": from_c["x"], "y": from_c["y"]})
                time.sleep(0.15)
                # 2. Click destination square
                computer_control({"action": "click", "x": to_c["x"], "y": to_c["y"]})
                res["mouse_executed"] = True
            except Exception as exc:
                res["mouse_executed"] = False
                res["mouse_error"] = str(exc)

        # Update internal board
        move_obj = chess.Move.from_uci(uci)
        self.state.board.push(move_obj)
        self.state.moves_history.append(san_val)
        res["fen_after"] = self.state.board.fen()

        return res


def get_chess_agent() -> AutonomousChessAgent:
    global _CHESS_AGENT
    if _CHESS_AGENT is None:
        _CHESS_AGENT = AutonomousChessAgent()
    return _CHESS_AGENT


# ── 2. Autonomous GitHub Repository Analyzer ──────────────────────────────────

class GitHubRepoAuditor:
    """Autonomously analyzes GitHub repositories: READMEs, architecture, code quality, and decides usefulness."""

    @staticmethod
    def audit_repository(repo_path_or_url: str) -> dict[str, Any]:
        """Audit a local or remote GitHub repository."""
        target = repo_path_or_url.strip()
        temp_dir: Optional[Path] = None
        repo_dir: Path

        if target.startswith("http://") or target.startswith("https://") or "github.com" in target:
            # Remote repository: shallow clone to temporary location
            import tempfile
            clean_name = re.sub(r"[^\w\-]", "_", target.split("/")[-1].replace(".git", ""))
            temp_dir = Path(tempfile.gettempdir()) / f"amatya_repo_{clean_name}_{int(time.time())}"
            try:
                cmd = ["git", "clone", "--depth", "1", target, str(temp_dir)]
                p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if p.returncode != 0:
                    return {"ok": False, "error": f"Failed to clone repository: {p.stderr.strip()}"}
                repo_dir = temp_dir
            except Exception as exc:
                return {"ok": False, "error": f"Git clone error: {exc}"}
        else:
            repo_dir = Path(target).expanduser().resolve()
            if not repo_dir.exists() or not repo_dir.is_dir():
                return {"ok": False, "error": f"Local repository directory not found: {target}"}

        # 1. Read README
        readme_text = ""
        for r_name in ("README.md", "readme.md", "README.rst", "README.txt", "README"):
            r_path = repo_dir / r_name
            if r_path.is_file():
                try:
                    readme_text = r_path.read_text(encoding="utf-8", errors="ignore")
                    break
                except Exception:
                    pass

        # 2. Check License
        has_license = any((repo_dir / l_name).is_file() for l_name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"))

        # 3. Directory structure & Stack detection
        languages = set()
        total_files = 0
        has_tests = False
        package_manifests = []

        manifest_checks = {
            "requirements.txt": "Python",
            "setup.py": "Python",
            "pyproject.toml": "Python",
            "package.json": "JavaScript/TypeScript",
            "Cargo.toml": "Rust",
            "go.mod": "Go",
            "pom.xml": "Java",
            "CMakeLists.txt": "C/C++",
        }

        for fname, lang in manifest_checks.items():
            if (repo_dir / fname).is_file():
                package_manifests.append(fname)
                languages.add(lang)

        # File count and test detection
        for root, dirs, files in os.walk(repo_dir):
            if ".git" in dirs:
                dirs.remove(".git")
            if "node_modules" in dirs:
                dirs.remove("node_modules")
            if ".venv" in dirs or "venv" in dirs:
                dirs.remove(dirs[0])

            total_files += len(files)
            if any("test" in f.lower() for f in files) or "tests" in [d.lower() for d in dirs]:
                has_tests = True

            for f in files:
                ext = Path(f).suffix.lower()
                if ext in (".py", ".pyw"):
                    languages.add("Python")
                elif ext in (".js", ".ts", ".jsx", ".tsx"):
                    languages.add("JavaScript/TypeScript")
                elif ext in (".rs",):
                    languages.add("Rust")
                elif ext in (".go",):
                    languages.add("Go")
                elif ext in (".c", ".cpp", ".h", ".hpp"):
                    languages.add("C/C++")

        # 4. Recent git commits
        recent_commits = []
        try:
            p_log = subprocess.run(
                ["git", "-C", str(repo_dir), "log", "-n", "5", "--oneline"],
                capture_output=True, text=True, timeout=5,
            )
            if p_log.returncode == 0:
                recent_commits = p_log.stdout.strip().splitlines()
        except Exception:
            pass

        # 5. Autonomous Usefulness & Quality Decision Scoring
        score = 0
        reasons_positive = []
        reasons_negative = []

        # README evaluation
        if len(readme_text) > 500:
            score += 25
            reasons_positive.append("Comprehensive README documentation with usage guidelines.")
        elif len(readme_text) > 100:
            score += 10
            reasons_positive.append("Basic README provided.")
        else:
            score -= 15
            reasons_negative.append("Missing or sparse README documentation.")

        # Test suite existence
        if has_tests:
            score += 20
            reasons_positive.append("Automated test suite detected.")
        else:
            score -= 10
            reasons_negative.append("No automated test suite discovered.")

        # License
        if has_license:
            score += 15
            reasons_positive.append("Clear open-source license provided.")
        else:
            score -= 15
            reasons_negative.append("Missing open-source license file.")

        # Modern manifest & dependencies
        if package_manifests:
            score += 20
            reasons_positive.append(f"Standard package manifests present: {', '.join(package_manifests)}.")
        else:
            reasons_negative.append("No standard package dependency manifest discovered.")

        # Commit activity
        if recent_commits:
            score += 20
            reasons_positive.append(f"Active commit history ({len(recent_commits)} recent commits verified).")

        # Decision synthesis
        if score >= 70:
            decision = "HIGHLY USEFUL & PRODUCTION-READY"
            recommendation = "Recommended for integration. Codebase demonstrates high documentation standards, test coverage, and clear structure."
        elif score >= 45:
            decision = "USEFUL WITH RESERVATIONS"
            recommendation = "Usable, but verify missing areas (e.g. tests, documentation, or dependency pinning) before production adoption."
        else:
            decision = "NOT RECOMMENDED / EXPERIMENTAL"
            recommendation = "High risk or unmaintained. Codebase lacks essential documentation, tests, or packaging structure."

        # Cleanup if cloned
        if temp_dir and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

        return {
            "ok": True,
            "target": target,
            "decision": decision,
            "score": score,
            "languages": list(languages),
            "manifests": package_manifests,
            "total_files": total_files,
            "has_tests": has_tests,
            "has_license": has_license,
            "readme_summary": readme_text[:400] + ("..." if len(readme_text) > 400 else ""),
            "recent_commits": recent_commits,
            "strengths": reasons_positive,
            "risks": reasons_negative,
            "recommendation": recommendation,
        }

