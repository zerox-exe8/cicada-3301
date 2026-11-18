from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.managers.antinuke_manager import AntinukeManager


@pytest.fixture
def antinuke_mgr() -> AntinukeManager:
    mock_db = MagicMock()
    return AntinukeManager(db=mock_db)


@pytest.fixture
def mock_guild() -> MagicMock:
    guild = MagicMock()
    guild.id = 123456789
    guild.owner_id = 111111111
    guild.me = MagicMock()
    guild.me.id = 999999999
    return guild


def test_server_owner_is_always_immune(antinuke_mgr: AntinukeManager, mock_guild: MagicMock) -> None:
    owner_id = mock_guild.owner_id
    assert antinuke_mgr.is_immune(mock_guild, owner_id) is True
    assert antinuke_mgr.is_immune(mock_guild, owner_id, module_name="anti_nuke") is True
    assert antinuke_mgr.is_immune(mock_guild, owner_id, module_name="anti_ban") is True


def test_bot_itself_is_always_immune(antinuke_mgr: AntinukeManager, mock_guild: MagicMock) -> None:
    bot_id = mock_guild.me.id
    assert antinuke_mgr.is_immune(mock_guild, bot_id) is True
    assert antinuke_mgr.is_immune(mock_guild, bot_id, module_name="anti_kick") is True


def test_extra_owner_is_immune(antinuke_mgr: AntinukeManager, mock_guild: MagicMock) -> None:
    extra_owner_id = 222222222
    antinuke_mgr._whitelist[mock_guild.id] = {
        extra_owner_id: {
            "is_extra_owner": True,
            "is_full": False,
            "scope": set(),
        }
    }
    assert antinuke_mgr.is_immune(mock_guild, extra_owner_id) is True
    assert antinuke_mgr.is_immune(mock_guild, extra_owner_id, module_name="anti_channel_create") is True


def test_whitelisted_for_this_action(antinuke_mgr: AntinukeManager, mock_guild: MagicMock) -> None:
    scoped_user_id = 333333333
    antinuke_mgr._whitelist[mock_guild.id] = {
        scoped_user_id: {
            "is_extra_owner": False,
            "is_full": False,
            "scope": {"anti_ban", "anti_kick"},
        }
    }
    # Whitelisted for anti_ban
    assert antinuke_mgr.is_immune(mock_guild, scoped_user_id, module_name="anti_ban") is True
    assert antinuke_mgr.is_immune(mock_guild, scoped_user_id, module_name="anti_kick") is True


def test_whitelisted_for_other_action_not_immune(antinuke_mgr: AntinukeManager, mock_guild: MagicMock) -> None:
    scoped_user_id = 333333333
    antinuke_mgr._whitelist[mock_guild.id] = {
        scoped_user_id: {
            "is_extra_owner": False,
            "is_full": False,
            "scope": {"anti_ban"},
        }
    }
    # Not whitelisted for anti_role_delete or without module
    assert antinuke_mgr.is_immune(mock_guild, scoped_user_id, module_name="anti_role_delete") is False
    assert antinuke_mgr.is_immune(mock_guild, scoped_user_id, module_name="") is False


def test_whitelisted_by_role(antinuke_mgr: AntinukeManager, mock_guild: MagicMock) -> None:
    user_id = 444444444
    role_id_admin = 555555555
    role_id_mod = 666666666

    role_admin = MagicMock()
    role_admin.id = role_id_admin
    role_mod = MagicMock()
    role_mod.id = role_id_mod

    member = MagicMock()
    member.id = user_id
    member.roles = [role_admin, role_mod]
    mock_guild.get_member.return_value = member

    # Role whitelist: role_admin has full immunity, role_mod has anti_kick
    antinuke_mgr._role_whitelist[mock_guild.id] = {
        role_id_admin: {
            "is_full": True,
            "scope": set(),
        }
    }
    assert antinuke_mgr.is_immune(mock_guild, user_id, module_name="anti_guild_update") is True

    # Now test with only scoped role
    antinuke_mgr._role_whitelist[mock_guild.id] = {
        role_id_mod: {
            "is_full": False,
            "scope": {"anti_kick"},
        }
    }
    member.roles = [role_mod]
    assert antinuke_mgr.is_immune(mock_guild, user_id, module_name="anti_kick") is True
    assert antinuke_mgr.is_immune(mock_guild, user_id, module_name="anti_ban") is False


def test_unprivileged_user_is_not_immune(antinuke_mgr: AntinukeManager, mock_guild: MagicMock) -> None:
    random_user_id = 777777777
    member = MagicMock()
    member.id = random_user_id
    member.roles = []
    mock_guild.get_member.return_value = member

    assert antinuke_mgr.is_immune(mock_guild, random_user_id) is False
    assert antinuke_mgr.is_immune(mock_guild, random_user_id, module_name="anti_ban") is False
