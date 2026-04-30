import json
import psycopg2
from psycopg2.extras import Json


def insert(
    tactical_json: list,
    db_host: str,
    db_name: str,
    db_user: str,
    db_password: str,
    db_port: int = 5432,
) -> bool:
    """
    Insert a completed battle JSON record as a new row in the pae_data table.

    Each reassessment is always a fresh INSERT — never an UPDATE — so the
    original row is preserved alongside the new assessment.

    The inserted row captures:
        - request_id  : the unique track ID from the JSON
        - originator  : the source username or label (IRC nick or "SSE")
        - label       : short tactical title from the AI
        - description : strategic summary from the AI
        - payload     : the full battle JSON stored as JSONB
        - message     : the original raw chat message

    Parameters
    ----------
    tactical_json : The completed battle JSON list from ai.agent.
    db_*          : Postgres connection parameters from config.py.

    Returns
    -------
    True on success, False on any failure.
    """
    record   = tactical_json[0]
    chat     = record.get("chat", [])

    row = {
        "request_id":  record.get("requestId"),
        "originator":  record.get("originator"),
        "label":       record.get("label"),
        "description": record.get("description"),
        "payload":     Json(record),                    # full JSON stored as JSONB
        "message":     chat[0] if chat else None,       # original raw message
    }

    sql = """
        INSERT INTO pae_data
            (request_id, originator, label, description, payload, message)
        VALUES
            (%(request_id)s, %(originator)s, %(label)s, %(description)s, %(payload)s, %(message)s)
    """

    conn = None
    try:
        conn = psycopg2.connect(
            host=db_host,
            dbname=db_name,
            user=db_user,
            password=db_password,
            port=db_port,
        )
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, row)
        print(f"💾  DB insert OK — requestId: {row['request_id']}  label: {row['label']}")
        return True

    except psycopg2.OperationalError as e:
        print(f"⚠️  DB connection failed: {e}")
    except psycopg2.Error as e:
        print(f"⚠️  DB insert failed: {e}")
    finally:
        if conn:
            conn.close()

    return False
