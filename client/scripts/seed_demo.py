"""
Seed demo data (optional).
Run:
  python client/scripts/seed_demo.py
"""
import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import date, timedelta
import random

from db_local import connect, init_schema, set_setting
from services import (
    create_farm_local, add_income, add_expense, list_categories,
    upsert_inventory_item, add_inventory_movement,
    upsert_cattle, add_vaccination
)

if __name__ == "__main__":
    with connect() as conn:
        init_schema(conn)
        farm_id = create_farm_local(conn, "Fazenda Demo", "BRL", "America/Sao_Paulo")
        set_setting(conn, "active_farm_id", farm_id)

        cats = list_categories(conn, farm_id)
        cat_ids = [c["id"] for c in cats]

        today = date.today()
        for i in range(20):
            d = today - timedelta(days=i*3)
            add_income(conn, farm_id, d.isoformat(), f"Venda {i}", random.uniform(200, 1200), "Venda")
            add_expense(conn, farm_id, d.isoformat(), random.choice(cat_ids), f"Compra {i}", random.uniform(50, 600), "Fornecedor", random.choice([0,1])==1)

        # inventory
        feed = upsert_inventory_item(conn, farm_id, "Ração 20kg", "FEED", "kg", 50)
        vac = upsert_inventory_item(conn, farm_id, "Vacina A", "VACCINE", "dose", 10)
        add_inventory_movement(conn, farm_id, feed, today.isoformat(), 200, 800, "IN", "Compra inicial")
        add_inventory_movement(conn, farm_id, feed, today.isoformat(), 40, 0, "OUT", "Consumo")
        add_inventory_movement(conn, farm_id, vac, today.isoformat(), 30, 300, "IN", "Lote vacinas")

        # cattle + vaccination
        c1 = upsert_cattle(conn, farm_id, "BR-001", None, "")
        add_vaccination(conn, farm_id, c1, vac, today.isoformat(), "1 dose", 10, (today + timedelta(days=5)).isoformat())

    print("✅ Dados demo inseridos. Abra o app e veja o Dashboard.")
