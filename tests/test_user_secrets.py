from __future__ import annotations

import os
from pathlib import Path

from src.settings.user_secrets import (
    UserSecrets,
    apply_secrets_to_env,
    clear_user_secrets,
    load_user_secrets,
    mask_secret,
    save_user_secrets,
    secrets_path,
)


def test_save_and_load_secrets(tmp_path):
    data_dir = tmp_path / "data"
    sec = UserSecrets(dart_api_key="dart-key-1234567890", krx_id="user1", krx_pw="pass1")
    path = save_user_secrets(data_dir, sec)
    assert path.exists()
    loaded = load_user_secrets(data_dir)
    assert loaded.dart_api_key == "dart-key-1234567890"
    assert loaded.krx_id == "user1"


def test_apply_secrets_to_env(tmp_path, monkeypatch):
    monkeypatch.delenv("DART_API_KEY", raising=False)
    monkeypatch.delenv("KRX_ID", raising=False)
    data_dir = tmp_path / "data"
    save_user_secrets(data_dir, UserSecrets(dart_api_key="abc", krx_id="id", krx_pw="pw"))
    apply_secrets_to_env(data_dir, overwrite=True)
    assert os.environ["DART_API_KEY"] == "abc"
    assert os.environ["KRX_ID"] == "id"


def test_clear_secrets(tmp_path):
    data_dir = tmp_path / "data"
    save_user_secrets(data_dir, UserSecrets(dart_api_key="x"))
    clear_user_secrets(data_dir)
    assert not secrets_path(data_dir).exists()


def test_mask_secret():
    assert mask_secret("1234567890") == "******7890"
    assert mask_secret("") == "—"
