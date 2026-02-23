# Rural SaaS (Offline-first) — Streamlit + SQLite + FastAPI (opcional)

Projeto **simples e clean** para gestão rural com:
- **Cliente Windows** (Streamlit) que roda **offline** com **SQLite**
- **Servidor SaaS opcional** (FastAPI) para **login + multi-fazendas + sincronização leve**
- Sincronização **push/pull** sob demanda usando `updated_at` / `deleted_at` (**last write wins**)

> Core: **Financeiro, Estoque, Vacinação, Dashboards, Alertas**, Exportar CSV, Dark Mode.

---

## Estrutura

```
repo/
  README.md
  requirements_client.txt
  requirements_server.txt
  client/
    app.py
    db_local.py
    services.py
    analytics.py
    ui.py
    sync_client.py
    scripts/
      init_local_db.py
      seed_demo.py
    data/
      local.db (gerado)
  server/
    main.py
    db_server.py
    models_server.sql
    auth.py
    sync_api.py
    scripts/
      init_server_db.py
    data/
      server.db (gerado)
```

---

## 1) Rodar o cliente (offline total)

### Requisitos
- Python **3.11+** (Windows)

### Passos
```bash
pip install -r requirements_client.txt
python client/scripts/init_local_db.py
streamlit run client/app.py
```

No login, clique em **"Continuar offline"** (ou use um e-mail qualquer).
- Você consegue criar fazendas, lançar receitas/despesas, estoque, vacinação e ver dashboards.
- A sincronização fica desabilitada sem servidor.

---

## 2) Rodar o servidor (modo SaaS opcional)

```bash
pip install -r requirements_server.txt
python server/scripts/init_server_db.py
uvicorn server.main:app --reload
```

Servidor padrão: `http://127.0.0.1:8000`

---

## 3) Rodar cliente com servidor (SaaS + Sync)

1) Suba o servidor.
2) Abra o cliente e, na tela de login:
   - Informe a URL do servidor (ex.: `http://127.0.0.1:8000`)
   - Crie conta em **Registrar**
   - Faça **Login**

Depois:
- Crie fazenda no servidor (**Criar fazenda**)
- Selecione a fazenda ativa
- Clique **"Sincronizar agora"** (push/pull)

### Como funciona a sync
- Cada registro tem: `id` (UUID string), `created_at`, `updated_at`, `deleted_at`
- Conflitos: **last write wins** por `updated_at` (**server vence se empate**)
- O cliente guarda `local_meta.last_sync_at`
- Sync:
  1) **push** mudanças locais desde `last_sync_at`
  2) **pull** mudanças do servidor desde `last_sync_at`
  3) aplica **upsert** no SQLite local
  4) atualiza `last_sync_at`

---

## Exportar CSV
Em cada seção (Financeiro, Estoque, Vacinação) há botões para exportar CSV.

---

## Observações (MVP)
- Banco local é a fonte principal offline.
- Sem Docker / Celery / Alembic.
- Código focado em funções simples e diretas.
- Segurança de convite é minimalista (MVP). Para produção: expiração curta, rotação, auditoria, etc.

---

## Troubleshooting (Windows)
Se o Streamlit não abrir:
- Rode: `python -m streamlit run client/app.py`
Se houver problema com dependências:
- Atualize pip: `python -m pip install --upgrade pip`

