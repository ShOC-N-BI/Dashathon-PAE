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
    Insert a completed battle JSON record into the pae_data table.
    Only inserts columns known to exist: message, originator, label, description, payload.
    """
    try:
        import psycopg2
        from psycopg2.extras import Json
    except ImportError:
        print("WARNING: psycopg2 not installed — skipping DB write.")
        return False

    record = tactical_json[0]
    chat   = record.get("chat", [])

    sql = """
        INSERT INTO pae_data (originator, label, description, payload, message)
        VALUES (%(originator)s, %(label)s, %(description)s, %(payload)s, %(message)s)
    """

    row = {
        "originator":  record.get("originator", "rhino"),
        "label":       record.get("label", ""),
        "description": record.get("description", ""),
        "payload":     Json(record),
        "message":     chat[0] if chat else None,
    }

    conn = None
    try:
        conn = psycopg2.connect(
            host=db_host, dbname=db_name, user=db_user,
            password=db_password, port=db_port,
        )
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, row)
        print(f"DB insert OK — label: {row['label']}")
        return True
    except psycopg2.OperationalError as e:
        print(f"WARNING: DB connection failed: {e}")
    except psycopg2.Error as e:
        print(f"WARNING: DB insert failed: {e}")
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    return False
