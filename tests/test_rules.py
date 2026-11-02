"""규칙 함수만 따로 검사(DB 없이). 실행: python -m tests.test_rules"""
from tf import rules
from tf.rules import PL, WP, FD, TT, RW, PT, Student


def S(i, main, *subs):
    return Student(i, str(i), f"학생{i}", main, tuple(subs))


def test():
    # 필수 포함 역할: 한 사람이 둘 다 가능해도 하나로 센다
    assert len(rules.required_cover([S(1, PL, WP)])) == 1
    assert rules.required_cover([S(1, PL, WP), S(2, TT, WP)]) == []
    # 부록 3 11단계: 테스터+발표자 팀에 보고서 작성자 → 막힘(남는 자리 1, 채울 역할 2)
    assert "자리가 모자람" in rules.join_block_reason([S(11, TT, PT), S(15, PT, FD)], S(14, RW, TT))
    # 공고 예: 주 기획자/보조 웹 프로그래머 혼자 있는 팀은 필수 역할 1개만 채운 것
    assert rules.join_block_reason([S(1, PL, WP), S(2, TT), S(3, RW)], S(4, PT)) is not None
    assert rules.join_block_reason([S(1, PL, WP), S(2, TT), S(3, RW)], S(4, FD, WP)) is None
    # 주 역할 중복, 꽉 참
    assert rules.join_block_reason([S(1, PL)], S(2, PL)) == "같은 주 역할의 팀원이 있음"
    assert rules.join_block_reason([S(1, PL), S(2, WP), S(3, FD), S(4, TT)], S(5, RW)) == "팀이 꽉 참(4명)"
    # 배정안 검사: 두 팀에 배정, 빠진 학생
    teams = {"팀1": [S(1, PL), S(2, WP)], "팀2": [S(3, PL)]}
    un = [S(4, WP), S(5, TT)]
    errs = rules.validate_plan(teams, un, [("4", "팀2"), ("4", "팀1")])
    assert any("두 팀" in e for e in errs) and any("배정되지 않음" in e for e in errs)
    plan = rules.solve(teams, un)
    assert plan and not rules.validate_plan(teams, un, plan)
    # 배정이 없는 경우
    assert rules.solve({"팀1": [S(1, PL)]}, [S(2, PL)]) is None
    print("규칙 검사 모두 통과")


if __name__ == "__main__":
    test()
