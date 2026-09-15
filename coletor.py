# -*- coding: utf-8 -*-
"""Coletor de baterias da WSL - roda no GitHub Actions."""
import requests, re, json, os
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

BR = ZoneInfo("America/Sao_Paulo")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}
BASE = "https://www.worldsurfleague.com"
ANO = datetime.now(BR).year
DUR_PADRAO, INTERVALO, HORA_FIM = 30, 5, 17

ORDEM = ["Rodada 1", "Rodada 2", "Oitavas de final",
         "Quartas de final", "Semifinal", "Final", "?"]


def busca(url):
    r = requests.get(url, headers=HEADERS, timeout=45)
    r.raise_for_status()
    return r.text


def classe(el, pref):
    for c in el.get("class", []):
        if c.startswith(pref):
            return c[len(pref):]
    return None


def rodada_de(avanco, nome):
    if not avanco:
        return "Final" if "Final" in (nome or "") else "?"
    a = avanco.upper()
    for chave, valor in (("R2H", "Rodada 1"), ("R3H", "Rodada 2"),
                         ("QFH", "Oitavas de final"), ("SFH", "Quartas de final")):
        if chave in a:
            return valor
    return "Semifinal" if "FINAL" in a else "?"


def traduz(txt):
    """'Round 2, Heat 5 winner' -> 'vencedor da R2H5'"""
    if not txt:
        return txt
    m = re.match(r"Round (\d+), Heat (\d+) winner", txt, re.I)
    if m:
        return f"vencedor da R{m.group(1)}H{m.group(2)}"
    m = re.match(r"(Quarterfinals|Semifinals), Heat (\d+) winner", txt, re.I)
    if m:
        sigla = "QF" if m.group(1).lower().startswith("quarter") else "SF"
        return f"vencedor da {sigla}H{m.group(2)}"
    return txt


# ---------- 1) descobre a etapa em andamento (por data) ----------
CALENDARIO = {
    "436": ("rip-curl-pro-bells-beach",             (4, 1),   (4, 11)),
    "437": ("western-australia-margaret-river-pro", (4, 16),  (4, 26)),
    "438": ("bonsoy-gold-coast-pro",                (5, 2),   (5, 12)),
    "494": ("corona-cero-new-zealand-pro",          (5, 15),  (5, 25)),
    "439": ("surf-city-el-salvador-pro",            (6, 5),   (6, 15)),
    "440": ("vivo-rio-pro",                         (6, 19),  (6, 27)),
    "441": ("outerknown-tahiti-pro",                (8, 8),   (8, 18)),
    "442": ("fiji-pro",                             (8, 25),  (9, 4)),
    "443": ("lexus-trestles-pro",                   (9, 11),  (9, 20)),
    "445": ("meo-rip-curl-pro-portugal",            (10, 16), (10, 25)),
    "543": ("philippines-pro",                      (10, 31), (11, 10)),
    "446": ("lexus-pipe-masters",                   (12, 8),  (12, 20)),
}


def etapa_atual():
    hoje = datetime.now(BR).date()
    proximas = []
    for eid, (slug, ini, fim) in CALENDARIO.items():
        d_ini = datetime(hoje.year, ini[0], ini[1]).date()
        d_fim = datetime(hoje.year, fim[0], fim[1]).date()
        if d_ini <= hoje <= d_fim:
            return eid, slug
        if hoje < d_ini:
            proximas.append((d_ini, eid, slug))
    if proximas:
        proximas.sort()
        return proximas[0][1], proximas[0][2]
    ultima = max(CALENDARIO.items(), key=lambda x: x[1][2])
    return ultima[0], ultima[1][0]


# ---------- 2) coleta as baterias ----------
def coleta(eid, slug, stat_id, genero):
    url = f"{BASE}/events/{ANO}/ct/{eid}/{slug}/results?showAll=1&statEventId={stat_id}"
    soup = BeautifulSoup(busca(url), "html.parser")
    out = []
    for h in soup.select(".hot-heat"):
        nome_el = h.select_one(".heat-name")
        nome = nome_el.get_text(strip=True) if nome_el else ""
        adv_el = h.select_one(".hot-heat__advancement")
        adv = adv_el.get_text(strip=True) if adv_el else None
        st = classe(h, "hot-heat--heat-status-")
        surfistas = []
        for a in h.select(".hot-heat-athlete"):
            cls = " ".join(a.get("class", []))
            n = a.select_one(".hot-heat-athlete__name--full")
            nt = a.select_one(".hot-heat-athlete__score")
            nt = nt.get_text(strip=True) if nt else ""
            surfistas.append({
                "nome": traduz(n.get_text(strip=True)) if n else "?",
                "nota": None if nt in ("", "\u2013\u2013", "--") else nt,
                "colete": classe(a, "hot-heat-athlete--singlet-"),
                "avancou": "advance-winner" in cls,
            })
        num = re.search(r"(\d+)", nome)
        rod = rodada_de(adv, nome)
        out.append({
            "id": classe(h, "hot-heat--heat-id-"),
            "genero": genero,
            "rodada": rod,
            "numero": 1 if rod == "Final" else (int(num.group(1)) if num else 99),
            "status": "encerrada" if st == "over" else
                      ("ao_vivo" if st in ("live", "active", "in-progress") else "aguardando"),
            "surfistas": surfistas,
            "definida": not any(re.search(r"winner|vencedor", s["nome"], re.I)
                                for s in surfistas),
        })
    return out


# ---------- 3) descobre os IDs das divisoes ----------
def stat_ids(eid, slug):
    html = busca(f"{BASE}/events/{ANO}/ct/{eid}/{slug}/results")
    ids = sorted(set(re.findall(r"statEventId=(\d+)", html)))
    if len(ids) >= 2:
        return {"M": ids[0], "F": ids[1]}
    if ids:
        return {"M": ids[0]}
    return {}


# ---------- 4) call do dia ----------
def pega_call(eid, slug):
    soup = BeautifulSoup(busca(f"{BASE}/events/{ANO}/ct/{eid}/{slug}/main"), "html.parser")
    for el in soup.select("[data-timestamp]"):
        try:
            return datetime.fromisoformat(
                el["data-timestamp"].replace("Z", "+00:00")).astimezone(BR)
        except Exception:
            continue
    return None


# ---------- 5) estado (aprende o ritmo real) ----------
def carrega_estado():
    if os.path.exists("estado.json"):
        try:
            return json.load(open("estado.json", encoding="utf-8"))
        except Exception:
            pass
    return {"encerramentos": {}, "duracoes": []}


def atualiza_estado(estado, baterias, agora):
    for b in baterias:
        if b["status"] == "encerrada" and b["id"] not in estado["encerramentos"]:
            estado["encerramentos"][b["id"]] = agora.isoformat()
    marcos = sorted(datetime.fromisoformat(v) for v in estado["encerramentos"].values())
    dur = []
    for a, b in zip(marcos, marcos[1:]):
        delta = (b - a).total_seconds() / 60
        if 10 <= delta <= 90:
            dur.append(delta)
    estado["duracoes"] = dur[-12:]
    return estado


def duracao_real(estado):
    d = estado.get("duracoes") or []
    if len(d) >= 3:
        return round(sum(d) / len(d))
    return DUR_PADRAO + INTERVALO


# ---------- 6) monta os horarios ----------
def monta(baterias, call, passo, agora):
    pend = [b for b in baterias if b["status"] != "encerrada"]
    pend.sort(key=lambda b: (ORDEM.index(b["rodada"]), b["numero"], b["genero"]))

    tem_call = bool(call and call.date() <= agora.date() + timedelta(days=1))
    t = call if tem_call else None
    if t and t < agora:
        t = agora
    fim = t.replace(hour=HORA_FIM + 4, minute=0) if t else None
    dia = 1

    for b in pend:
        if not t:
            b["dia_competicao"] = dia
            b["quando"] = "aguardando call" if dia == 1 else f"Dia {dia} \u00b7 aguardando call"
            b["estado"] = "aguardando_call"
            continue
        if t + timedelta(minutes=passo) > fim:
            dia += 1
            t = None
            b["dia_competicao"] = dia
            b["quando"] = f"Dia {dia} \u00b7 aguardando call"
            b["estado"] = "aguardando_call"
            continue
        b["dia_competicao"] = dia
        b["quando"] = f"{t.strftime('%d/%m')} \u00b7 {t.strftime('%H:%M')}"
        b["estado"] = "com_horario"
        t += timedelta(minutes=passo)

    for b in baterias:
        if b["status"] == "encerrada":
            b["quando"], b["estado"], b["dia_competicao"] = "encerrada", "encerrada", 0
        b.setdefault("dia_competicao", 9)
        b.setdefault("quando", "aguardando call")
        b.setdefault("estado", "aguardando_call")
    return baterias


# ---------- principal ----------
def main():
    agora = datetime.now(BR)
    eid, slug = etapa_atual()
    print("etapa:", eid, slug)
    if not eid:
        raise SystemExit("nao encontrei nenhuma etapa")

    ids = stat_ids(eid, slug)
    print("divisoes:", ids)

    baterias = []
    for genero, sid in ids.items():
        b = coleta(eid, slug, sid, genero)
        print(f"  {genero}: {len(b)} baterias")
        baterias += b

    call = pega_call(eid, slug)
    print("call:", call)

    estado = atualiza_estado(carrega_estado(), baterias, agora)
    passo = duracao_real(estado)
    print("passo (min):", passo, "| amostras:", len(estado["duracoes"]))

    baterias = monta(baterias, call, passo, agora)
    baterias.sort(key=lambda b: (ORDEM.index(b["rodada"]), b["numero"], b["genero"]))

    ao_vivo = next((b for b in baterias if b["status"] == "ao_vivo"), None)
    proxima = next((b for b in baterias if b["status"] == "aguardando"), None)

    app = {
        "atualizado_em": agora.strftime("%d/%m/%Y %H:%M"),
        "evento": {"nome": slug.replace("-", " ").title(), "id": eid},
        "call": call.strftime("%d/%m \u00e0s %H:%M") if call else None,
        "passo_estimado_min": passo,
        "ao_vivo": ao_vivo,
        "proxima": proxima,
        "baterias": baterias,
    }
    json.dump(app, open("app.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump(estado, open("estado.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"OK - {len(baterias)} baterias salvas")


if __name__ == "__main__":
    main()
