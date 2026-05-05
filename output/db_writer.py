import json


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

    psycopg2 is imported inside the function so a missing or unconfigured DB
    never crashes the app on startup. This function is only called when DB
    credentials are present in .env.

    Returns True on success, False on any failure.
    """
    try:
        import psycopg2
        from psycopg2.extras import Json
    except ImportError:
        print("WARNING: psycopg2 not installed — skipping DB write.")
        return False

    record = tactical_json[0]
    chat   = record.get("chat", [])

    row = {
        "request_id":  record.get("requestId"),
        "originator":  record.get("originator"),
        "label":       record.get("label"),
        "description": record.get("description"),
        "payload":     Json(record),
        "message":     chat[0] if chat else None,
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
        print(f"DB insert OK — requestId: {row['request_id']}  label: {row['label']}")
        return True

    except psycopg2.OperationalError as e:
        print(f"WARNING: DB connection failed: {e}")
    except psycopg2.Error as e:
        print(f"WARNING: DB insert failed: {e}")
    finally:
        if conn:
            conn.close()

    return False
