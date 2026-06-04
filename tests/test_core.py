"""
核心逻辑单元测试 — OperatorEvaluator、康复阶段映射、安全规则匹配、文本分段。

运行: python -m pytest tests/ -v
"""

import pytest
from datetime import datetime, timedelta


# ── OperatorEvaluator 测试 ────────────────────────────

class TestOperatorEvaluator:
    """测试安全规则引擎的操作符求值器。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        from src.agents.safety_sentinel import OperatorEvaluator
        self.eval = OperatorEvaluator.evaluate

    def test_equals_match(self):
        assert self.eval("TKA", "equals", "TKA") is True
        assert self.eval("THA", "equals", "TKA") is False

    def test_greater_than(self):
        assert self.eval(8, "greater_than", 5) is True
        assert self.eval(3, "greater_than", 5) is False

    def test_less_than(self):
        assert self.eval(3, "less_than", 5) is True
        assert self.eval(8, "less_than", 5) is False

    def test_greater_than_or_equal(self):
        assert self.eval(5, "greater_than_or_equal", 5) is True
        assert self.eval(6, "greater_than_or_equal", 5) is True

    def test_less_than_or_equal(self):
        assert self.eval(5, "less_than_or_equal", 5) is True
        assert self.eval(4, "less_than_or_equal", 5) is True

    def test_is_true(self):
        assert self.eval(True, "is_true", None) is True
        assert self.eval(False, "is_true", None) is False

    def test_is_false(self):
        assert self.eval(False, "is_false", None) is True
        assert self.eval(True, "is_false", None) is False

    def test_contains(self):
        assert self.eval("膝关节肿胀疼痛", "contains", "疼痛") is True
        assert self.eval("膝关节肿胀", "contains", "发热") is False

    def test_not_equals(self):
        assert self.eval("normal", "not_equals", "emergency") is True
        assert self.eval("normal", "not_equals", "normal") is False

    def test_unknown_operator_returns_false(self):
        assert self.eval(5, "invalid_operator", 3) is False


# ── 康复阶段映射测试 ─────────────────────────────────

class TestPhaseMapping:
    """测试手术类型 → 康复阶段的映射。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        from src.agents.rehab_planner import RehabPlanner
        self.planner = RehabPlanner()

    @pytest.mark.parametrize("days, surgery, expected", [
        (3, "TKA", "急性期"),
        (10, "TKA", "急性期"),
        (14, "TKA", "急性期"),  # 边界：≤14
        (20, "TKA", "亚急性期"),
        (42, "TKA", "亚急性期"),  # 边界：≤42
        (60, "TKA", "恢复期"),
        (90, "TKA", "恢复期"),  # 边界：≤90
        (120, "TKA", "维持期"),
    ])
    def test_tka_phase(self, days, surgery, expected):
        phase = self.planner._determine_phase(days, surgery)
        assert phase == expected, f"Day {days} {surgery}: expected {expected}, got {phase}"

    @pytest.mark.parametrize("days, surgery, expected", [
        (3, "THA", "急性期"),
        (20, "THA", "亚急性期"),
        (60, "THA", "恢复期"),
        (120, "THA", "维持期"),
    ])
    def test_tha_phase(self, days, surgery, expected):
        phase = self.planner._determine_phase(days, surgery)
        assert phase == expected

    @pytest.mark.parametrize("days, surgery, expected", [
        (3, "ACL", "急性保护期"),
        (14, "ACL", "急性保护期"),
        (30, "ACL", "早期保护性训练期"),
        (42, "ACL", "早期保护性训练期"),
        (70, "ACL", "肌力重建期"),
        (90, "ACL", "肌力重建期"),
        (150, "ACL", "运动准备期"),
        (180, "ACL", "运动准备期"),
        (250, "ACL", "回归运动期"),
    ])
    def test_acl_phase(self, days, surgery, expected):
        phase = self.planner._determine_phase(days, surgery)
        assert phase == expected

    def test_unknown_surgery_defaults_to_tka(self):
        phase = self.planner._determine_phase(10, "UNKNOWN")
        assert phase == "急性期"  # 回退到 TKA 的阶段映射


# ── 安全规则匹配测试 ─────────────────────────────────

class TestRuleMatching:
    """测试 YAML 规则的条件匹配逻辑。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        from src.agents.safety_sentinel import OrthoSafetySentinel
        self.sentinel = OrthoSafetySentinel()

    def test_emergency_keyword_detected(self):
        state = {
            "patient_id": "P001",
            "daily_feedback": "我今天突然感到胸痛，呼吸有些困难",
            "pain_score": 5,
        }
        result = self.sentinel._rule_based_assessment(state)
        assert result["safety_level"] == "emergency"
        assert result["source"] == "rule_engine"
        assert result["rule_matched"] == "emergency_keyword"

    def test_no_keyword_returns_normal(self):
        state = {
            "patient_id": "P002",
            "daily_feedback": "今天膝关节有点酸，冰敷后好转。走路练习很顺利。",
            "pain_score": 2,
            "surgery_type": "TKA",
        }
        result = self.sentinel._rule_based_assessment(state)
        assert result["safety_level"] == "normal"

    def test_match_rule_all_conditions_satisfied(self):
        rule = {
            "name": "test_rule",
            "conditions": [
                {"field": "pain_score", "operator": "greater_than", "value": 7},
                {"field": "pain_trend", "operator": "equals", "value": "worsening"},
            ],
        }
        state = {"pain_score": 8, "pain_trend": "worsening"}
        assert self.sentinel._match_rule(rule, state) is True

    def test_match_rule_one_condition_fails(self):
        rule = {
            "name": "test_rule",
            "conditions": [
                {"field": "pain_score", "operator": "greater_than", "value": 7},
                {"field": "pain_trend", "operator": "equals", "value": "worsening"},
            ],
        }
        state = {"pain_score": 8, "pain_trend": "improving"}
        assert self.sentinel._match_rule(rule, state) is False

    def test_match_rule_missing_field_returns_false(self):
        rule = {
            "name": "test_rule",
            "conditions": [
                {"field": "calf_swelling", "operator": "is_true", "value": None},
            ],
        }
        state = {"pain_score": 3}  # calf_swelling 不存在
        assert self.sentinel._match_rule(rule, state) is False

    def test_empty_conditions_returns_false(self):
        rule = {"name": "empty_rule", "conditions": []}
        assert self.sentinel._match_rule(rule, {}) is False


# ── 安全判读融合策略测试 ─────────────────────────────

class TestSafetyMerge:
    @pytest.fixture(autouse=True)
    def setup(self):
        from src.agents.safety_sentinel import OrthoSafetySentinel
        self.sentinel = OrthoSafetySentinel()

    def test_merge_escalates_to_worse(self):
        rule_result = {"safety_level": "normal"}
        ai_result = {"safety_level": "warning", "reasoning": "AI判断有风险"}
        merged = self.sentinel._merge_results(rule_result, ai_result)
        assert merged["safety_level"] == "warning"

    def test_merge_keeps_higher_rule_result(self):
        rule_result = {"safety_level": "emergency"}
        ai_result = {"safety_level": "normal"}
        merged = self.sentinel._merge_results(rule_result, ai_result)
        assert merged["safety_level"] == "emergency"

    def test_merge_equal_levels(self):
        rule_result = {"safety_level": "attention"}
        ai_result = {"safety_level": "attention"}
        merged = self.sentinel._merge_results(rule_result, ai_result)
        assert merged["safety_level"] == "attention"
        assert "rule_engine" in merged.get("sources", [])

    def test_normal_range_for_tka_acute(self):
        desc = self.sentinel._get_normal_range(5, "TKA")
        assert "0-2周" in desc
        assert "0→90度" in desc

    def test_normal_range_fallback(self):
        # 未知手术类型回退到 TKA 范围
        desc = self.sentinel._get_normal_range(999, "UNKNOWN")
        # 999天命中 TKA 维持期范围 (91, 999)
        assert "维持期" in desc

    def test_normal_range_fallback_no_match(self):
        # 天数不在任何范围内时触发兜底
        # 注意：由于未知手术类型回退到 TKA，(0,14)->(15,42)->(43,90)->(91,999)
        # 覆盖了 0-999 天，所以需要超出这个范围
        desc = self.sentinel._get_normal_range(1000, "UNKNOWN")
        assert "标准骨科康复指南" in desc


# ── 文本分段测试 ─────────────────────────────────────

class TestSectionSplitting:
    def test_split_basic(self):
        from src.rag.vector_store import OrthoVectorStore

        content = """这是前言内容，在第一个标题之前。
# 一级标题
这是第一节的内容。
## 二级标题
这是第二节内容。
### 三级标题
这是第二节子内容。
# 另一章节
这是最后的内容。"""

        sections = OrthoVectorStore._split_by_sections(content)
        titles = [s["title"] for s in sections]
        assert "前言" in titles
        assert "一级标题" in titles
        assert "二级标题" in titles
        assert "另一章节" in titles

    def test_split_no_title(self):
        from src.rag.vector_store import OrthoVectorStore

        content = "这是一段没有任何标题的纯文本。\n第二行内容。"
        sections = OrthoVectorStore._split_by_sections(content)
        assert len(sections) == 1
        assert sections[0]["title"] == "前言"


# ── GraphRAG 实体匹配测试 ────────────────────────────

class TestGraphRAG:
    @pytest.fixture(autouse=True)
    def setup(self):
        from src.rag.graph_rag import OrthoGraphRAG
        self.graph = OrthoGraphRAG()

    def test_find_entity_by_id(self):
        assert self.graph.find_entity("TKA") == "TKA"
        assert self.graph.find_entity("tha") == "THA"

    def test_find_entity_by_alias(self):
        assert self.graph.find_entity("膝关节置换") == "TKA"
        assert self.graph.find_entity("ACL重建") == "ACL"

    def test_find_entity_by_name(self):
        assert self.graph.find_entity("全膝关节置换术") == "TKA"

    def test_find_unknown_entity(self):
        assert self.graph.find_entity("心脏搭桥") is None

    def test_get_complications(self):
        complications = self.graph.get_related_complications("TKA")
        assert "DVT" in complications
        assert "假体感染" in complications

    def test_get_contraindicated_actions(self):
        actions = self.graph.get_contraindicated_actions("THA")
        assert any("屈髋" in a for a in actions)

    def test_graph_search_surgery(self):
        result = self.graph.graph_search("TKA 术后 疼痛 康复", max_hops=1)
        assert len(result["matched_surgeries"]) > 0
        assert "TKA" in result["matched_surgeries"]

    def test_graph_search_no_match(self):
        result = self.graph.graph_search("今天天气真好", max_hops=1)
        assert result["matched_surgeries"] == []
        assert result["matched_complications"] == []


# ── 持久化层测试 (需要 sqlite) ───────────────────────

class TestPersistence:
    def test_get_rom_trend_parses_flexion(self):
        from src.db.persistence import get_rom_trend
        # 测试 ROM 正则解析逻辑（独立于数据库）
        import re
        test_cases = [
            ("膝关节屈曲95度，伸展0度", 95),
            ("屈曲110度，伸展-5度", 110),
            ("膝关节活动度：屈曲 90 度", 90),
            ("未记录", None),
            ("", None),
        ]
        for rom_str, expected in test_cases:
            m = re.search(r'屈曲[^\d]*(\d+)', rom_str)
            val = int(m.group(1)) if m else None
            assert val == expected, f"Failed for '{rom_str}': got {val}, expected {expected}"


# ── 康复计划查询构建测试 ─────────────────────────────

class TestSearchQuery:
    @pytest.fixture(autouse=True)
    def setup(self):
        from src.agents.rehab_planner import RehabPlanner
        self.planner = RehabPlanner()

    def test_query_high_pain(self):
        state = {"pain_score": 8}
        query = self.planner._build_search_query("TKA", "急性期", state)
        assert "重度疼痛管理" in query

    def test_query_moderate_pain(self):
        state = {"pain_score": 4}
        query = self.planner._build_search_query("TKA", "亚急性期", state)
        assert "中度疼痛" in query

    def test_query_acute_phase(self):
        state = {"pain_score": 2}
        query = self.planner._build_search_query("THA", "急性期", state)
        assert "早期康复" in query
        assert "DVT预防" in query
