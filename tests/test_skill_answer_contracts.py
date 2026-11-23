"""Role swaps and missing deliverables that once passed the public cases."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import dialogue_eval
import simulate_eval


class SkillContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = {c["id"]: c for c in simulate_eval.load_cases(simulate_eval.DEFAULT_CASES)["cases"]}

    def check_case(self, ident, correct, original_bad, mutations):
        case = self.cases[ident]
        def encode(value):
            return json.dumps(value, ensure_ascii=False)

        self.assertTrue(dialogue_eval.auto_check(encode(correct), case)[1], ident)
        self.assertFalse(dialogue_eval.auto_check(original_bad, case)[1], ident)
        for changes in mutations:
            with self.subTest(case=ident, changes=changes):
                self.assertFalse(dialogue_eval.auto_check(encode(correct | changes), case)[1])
        for key in correct:
            with self.subTest(missing=key):
                self.assertFalse(dialogue_eval.auto_check(encode({k: v for k, v in correct.items() if k != key}), case)[1])

    def test_document_roles_per_medium(self):
        good = {"기술_목표": "목표는 10건이다.", "기술_실적": "실제 확인한 수는 8건이다.",
                "매뉴얼_목표": "작업 목표를 10건으로 둔다.", "매뉴얼_실적": "이번에 확인한 건수는 8건이다."}
        self.check_case("document-authoring-cross-format-02", good, "목표 8건, 실제 10건.",
                        [{"매뉴얼_목표": "목표는 8건"}, {"기술_실적": "18건 확인"},
                         {"기술_실적": "확인 -8건"}, {"기술_실적": "확인 8.5건"}])

    def test_slide_claims(self):
        good = {"현황_제목": "현행 처리에 12분이 든다", "문제_제목": "대기가 4분을 차지한다",
                "제안_제목": "처리 시간을 8분으로 줄이는 것이 목표다", "수치_성격": "가정"}
        self.check_case("office-docs-each-slide-02", good, "실측 처리시간 4분, 목표 12분, 대기 8분.",
                        [{"현황_제목": good["문제_제목"]}, {"수치_성격": "실측"},
                         {"제안_제목": "처리 시간이 8분으로 단축됐다"}])

    def test_prompt_and_three_examples(self):
        good = {"prompt": "JSON에 category와 urgency를 작성한다. 배송·결제 외 모호한 문의는 기타다. 중복 결제는 긴급, 나머지는 일반이다.",
                "배송_입력": "택배가 언제 도착하나요?", "결제_입력": "결제가 두 번 됐어요.", "모호_입력": "좀 도와주세요.",
                "배송_category": "배송", "결제_category": "결제", "모호_category": "기타",
                "배송_urgency": "일반", "결제_urgency": "긴급", "모호_urgency": "일반",
                "통과기준": "분류와 긴급도가 모두 기대값과 일치해야 한다."}
        self.check_case("prompt-engineering-01", good, "JSON",
                        [{"prompt": "JSON"}, {"모호_category": "배송"}, {"결제_urgency": "일반"}, {"결제_입력": ""}, {"모호_입력": "  "}])

    def test_judged_pairs(self):
        good = {"예정": 4, "양쪽출력": 3, "판정완료": 2, "개선": 1, "악화": 1, "시간초과": 1,
                "판정대기": 1, "종합개선확정": False, "안전확인": False}
        self.check_case("evidence-first-eval-pairs-03", good, "4건 전부 개선, 보류 2건도 개선으로 집계.",
                        [{"개선": 4}, {"악화": True}, {"판정완료": 3}, {"종합개선확정": True}])

    def test_sources_keep_their_roles(self):
        self.check_case("research-brief-source-origin-01",
                        {"A": "1차", "B": "2차", "독립적으로재현됨": False, "한계": "독립 검증이 없다."},
                        "1차, 2차", [{"A": "2차", "B": "1차"}])
        self.check_case("research-brief-dependent-sources",
                        {"A": "직접관찰", "B": "재인용", "C": "재인용", "독립관찰수": 1, "기사수만으로확신상향": False},
                        "기사 세 개", [{"독립관찰수": 3}, {"기사수만으로확신상향": True}])

    def test_product_decision_changes_with_evidence(self):
        good = {"최초선택": "보류", "비용확인후": "A", "의존성확인후": "B", "최종A일": 8, "최종B일": 4,
                "최초이유": "소요 기간 미확인", "변경이유": "A에 선행 작업이 추가됐다."}
        self.check_case("product-management-changing-evidence", good, "자료가 부족하다.",
                        [{"비용확인후": "B"}, {"의존성확인후": "A"}, {"최종A일": 2}, {"변경이유": "더 좋다."}])

    def test_alert_is_not_evidence_of_onset(self):
        good = {"탐지시각": "09:00", "복구시각": "09:20", "탐지후경과분": 20, "총영향분": None, "발생시각": None}
        self.check_case("incident-rca-alert-onset", good, "장애는 20분 지속됐다.",
                        [{"발생시각": "09:00"}, {"총영향분": 20}])

    def test_score_date_report_and_sync_receipt(self):
        good = {"A_점수": 1, "B_점수": 1, "C_점수": 1, "A_기준일": "기준일 미확인", "B_기준일": "기준일 미확인",
                "C_기준일": "2099-01-01", "최신여부확정": False}
        self.check_case("rhel-cve-score-date", good, "최신 점수다.",
                        [{"B_점수": 0}, {"A_기준일": "2099-01-01"}, {"최신여부확정": True}])
        self.check_case("devlog-lost-receipt", {"추가append": 0, "로컬상태": "synced", "원격항목수": 1},
                        "다시 추가", [{"추가append": 1}])

    def test_bad_field_spec_rejected_before_running(self):
        for invalid in ({"contains_all": None}, {"contains_all": [None]}, {"contains_all": [[]]},
                        {"contains_all": ["yes"], "numbers": [True]}, {"contains_all": ["ok"], "unknown": 1}):
            with self.subTest(invalid=invalid):
                self.assertFalse(simulate_eval.valid_answer_field(invalid))
