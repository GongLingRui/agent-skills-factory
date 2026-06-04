"""agent.yaml normalization."""

from agent_factory.services.agent_yaml import normalize_agent_yaml_dict


def test_normalize_minimal_agent_yaml():
    row = normalize_agent_yaml_dict(
        {
            "id": "my-agent",
            "name": "My Agent",
            "version": "1.0.0",
            "skill": {"id": "some-skill"},
            "tools": {"allow": ["kb.search"]},
            "release": {"strategy": "full"},
        }
    )
    assert row["id"] == "my-agent"
    assert row["skill_config"]["id"] == "some-skill"
    assert row["tools_allow"] == ["kb.search"]
    assert row["release_config"]["strategy"] == "full"


def test_normalize_instruction_and_limits_alias():
    row = normalize_agent_yaml_dict(
        {
            "id": "x-agent",
            "name": "X",
            "version": "0.0.1",
            "instruction": "do good",
            "limits": {"max_turns": 3},
            "skill": {"id": "sk", "version_pin": "1.0.0"},
        }
    )
    assert row["instruction"] == "do good"
    assert row["limits_config"] == {"max_turns": 3}
    assert row["skill_config"]["version_pin"] == "1.0.0"


def test_normalize_flat_tools_allow():
    row = normalize_agent_yaml_dict(
        {
            "id": "flat-tools",
            "name": "Flat",
            "version": "1.0.0",
            "skill": {"id": "sk"},
            "tools_allow": ["read_reference", "kb.search"],
        }
    )
    assert row["tools_allow"] == ["read_reference", "kb.search"]


def test_normalize_nested_tools_allow_overrides_flat():
    row = normalize_agent_yaml_dict(
        {
            "id": "nested-wins",
            "name": "N",
            "version": "1.0.0",
            "skill": {"id": "sk"},
            "tools": {"allow": ["kb.search"]},
            "tools_allow": ["read_reference"],
        }
    )
    assert row["tools_allow"] == ["kb.search"]
