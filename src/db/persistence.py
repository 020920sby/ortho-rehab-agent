"""
SQLite 持久化层 — 存储打卡记录、训练完成状态等患者日常数据。

与 LangGraph 的 SqliteSaver（checkpoint 用）互补，
本模块专注于结构化业务数据的增删改查。
"""

import sqlite3
import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, date

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "data", "patient_records.db")


def _get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库表结构。幂等操作，可多次调用。"""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS patients (
            patient_id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            age INTEGER,
            gender TEXT DEFAULT '',
            surgery_type TEXT NOT NULL DEFAULT '',
            surgery_date TEXT NOT NULL DEFAULT '',
            doctor_name TEXT DEFAULT '',
            contact TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS checkins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT NOT NULL,
            checkin_date TEXT NOT NULL,
            pain_score INTEGER NOT NULL DEFAULT 0,
            rom TEXT NOT NULL DEFAULT '',
            walking_ability TEXT NOT NULL DEFAULT '',
            symptoms TEXT NOT NULL DEFAULT '[]',
            daily_feedback TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
        );

        CREATE TABLE IF NOT EXISTS exercise_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT NOT NULL,
            record_date TEXT NOT NULL,
            exercise_id TEXT NOT NULL,
            exercise_name TEXT NOT NULL DEFAULT '',
            completed INTEGER NOT NULL DEFAULT 0,
            completed_at TEXT,
            FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
        );

        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
        );

        CREATE TABLE IF NOT EXISTS medication_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT NOT NULL,
            log_date TEXT NOT NULL,
            drug_name TEXT NOT NULL,
            dosage TEXT NOT NULL DEFAULT '',
            taken INTEGER NOT NULL DEFAULT 0,
            taken_at TEXT,
            skipped_reason TEXT DEFAULT '',
            FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
        );

        CREATE TABLE IF NOT EXISTS followup_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT NOT NULL,
            followup_date TEXT NOT NULL,
            hospital TEXT NOT NULL DEFAULT '',
            department TEXT NOT NULL DEFAULT '',
            doctor_name TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            precautions TEXT NOT NULL DEFAULT '',
            materials_to_bring TEXT NOT NULL DEFAULT '',
            reminder_enabled INTEGER NOT NULL DEFAULT 0,
            reminder_before_days INTEGER NOT NULL DEFAULT 1,
            source TEXT NOT NULL DEFAULT 'manual',
            notes TEXT NOT NULL DEFAULT '',
            completed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
        );

        CREATE INDEX IF NOT EXISTS idx_checkins_patient_date
            ON checkins(patient_id, checkin_date);
        CREATE INDEX IF NOT EXISTS idx_exercise_patient_date
            ON exercise_records(patient_id, record_date);
        CREATE INDEX IF NOT EXISTS idx_chat_patient
            ON chat_history(patient_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_medication_patient_date
            ON medication_logs(patient_id, log_date);
        CREATE INDEX IF NOT EXISTS idx_followup_patient_date
            ON followup_plans(patient_id, followup_date);

        CREATE TABLE IF NOT EXISTS order_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT NOT NULL,
            filename TEXT NOT NULL DEFAULT '',
            raw_text_preview TEXT NOT NULL DEFAULT '',
            parsed_data TEXT NOT NULL DEFAULT '{}',
            source_type TEXT NOT NULL DEFAULT 'upload',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
        );

        CREATE INDEX IF NOT EXISTS idx_order_patient
            ON order_records(patient_id, created_at);
    """)
    # Migration: add skipped_reason to exercise_records if not already present
    try:
        conn.execute("ALTER TABLE exercise_records ADD COLUMN skipped_reason TEXT DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column already exists
    # Migration: add emergency_contacts to patients
    try:
        conn.execute("ALTER TABLE patients ADD COLUMN emergency_contacts TEXT DEFAULT '[]'")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.close()
    logger.info("Database initialized at %s", DB_PATH)


# ── Patient ────────────────────────────────────────────

def ensure_patient(patient_id: str, defaults: Optional[Dict] = None) -> Dict:
    """确保患者存在，不存在则创建。返回患者记录。"""
    defaults = defaults or {}
    conn = _get_conn()
    existing = conn.execute(
        "SELECT * FROM patients WHERE patient_id = ?", (patient_id,)
    ).fetchone()
    if existing:
        conn.close()
        return dict(existing)
    conn.execute(
        """INSERT INTO patients (patient_id, name, age, gender, surgery_type,
           surgery_date, doctor_name, contact)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            patient_id,
            defaults.get("name", ""),
            defaults.get("age"),
            defaults.get("gender", ""),
            defaults.get("surgery_type", ""),
            defaults.get("surgery_date", ""),
            defaults.get("doctor_name", ""),
            defaults.get("contact", ""),
        ),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM patients WHERE patient_id = ?", (patient_id,)
    ).fetchone()
    conn.close()
    return dict(row)


def update_patient(patient_id: str, updates: Dict) -> Dict:
    """更新患者信息。"""
    ensure_patient(patient_id)
    allowed = ["name", "age", "gender", "surgery_type", "surgery_date",
               "doctor_name", "contact"]
    fields = {k: v for k, v in updates.items() if k in allowed}
    if not fields:
        return get_patient(patient_id)
    fields["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [patient_id]
    conn = _get_conn()
    conn.execute(f"UPDATE patients SET {set_clause} WHERE patient_id = ?", values)
    conn.commit()
    row = conn.execute(
        "SELECT * FROM patients WHERE patient_id = ?", (patient_id,)
    ).fetchone()
    conn.close()
    return dict(row)


def get_patient(patient_id: str) -> Optional[Dict]:
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM patients WHERE patient_id = ?", (patient_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def list_all_patients() -> List[Dict]:
    """列出数据库中所有患者（按创建时间倒序）。"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM patients ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Check-In ───────────────────────────────────────────

def save_checkin(patient_id: str, data: Dict) -> Dict:
    today = date.today().isoformat()
    conn = _get_conn()
    # upsert: 同一天已有打卡则更新
    existing = conn.execute(
        "SELECT id FROM checkins WHERE patient_id = ? AND checkin_date = ?",
        (patient_id, today),
    ).fetchone()
    symptoms_json = json.dumps(data.get("symptoms", []), ensure_ascii=False)
    if existing:
        conn.execute(
            """UPDATE checkins SET pain_score=?, rom=?, walking_ability=?,
               symptoms=?, daily_feedback=? WHERE id=?""",
            (data.get("pain_score", 0), data.get("rom", ""),
             data.get("walking_ability", ""), symptoms_json,
             data.get("daily_feedback", ""), existing["id"]),
        )
    else:
        conn.execute(
            """INSERT INTO checkins (patient_id, checkin_date, pain_score, rom,
               walking_ability, symptoms, daily_feedback)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (patient_id, today, data.get("pain_score", 0), data.get("rom", ""),
             data.get("walking_ability", ""), symptoms_json,
             data.get("daily_feedback", "")),
        )
    conn.commit()
    conn.close()
    return {"status": "ok", "checkin_date": today}


def get_today_checkin(patient_id: str) -> Optional[Dict]:
    today = date.today().isoformat()
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM checkins WHERE patient_id = ? AND checkin_date = ?",
        (patient_id, today),
    ).fetchone()
    conn.close()
    if not row:
        return None
    result = dict(row)
    try:
        result["symptoms"] = json.loads(result.get("symptoms", "[]"))
    except json.JSONDecodeError:
        result["symptoms"] = []
    return result


# ── Exercises ──────────────────────────────────────────

def get_today_exercises(patient_id: str) -> List[Dict]:
    today = date.today().isoformat()
    conn = _get_conn()
    rows = conn.execute(
        """SELECT * FROM exercise_records
           WHERE patient_id = ? AND record_date = ?""",
        (patient_id, today),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_exercises(patient_id: str, exercises: List[Dict]):
    """批量保存今日训练项目（先删后插）。"""
    today = date.today().isoformat()
    conn = _get_conn()
    conn.execute(
        "DELETE FROM exercise_records WHERE patient_id = ? AND record_date = ?",
        (patient_id, today),
    )
    for ex in exercises:
        conn.execute(
            """INSERT INTO exercise_records
               (patient_id, record_date, exercise_id, exercise_name, completed)
               VALUES (?, ?, ?, ?, ?)""",
            (patient_id, today, ex.get("id", ""), ex.get("name", ""),
             1 if ex.get("completed") else 0),
        )
    conn.commit()
    conn.close()


def complete_exercise(patient_id: str, exercise_id: str) -> Dict:
    today = date.today().isoformat()
    conn = _get_conn()
    conn.execute(
        """UPDATE exercise_records SET completed = 1, completed_at = ?
           WHERE patient_id = ? AND record_date = ? AND exercise_id = ?""",
        (datetime.now().isoformat(), patient_id, today, exercise_id),
    )
    conn.commit()
    updated = conn.execute(
        """SELECT * FROM exercise_records
           WHERE patient_id = ? AND record_date = ? AND exercise_id = ?""",
        (patient_id, today, exercise_id),
    ).fetchone()
    conn.close()
    return dict(updated) if updated else {"error": "not found"}


# ── Progress ───────────────────────────────────────────

def get_progress(patient_id: str) -> Dict:
    conn = _get_conn()

    # 疼痛趋势
    pain_rows = conn.execute(
        """SELECT checkin_date as day, pain_score as value
           FROM checkins WHERE patient_id = ?
           ORDER BY checkin_date ASC LIMIT 30""",
        (patient_id,),
    ).fetchall()

    # 训练完成率
    exercise_rows = conn.execute(
        """SELECT record_date, COUNT(*) as total,
           SUM(completed) as done
           FROM exercise_records WHERE patient_id = ?
           GROUP BY record_date ORDER BY record_date DESC LIMIT 30""",
        (patient_id,),
    ).fetchall()

    conn.close()

    return {
        "pain_trend": [
            {"day": f"第{i+1}天", "value": r["value"]}
            for i, r in enumerate(pain_rows)
        ] if pain_rows else [],
        "rom_trend": [],  # 由 AI 从打卡数据中提取
        "milestones": [],  # 由 AI 动态生成
        "daily_records": [
            {
                "date": r["record_date"],
                "pain": 0,
                "rom": 0,
                "training_complete": r["done"] == r["total"] and r["total"] > 0,
            }
            for r in exercise_rows
        ],
    }


# ── Chat History ───────────────────────────────────────

def save_chat_message(patient_id: str, role: str, content: str):
    conn = _get_conn()
    conn.execute(
        "INSERT INTO chat_history (patient_id, role, content) VALUES (?, ?, ?)",
        (patient_id, role, content),
    )
    conn.commit()
    conn.close()


def get_recent_chat(patient_id: str, limit: int = 20) -> List[Dict]:
    conn = _get_conn()
    rows = conn.execute(
        """SELECT role, content FROM chat_history
           WHERE patient_id = ? ORDER BY created_at DESC LIMIT ?""",
        (patient_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


# ── Medication Log ──────────────────────────────────────

def save_medication_log(patient_id: str, drug_name: str, taken: bool,
                        dosage: str = "", skipped_reason: str = "") -> Dict:
    """记录用药状态（已服用/未服用）。"""
    today = date.today().isoformat()
    now = datetime.now().isoformat()
    conn = _get_conn()
    existing = conn.execute(
        """SELECT id FROM medication_logs
           WHERE patient_id = ? AND log_date = ? AND drug_name = ?""",
        (patient_id, today, drug_name),
    ).fetchone()
    if existing:
        conn.execute(
            """UPDATE medication_logs SET taken=?, taken_at=?,
               skipped_reason=?, dosage=?
               WHERE id=?""",
            (1 if taken else 0, now if taken else None, skipped_reason, dosage, existing["id"]),
        )
    else:
        conn.execute(
            """INSERT INTO medication_logs (patient_id, log_date, drug_name, dosage, taken, taken_at, skipped_reason)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (patient_id, today, drug_name, dosage, 1 if taken else 0,
             now if taken else None, skipped_reason),
        )
    conn.commit()
    conn.close()
    return {"status": "ok", "drug_name": drug_name, "taken": taken}


def get_today_medication_logs(patient_id: str) -> List[Dict]:
    """获取今日用药记录。"""
    today = date.today().isoformat()
    conn = _get_conn()
    rows = conn.execute(
        """SELECT * FROM medication_logs
           WHERE patient_id = ? AND log_date = ?
           ORDER BY id ASC""",
        (patient_id, today),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def seed_today_medications(patient_id: str, medications: List[Dict]):
    """为今日初始化用药记录（从康复计划中提取）。"""
    today = date.today().isoformat()
    conn = _get_conn()
    for med in medications:
        drug_name = med.get("drug_name", "")
        if not drug_name:
            continue
        existing = conn.execute(
            """SELECT id FROM medication_logs
               WHERE patient_id = ? AND log_date = ? AND drug_name = ?""",
            (patient_id, today, drug_name),
        ).fetchone()
        if not existing:
            conn.execute(
                """INSERT INTO medication_logs (patient_id, log_date, drug_name, dosage)
                   VALUES (?, ?, ?, ?)""",
                (patient_id, today, drug_name, med.get("dosage", "")),
            )
    conn.commit()
    conn.close()


# ── Exercise Log (enhanced) ─────────────────────────────

def save_exercise_log(patient_id: str, exercise_id: str, exercise_name: str = "",
                      completed: bool = False, skipped_reason: str = "") -> Dict:
    """记录训练状态（完成/跳过），支持跳过原因。"""
    today = date.today().isoformat()
    now = datetime.now().isoformat()
    conn = _get_conn()
    existing = conn.execute(
        """SELECT id FROM exercise_records
           WHERE patient_id = ? AND record_date = ? AND exercise_id = ?""",
        (patient_id, today, exercise_id),
    ).fetchone()
    if existing:
        conn.execute(
            """UPDATE exercise_records SET completed=?, completed_at=?,
               skipped_reason=?, exercise_name=?
               WHERE id=?""",
            (1 if completed else 0, now if completed else None,
             skipped_reason, exercise_name, existing["id"]),
        )
    else:
        conn.execute(
            """INSERT INTO exercise_records
               (patient_id, record_date, exercise_id, exercise_name, completed, completed_at, skipped_reason)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (patient_id, today, exercise_id, exercise_name,
             1 if completed else 0, now if completed else None, skipped_reason),
        )
    conn.commit()
    conn.close()
    return {"status": "ok", "exercise_id": exercise_id, "completed": completed}


def get_exercise_details(patient_id: str) -> List[Dict]:
    """获取患者最近训练详情（用于进度展示）。"""
    conn = _get_conn()
    rows = conn.execute(
        """SELECT record_date, exercise_name, completed, skipped_reason
           FROM exercise_records WHERE patient_id = ?
           ORDER BY record_date DESC, id ASC LIMIT 100""",
        (patient_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── ROM Trend ───────────────────────────────────────────

def get_rom_trend(patient_id: str) -> List[Dict]:
    """从打卡记录中解析关节活动度数值趋势。"""
    conn = _get_conn()
    rows = conn.execute(
        """SELECT checkin_date, rom FROM checkins WHERE patient_id = ?
           ORDER BY checkin_date ASC LIMIT 30""",
        (patient_id,),
    ).fetchall()
    conn.close()
    trends = []
    for r in rows:
        rom_str = r["rom"] or ""
        flex_val = None
        import re
        m = re.search(r'屈曲[^\d]*(\d+)', rom_str)
        if m:
            flex_val = int(m.group(1))
        trends.append({
            "week": r["checkin_date"],
            "value": flex_val,
            "target": 110,
            "raw_rom": rom_str,
        })
    return trends


# ── Followup Plans ───────────────────────────────────────

def save_followup(patient_id: str, data: Dict) -> Dict:
    """创建复诊计划记录。"""
    conn = _get_conn()
    now = datetime.now().isoformat()
    conn.execute(
        """INSERT INTO followup_plans (patient_id, followup_date, hospital, department,
           doctor_name, content, precautions, materials_to_bring, reminder_enabled,
           reminder_before_days, source, notes, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (patient_id, data.get("followup_date", ""), data.get("hospital", ""),
         data.get("department", ""), data.get("doctor_name", ""),
         data.get("content", ""), data.get("precautions", ""),
         data.get("materials_to_bring", ""), 1 if data.get("reminder_enabled") else 0,
         data.get("reminder_before_days", 1), data.get("source", "manual"),
         data.get("notes", ""), now, now),
    )
    conn.commit()
    row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    row = conn.execute("SELECT * FROM followup_plans WHERE id = ?", (row_id,)).fetchone()
    conn.close()
    return dict(row)


def get_followups(patient_id: str, upcoming_only: bool = False) -> List[Dict]:
    """获取患者复诊计划列表（按日期升序）。"""
    conn = _get_conn()
    if upcoming_only:
        today = date.today().isoformat()
        rows = conn.execute(
            """SELECT * FROM followup_plans
               WHERE patient_id = ? AND followup_date >= ? AND completed = 0
               ORDER BY followup_date ASC""",
            (patient_id, today),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT * FROM followup_plans
               WHERE patient_id = ?
               ORDER BY followup_date ASC""",
            (patient_id,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_followup(followup_id: int, data: Dict) -> Optional[Dict]:
    """更新复诊计划记录。"""
    allowed = ["followup_date", "hospital", "department", "doctor_name", "content",
               "precautions", "materials_to_bring", "reminder_enabled",
               "reminder_before_days", "notes", "completed"]
    fields = {k: v for k, v in data.items() if k in allowed}
    if not fields:
        return None
    fields["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [followup_id]
    conn = _get_conn()
    conn.execute(f"UPDATE followup_plans SET {set_clause} WHERE id = ?", values)
    conn.commit()
    row = conn.execute("SELECT * FROM followup_plans WHERE id = ?", (followup_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_followup(followup_id: int) -> bool:
    """删除复诊计划记录。"""
    conn = _get_conn()
    conn.execute("DELETE FROM followup_plans WHERE id = ?", (followup_id,))
    conn.commit()
    conn.close()
    return True


def get_next_followup(patient_id: str) -> Optional[Dict]:
    """获取最近一次未完成的复诊计划。"""
    today = date.today().isoformat()
    conn = _get_conn()
    row = conn.execute(
        """SELECT * FROM followup_plans
           WHERE patient_id = ? AND followup_date >= ? AND completed = 0
           ORDER BY followup_date ASC LIMIT 1""",
        (patient_id, today),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def seed_default_followups(patient_id: str, surgery_type: str, surgery_date: str):
    """根据手术类型生成默认复诊计划（AI 兜底方案）。"""
    from datetime import datetime as _dt
    existing = get_followups(patient_id)
    if existing:
        return existing  # 已有计划，不重复生成

    try:
        base_date = _dt.strptime(surgery_date, "%Y-%m-%d") if surgery_date else _dt.now()
    except ValueError:
        base_date = _dt.now()

    def _add_days(days: int) -> str:
        from datetime import timedelta
        return (base_date + timedelta(days=days)).strftime("%Y-%m-%d")

    defaults = {
        "TKA": [
            {"followup_date": _add_days(14), "content": "拆线 + 伤口评估", "department": "骨科",
             "precautions": "保持伤口干燥，如红肿渗液提前就医",
             "materials_to_bring": "出院小结、医保卡"},
            {"followup_date": _add_days(42), "content": "膝关节X光复查 + ROM评估", "department": "骨科",
             "precautions": "复查前正常服药",
             "materials_to_bring": "既往影像资料、医保卡"},
            {"followup_date": _add_days(90), "content": "功能恢复评估 + 步态分析", "department": "康复科",
             "precautions": "穿便于活动的衣物",
             "materials_to_bring": "近期康复打卡记录"},
        ],
        "THA": [
            {"followup_date": _add_days(14), "content": "拆线 + 髋关节评估", "department": "骨科",
             "precautions": "保持伤口干燥，注意防脱位姿势",
             "materials_to_bring": "出院小结、医保卡"},
            {"followup_date": _add_days(42), "content": "髋关节X光复查 + 步态评估", "department": "骨科",
             "precautions": "复查前正常服药",
             "materials_to_bring": "既往影像资料、医保卡"},
            {"followup_date": _add_days(90), "content": "功能恢复评估 + 肌力测试", "department": "康复科",
             "precautions": "穿便于活动的衣物",
             "materials_to_bring": "近期康复打卡记录"},
        ],
        "ACL": [
            {"followup_date": _add_days(14), "content": "拆线 + 关节活动度评估", "department": "骨科",
             "precautions": "支具锁定0度前往",
             "materials_to_bring": "出院小结、医保卡"},
            {"followup_date": _add_days(42), "content": "MRI复查 + Lachman测试", "department": "骨科",
             "precautions": "复查前正常服药",
             "materials_to_bring": "既往影像资料、医保卡"},
            {"followup_date": _add_days(90), "content": "功能恢复评估 + 等速肌力测试", "department": "康复科",
             "precautions": "穿运动装备",
             "materials_to_bring": "近期康复打卡记录"},
        ],
    }

    plans = defaults.get(surgery_type, defaults["TKA"])
    results = []
    for plan in plans:
        plan["source"] = "ai_generated"
        plan["reminder_enabled"] = True
        plan["reminder_before_days"] = 1
        r = save_followup(patient_id, plan)
        results.append(r)
    return results


# ── Emergency Contacts ────────────────────────────────────

def get_emergency_contacts(patient_id: str) -> List[Dict]:
    """获取患者紧急联系人列表（最多3个）。"""
    conn = _get_conn()
    row = conn.execute(
        "SELECT emergency_contacts FROM patients WHERE patient_id = ?",
        (patient_id,),
    ).fetchone()
    conn.close()
    if not row or not row["emergency_contacts"]:
        return []
    try:
        contacts = json.loads(row["emergency_contacts"])
        return contacts if isinstance(contacts, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def save_emergency_contacts(patient_id: str, contacts: List[Dict]) -> List[Dict]:
    """保存紧急联系人（最多3个，覆盖写入）。"""
    ensure_patient(patient_id)
    # 验证字段
    cleaned = []
    for c in contacts[:3]:
        cleaned.append({
            "name": str(c.get("name", "")).strip(),
            "relationship": str(c.get("relationship", "")).strip(),
            "phone": str(c.get("phone", "")).strip(),
        })
    conn = _get_conn()
    conn.execute(
        "UPDATE patients SET emergency_contacts = ?, updated_at = ? WHERE patient_id = ?",
        (json.dumps(cleaned, ensure_ascii=False), datetime.now().isoformat(), patient_id),
    )
    conn.commit()
    conn.close()
    return cleaned


# ── Order Records ────────────────────────────────────────

def save_order_record(patient_id: str, filename: str, raw_text: str, parsed: Dict, source: str = "upload") -> Dict:
    """保存一份已解析的医嘱记录。"""
    conn = _get_conn()
    conn.execute(
        """INSERT INTO order_records (patient_id, filename, raw_text_preview, parsed_data, source_type)
           VALUES (?, ?, ?, ?, ?)""",
        (patient_id, filename, raw_text[:2000], json.dumps(parsed, ensure_ascii=False), source),
    )
    conn.commit()
    row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    row = conn.execute("SELECT * FROM order_records WHERE id = ?", (row_id,)).fetchone()
    conn.close()
    result = dict(row)
    try:
        result["parsed_data"] = json.loads(result.get("parsed_data", "{}"))
    except (json.JSONDecodeError, TypeError):
        result["parsed_data"] = {}
    return result


def get_order_records(patient_id: str) -> List[Dict]:
    """获取患者所有医嘱记录列表。"""
    conn = _get_conn()
    rows = conn.execute(
        """SELECT id, patient_id, filename, raw_text_preview, source_type, created_at
           FROM order_records WHERE patient_id = ?
           ORDER BY created_at DESC LIMIT 50""",
        (patient_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_order_detail(order_id: int) -> Optional[Dict]:
    """获取单条医嘱记录的完整信息（含解析数据）。"""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM order_records WHERE id = ?", (order_id,)).fetchone()
    conn.close()
    if not row:
        return None
    result = dict(row)
    try:
        result["parsed_data"] = json.loads(result.get("parsed_data", "{}"))
    except (json.JSONDecodeError, TypeError):
        result["parsed_data"] = {}
    return result


# ── 初始化 ─────────────────────────────────────────────

init_db()
