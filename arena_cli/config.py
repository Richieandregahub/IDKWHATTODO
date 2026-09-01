"""Config + local data storage for arena-cli (~/.arena-cli/)."""

import json
import os
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("ARENA_CLI_HOME", Path.home() / ".arena-cli"))
CONFIG_FILE = CONFIG_DIR / "config.json"
LEADERBOARD_FILE = CONFIG_DIR / "leaderboard.json"

DEFAULT_MODELS = [
    "openai/gpt-4o-mini",
    "anthropic/claude-3.5-haiku",
    "google/gemini-2.0-flash-001",
    "meta-llama/llama-3.3-70b-instruct",
    "mistralai/mistral-small-3.1-24b-instruct",
    "deepseek/deepseek-chat",
    "qwen/qwen-2.5-72b-instruct",
]

DEFAULT_CONFIG = {
    "provider": "demo",          # "openrouter", "openai", "custom", or "demo"
    "api_key": "",
    "base_url": "",
    "models": DEFAULT_MODELS,
    "default_model": "",
}


def _ensure_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text()))
        except (json.JSONDecodeError, OSError):
            pass
    # Environment variables always win
    if os.environ.get("OPENROUTER_API_KEY"):
        cfg["provider"] = "openrouter"
        cfg["api_key"] = os.environ["OPENROUTER_API_KEY"]
    elif os.environ.get("OPENAI_API_KEY") and cfg["provider"] == "demo":
        cfg["provider"] = "openai"
        cfg["api_key"] = os.environ["OPENAI_API_KEY"]
    return cfg


def save_config(cfg):
    _ensure_dir()
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


def load_leaderboard():
    if LEADERBOARD_FILE.exists():
        try:
            return json.loads(LEADERBOARD_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_leaderboard(board):
    _ensure_dir()
    LEADERBOARD_FILE.write_text(json.dumps(board, indent=2))


def update_elo(board, winner, loser, tie=False, k=32):
    """Standard Elo update. board maps model -> {elo, wins, losses, ties, battles}."""
    for m in (winner, loser):
        board.setdefault(m, {"elo": 1000.0, "wins": 0, "losses": 0, "ties": 0, "battles": 0})
    ra, rb = board[winner]["elo"], board[loser]["elo"]
    ea = 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))
    eb = 1.0 - ea
    sa, sb = (0.5, 0.5) if tie else (1.0, 0.0)
    board[winner]["elo"] = ra + k * (sa - ea)
    board[loser]["elo"] = rb + k * (sb - eb)
    board[winner]["battles"] += 1
    board[loser]["battles"] += 1
    if tie:
        board[winner]["ties"] += 1
        board[loser]["ties"] += 1
    else:
        board[winner]["wins"] += 1
        board[loser]["losses"] += 1
    return board
