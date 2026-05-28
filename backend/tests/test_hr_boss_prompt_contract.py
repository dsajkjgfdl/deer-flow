from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_hr_boss_skill_bans_raw_graph_identifiers_in_leader_answers():
    skill = (REPO_ROOT.parent / "skills" / "custom" / "hr-boss" / "SKILL.md").read_text(encoding="utf-8")

    assert "不得在最终回答中原样输出" in skill
    assert "CURRENTLY_IN_DEPARTMENT" in skill
    assert "当前所属部门" in skill
