import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db_server import connect, init_schema

if __name__ == "__main__":
    with connect() as conn:
        init_schema(conn)
    print("✅ Banco do servidor inicializado em server/data/server.db")
