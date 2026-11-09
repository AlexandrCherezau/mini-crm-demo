from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CRM_DB", str(tmp_path / "test.sqlite3"))
    monkeypatch.delenv("WEBHOOK_TOKEN", raising=False)
    from app import main

    main._hits.clear()
    with TestClient(main.app) as c:
        yield c


def _create(client, **extra):
    body = {"name": "Иван Тестов", "phone": "+7 900 000-00-01", "source": "avito", "amount": 50000}
    body.update(extra)
    res = client.post("/api/leads", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def test_webhook_creates_lead_with_history_and_log(client):
    res = client.post("/api/webhook/lead", json={"name": "Анна Примерова", "phone": "+7 900", "message": "Кухня", "budget": 150000})
    assert res.status_code == 201
    lead_id = res.json()["lead_id"]

    lead = client.get(f"/api/leads/{lead_id}").json()
    assert lead["source"] == "site" and lead["status"] == "new" and lead["amount"] == 150000
    assert lead["request"] == "Кухня"
    assert lead["history"][0]["kind"] == "created"

    log = client.get("/api/webhook/log").json()
    assert log[0]["lead_id"] == lead_id and log[0]["http_status"] == 201


def test_webhook_accepts_form_urlencoded(client):
    res = client.post("/api/webhook/lead", content="name=Пётр+Демов&phone=123&source=telegram",
                      headers={"content-type": "application/x-www-form-urlencoded"})
    assert res.status_code == 201
    assert client.get(f"/api/leads/{res.json()['lead_id']}").json()["source"] == "telegram"


def test_webhook_rejects_invalid_and_logs_it(client):
    res = client.post("/api/webhook/lead", json={"name": "x"})
    assert res.status_code == 422
    assert client.get("/api/webhook/log").json()[0]["http_status"] == 422
    assert client.get("/api/leads").json() == []


def test_webhook_rejects_non_object_json(client):
    assert client.post("/api/webhook/lead", content="[1,2]", headers={"content-type": "application/json"}).status_code == 422


def test_webhook_token_required_when_configured(client, monkeypatch):
    monkeypatch.setenv("WEBHOOK_TOKEN", "s3cret")
    body = {"name": "Вера Образцова"}
    assert client.post("/api/webhook/lead", json=body).status_code == 401
    assert client.post("/api/webhook/lead", json=body, headers={"X-Webhook-Token": "s3cret"}).status_code == 201


def test_webhook_rate_limit(client, monkeypatch):
    from app import main

    monkeypatch.setattr(main, "WEBHOOK_LIMIT_PER_MIN", 2)
    codes = [client.post("/api/webhook/lead", json={"name": "Глеб Макетов"}).status_code for _ in range(3)]
    assert codes == [201, 201, 429]


def test_status_change_persists_and_records_history(client):
    lead = _create(client)
    res = client.patch(f"/api/leads/{lead['id']}/status", json={"status": "paid", "author": "Ольга"})
    assert res.status_code == 200
    stored = client.get(f"/api/leads/{lead['id']}").json()
    assert stored["status"] == "paid" and stored["closed_at"]
    last = stored["history"][-1]
    assert last["kind"] == "status" and last["from_status"] == "new" and last["to_status"] == "paid"
    assert last["author"] == "Ольга"


def test_reopening_clears_closed_at(client):
    lead = _create(client)
    client.patch(f"/api/leads/{lead['id']}/status", json={"status": "lost"})
    stored = client.patch(f"/api/leads/{lead['id']}/status", json={"status": "in_progress"}).json()
    assert stored["closed_at"] is None


def test_invalid_status_and_missing_lead(client):
    lead = _create(client)
    assert client.patch(f"/api/leads/{lead['id']}/status", json={"status": "done"}).status_code == 422
    assert client.patch("/api/leads/999/status", json={"status": "paid"}).status_code == 404
    assert client.get("/api/leads/999").status_code == 404


def test_filters(client):
    _create(client, name="Иван Тестов", source="avito")
    _create(client, name="Мария Шаблонова", source="site", manager="Ольга Кравец")
    assert len(client.get("/api/leads?source=avito").json()) == 1
    assert len(client.get("/api/leads", params={"manager": "Ольга Кравец"}).json()) == 1
    assert client.get("/api/leads", params={"q": "Шаблон"}).json()[0]["name"] == "Мария Шаблонова"
    assert client.get("/api/leads?source=vk").status_code == 422


def test_comment_and_patch(client):
    lead = _create(client)
    res = client.post(f"/api/leads/{lead['id']}/comments", json={"text": "  Перезвонить  "})
    assert res.status_code == 201 and res.json()["history"][-1]["text"] == "Перезвонить"
    patched = client.patch(f"/api/leads/{lead['id']}", json={"amount": 70000, "manager": "Марина Лаптева"}).json()
    assert patched["amount"] == 70000 and patched["manager"] == "Марина Лаптева"
    kinds = [e["kind"] for e in client.get(f"/api/leads/{lead['id']}").json()["history"]]
    assert kinds == ["created", "comment", "amount", "manager"]
    assert client.patch(f"/api/leads/{lead['id']}", json={"manager": "Кто-то"}).status_code == 422


def test_stats_numbers(client):
    a = _create(client, source="avito", amount=100000)
    b = _create(client, source="site", amount=40000)
    _create(client, source="site", amount=10000)
    client.patch(f"/api/leads/{a['id']}/status", json={"status": "paid"})
    client.patch(f"/api/leads/{b['id']}/status", json={"status": "lost"})

    s = client.get("/api/stats").json()
    t = s["totals"]
    assert t["leads"] == 3 and t["paid"] == 1 and t["lost"] == 1 and t["open"] == 1
    assert t["revenue"] == 100000 and t["pipeline"] == 10000 and t["avg_check"] == 100000
    assert t["conversion"] == pytest.approx(1 / 3, abs=1e-3) and t["win_rate"] == 0.5
    avito = next(r for r in s["by_source"] if r["source"] == "avito")
    assert avito["count"] == 1 and avito["conversion"] == 1.0 and avito["revenue"] == 100000
    weeks = s["revenue_by_week"]
    assert len(weeks) == 10 and weeks[-1]["revenue"] == 100000 and weeks[-1]["leads"] == 3


def test_seed_generates_consistent_data(tmp_path, monkeypatch):
    monkeypatch.setenv("CRM_DB", str(tmp_path / "seed.sqlite3"))
    import seed
    from app.db import connect

    seed.seed(count=40)
    conn = connect()
    assert conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0] == 40
    bad = conn.execute(
        "SELECT COUNT(*) FROM leads WHERE (status IN ('paid','lost')) != (closed_at IS NOT NULL)"
    ).fetchone()[0]
    assert bad == 0
    statuses = {r[0] for r in conn.execute("SELECT DISTINCT status FROM leads")}
    assert statuses == {"new", "in_progress", "paid", "lost"}
