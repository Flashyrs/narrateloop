import os
import sqlite3
import json
from datetime import datetime

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "pipeline_state.db")

def get_current_time_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=20.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes SQLite database schema for pipeline jobs, run metrics, and API quota tracking."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Pipeline Jobs Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_key TEXT UNIQUE NOT NULL,
                date_str TEXT NOT NULL,
                story_index INTEGER NOT NULL,
                story_title TEXT DEFAULT '',
                story_format TEXT DEFAULT 'short',
                stage TEXT NOT NULL DEFAULT 'PENDING',
                output_path TEXT DEFAULT '',
                upload_url TEXT DEFAULT '',
                error_message TEXT DEFAULT '',
                retry_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # 2. Pipeline Runs Table (Metrics per stage / render)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_key TEXT NOT NULL,
                stage TEXT NOT NULL,
                wall_time_sec REAL DEFAULT 0.0,
                cpu_time_sec REAL DEFAULT 0.0,
                peak_rss_mb REAL DEFAULT 0.0,
                swap_before_mb REAL DEFAULT 0.0,
                swap_after_mb REAL DEFAULT 0.0,
                swap_delta_mb REAL DEFAULT 0.0,
                disk_before_mb REAL DEFAULT 0.0,
                disk_after_mb REAL DEFAULT 0.0,
                output_size_mb REAL DEFAULT 0.0,
                status TEXT DEFAULT 'SUCCESS',
                created_at TEXT NOT NULL
            )
        """)

        # 3. API Quota Tracking Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_quota_tracking (
                date_str TEXT PRIMARY KEY,
                ai_requests_count INTEGER DEFAULT 0,
                tts_requests_count INTEGER DEFAULT 0,
                uploads_count INTEGER DEFAULT 0,
                rate_limit_hits INTEGER DEFAULT 0,
                failed_requests INTEGER DEFAULT 0,
                updated_at TEXT NOT NULL
            )
        """)

        # Indexing for fast queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_date ON pipeline_jobs(date_str)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_stage ON pipeline_jobs(stage)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_runs_key ON pipeline_runs(job_key)")

        conn.commit()

# Initialize tables on import
init_db()

def get_or_create_job(date_str, story_index, title="", format="short"):
    """Gets an existing job or creates a new PENDING job."""
    job_key = f"{date_str}_{story_index}"
    now_str = get_current_time_str()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pipeline_jobs WHERE job_key = ?", (job_key,))
        row = cursor.fetchone()
        if row:
            # Update title/format if missing
            if title and not row["story_title"]:
                cursor.execute("UPDATE pipeline_jobs SET story_title = ?, story_format = ?, updated_at = ? WHERE job_key = ?",
                               (title, format, now_str, job_key))
                conn.commit()
            return dict(row)
        
        cursor.execute("""
            INSERT INTO pipeline_jobs (job_key, date_str, story_index, story_title, story_format, stage, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?)
        """, (job_key, date_str, story_index, title, format, now_str, now_str))
        conn.commit()
        
        cursor.execute("SELECT * FROM pipeline_jobs WHERE job_key = ?", (job_key,))
        return dict(cursor.fetchone())

def update_job_stage(date_str, story_index, stage, output_path=None, upload_url=None, error_message=None):
    """Updates the stage and relevant attributes of a pipeline job."""
    job_key = f"{date_str}_{story_index}"
    now_str = get_current_time_str()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        updates = ["stage = ?", "updated_at = ?"]
        params = [stage, now_str]
        
        if output_path is not None:
            updates.append("output_path = ?")
            params.append(output_path)
        if upload_url is not None:
            updates.append("upload_url = ?")
            params.append(upload_url)
        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)
            if stage == "FAILED":
                updates.append("retry_count = retry_count + 1")
                
        params.append(job_key)
        sql = f"UPDATE pipeline_jobs SET {', '.join(updates)} WHERE job_key = ?"
        cursor.execute(sql, params)
        conn.commit()

def get_job(date_str, story_index):
    job_key = f"{date_str}_{story_index}"
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pipeline_jobs WHERE job_key = ?", (job_key,))
        row = cursor.fetchone()
        return dict(row) if row else None

def record_run_metrics(job_key, stage, metrics_dict, status="SUCCESS"):
    """Records a benchmark or resource measurement run into pipeline_runs."""
    now_str = get_current_time_str()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO pipeline_runs (
                job_key, stage, wall_time_sec, cpu_time_sec, peak_rss_mb,
                swap_before_mb, swap_after_mb, swap_delta_mb,
                disk_before_mb, disk_after_mb, output_size_mb, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_key,
            stage,
            float(metrics_dict.get("wall_time_sec", 0.0)),
            float(metrics_dict.get("cpu_time_sec", 0.0)),
            float(metrics_dict.get("peak_rss_mb", 0.0)),
            float(metrics_dict.get("swap_before_mb", 0.0)),
            float(metrics_dict.get("swap_after_mb", 0.0)),
            float(metrics_dict.get("swap_delta_mb", 0.0)),
            float(metrics_dict.get("disk_before_mb", 0.0)),
            float(metrics_dict.get("disk_after_mb", 0.0)),
            float(metrics_dict.get("output_size_mb", 0.0)),
            status,
            now_str
        ))
        conn.commit()

class QuotaExceededError(Exception):
    """Raised when an API call exceeds the configured daily free-tier safety limit."""
    pass

def check_api_quota(api_type, date_str=None):
    """
    Checks if an API call is within daily free-tier safety limits.
    api_type: 'ai' | 'tts' | 'upload'
    """
    if not date_str:
        date_str = datetime.now().strftime("%Y%m%d")
        
    limits = {
        "ai": int(os.getenv("MAX_AI_REQUESTS_PER_DAY", "50")),
        "tts": int(os.getenv("MAX_TTS_REQUESTS_PER_DAY", "50")),
        "upload": int(os.getenv("MAX_UPLOADS_PER_DAY", "10"))
    }
    
    max_limit = limits.get(api_type, 100)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM api_quota_tracking WHERE date_str = ?", (date_str,))
        row = cursor.fetchone()
        
        current_count = 0
        if row:
            if api_type == "ai":
                current_count = row["ai_requests_count"]
            elif api_type == "tts":
                current_count = row["tts_requests_count"]
            elif api_type == "upload":
                current_count = row["uploads_count"]
                
        if current_count >= max_limit:
            raise QuotaExceededError(
                f"[FREE-TIER GUARD] Daily limit reached for '{api_type.upper()}': {current_count}/{max_limit}. Halting to prevent billing."
            )
            
    return True

def increment_api_quota(api_type, date_str=None, success=True, is_rate_limit=False):
    """Increments API usage counters for the current day."""
    if not date_str:
        date_str = datetime.now().strftime("%Y%m%d")
    now_str = get_current_time_str()
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM api_quota_tracking WHERE date_str = ?", (date_str,))
        row = cursor.fetchone()
        
        if not row:
            cursor.execute("""
                INSERT INTO api_quota_tracking (date_str, ai_requests_count, tts_requests_count, uploads_count, rate_limit_hits, failed_requests, updated_at)
                VALUES (?, 0, 0, 0, 0, 0, ?)
            """, (date_str, now_str))
            
        col_to_inc = []
        if api_type == "ai":
            col_to_inc.append("ai_requests_count = ai_requests_count + 1")
        elif api_type == "tts":
            col_to_inc.append("tts_requests_count = tts_requests_count + 1")
        elif api_type == "upload":
            col_to_inc.append("uploads_count = uploads_count + 1")
            
        if not success:
            col_to_inc.append("failed_requests = failed_requests + 1")
        if is_rate_limit:
            col_to_inc.append("rate_limit_hits = rate_limit_hits + 1")
            
        col_to_inc.append("updated_at = ?")
        params = [now_str, date_str]
        
        sql = f"UPDATE api_quota_tracking SET {', '.join(col_to_inc)} WHERE date_str = ?"
        cursor.execute(sql, (now_str, date_str) if len(col_to_inc) == 1 else tuple([now_str, date_str]))
        conn.commit()

def get_pipeline_summary(date_str=None):
    """Returns a full dictionary summary of current jobs, runs, and quotas."""
    if not date_str:
        date_str = datetime.now().strftime("%Y%m%d")
        
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM pipeline_jobs WHERE date_str = ? ORDER BY story_index ASC", (date_str,))
        jobs = [dict(r) for r in cursor.fetchall()]
        
        cursor.execute("SELECT * FROM pipeline_runs ORDER BY id DESC LIMIT 10")
        recent_runs = [dict(r) for r in cursor.fetchall()]
        
        cursor.execute("SELECT * FROM api_quota_tracking WHERE date_str = ?", (date_str,))
        quota_row = cursor.fetchone()
        quota = dict(quota_row) if quota_row else {
            "ai_requests_count": 0, "tts_requests_count": 0, "uploads_count": 0, "rate_limit_hits": 0, "failed_requests": 0
        }
        
        return {
            "date_str": date_str,
            "jobs": jobs,
            "recent_runs": recent_runs,
            "quota": quota
        }
