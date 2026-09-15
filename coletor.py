# -*- coding: utf-8 -*-
"""Coletor de baterias da WSL - roda no GitHub Actions."""
import requests, re, json, os
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

BR = ZoneInfo("America/Sao_Paulo")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}
BASE = "https://www.worldsurfleague.com"
ANO = datetime.now(BR).year
DIAS_BARRA = 15
DUR_PADRAO, INTERVALO = 30, 5
HORA_INI_LOCAL, HORA_FIM_LOCAL = 7, 17          # janela de surf no fuso do evento

ORDEM = ["Rodada 1", "Rodada 2", "Oitavas de final",
         "Quartas de final", "Semifinal", "Final", "?"]
SEMANA = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]

# etapa: (slug, inicio, fim, fuso do local)
CALENDARIO = {
    "436": ("rip-curl-pro-bells-beach",             (4, 1),   (4, 11),  "Australia/Melbourne"),
    "437": ("western-australia-margaret-river-pro", (4, 16),  (4, 26),  "Australia/Perth"),
    "438": ("bonsoy-gold-coast-pro",                (5, 2),   (5, 12),  "Australia/Brisbane"),
    "494": ("corona-cero-new-zealand-pro",          (5, 15),  (5, 25),  "Pacific/Auckland"),
    "439": ("surf-city-el-salvador-pro",            (6, 5),   (6, 15),  "America/El_Salvador"),
    "440": ("vivo-rio-pro",                         (6, 19),  (6, 27),  "America/Sao_Paulo"),
    "441": ("outerknown-tahiti-pro",                (8, 8),   (8, 18),  "Pacific/Tahiti"),
    "442": ("fiji-pro",                             (8, 25),  (9, 4),   "Pacific/Fiji"),
    "443": ("lexus-trestles-pro",                   (9, 11),  (9, 20),  "America/Los_Angeles"),
    "445": ("meo-rip-curl-pro-portugal",            (10, 16), (10, 25), "Europe/Lisbon"),
    "543": ("philippines-pro",                      (10, 31), (11, 10), "Asia/Manila"),
    "446": ("lexus-pipe-masters",                   (12, 8),  (12, 20), "Pacific/Honolulu"),
}

NOMES = {
    "436": "Rip Curl Pro Bells Beach", "437": "Margaret River Pro",
    "438": "Bonsoy Gold Coast Pro", "494": "Corona Cero New Zealand Pro",
    "439": "Surf City El Salvador Pro", "440": "VIVO Rio Pro",
    "441": "Outerknown Tahiti Pro", "442": "Fiji Pro",
    "443": "Lexus Trestles Pro", "445": "MEO Rip Curl Pro Portugal",
    "543": "Philippines Pro", "446": "Lexus Pipe Masters",
}


# pais de cada surfista do CT 2026 (a WSL nao expoe isso no HTML)
PAISES = {
    "Yago Dora": "BRA", "Griffin Colapinto": "USA", "Jordy Smith": "RSA",
    "Italo Ferreira": "BRA", "Jack Robinson": "AUS", "Ethan Ewing": "AUS",
    "Kanoa Igarashi": "JPN", "Filipe Toledo": "BRA", "Leonardo Fioravanti": "ITA",
    "Cole Houshmand": "USA", "Barron Mamiya": "HAW", "Connor O'Leary": "JPN",
    "Miguel Pupo": "BRA", "Jake Marshall": "USA", "Crosby Colapinto": "USA",
    "Marco Mignot": "FRA", "Joao Chianca": "BRA", "Joel Vaughan": "AUS",
    "Alan Cleland": "MEX", "Rio Waida": "INA", "Seth Moniz": "HAW",
    "Alejo Muniz": "BRA", "Kauli Vaast": "FRA", "Eli Hanneman": "HAW",
    "Morgan Cibilic": "AUS", "George Pittar": "AUS", "Samuel Pupo": "BRA",
    "Callum Robson": "AUS", "Luke Thompson": "RSA", "Oscar Berry": "AUS",
    "Mateus Herdy": "BRA", "Liam O'Brien": "AUS", "Gabriel Medina": "BRA",
    "Ramzi Boukhiam": "MAR", "Matthew McGillivray": "RSA",
    "Hayden Rodgers": "AUS", "Taj Lindblad": "USA",
    "Molly Picklum": "AUS", "Caroline Marks": "USA", "Gabriela Bryan": "HAW",
    "Caitlin Simmers": "USA", "Bettylou Sakura Johnson": "HAW",
    "Isabella Nichols": "AUS", "Tyler Wright": "AUS", "Erin Brooks": "CAN",
    "Lakey Peterson": "USA", "Luana Silva": "BRA", "Sawyer Lindblad": "USA",
    "Vahine Fierro": "FRA", "Bella Kenworthy": "USA", "Brisa Hennessy": "CRC",
    "Tya Zebrowski": "FRA", "Yolanda Hopkins": "POR", "Sally Fitzgibbons": "AUS",
    "Alyssa Spencer": "USA", "Francisca Veselko": "POR", "Nadia Erostarbe": "ESP",
    "Anat Lelior": "ISR", "Carissa Moore": "HAW", "Stephanie Gilmore": "AUS",
    "Annette Gonzalez Etxabarri": "ESP", "Kirra Pinkerton": "USA", "Eden Walla": "USA",
}


def pais_de(nome):
    if not nome or re.search(r"vencedor", nome, re.I):
        return None
    if nome in PAISES:
        return PAISES[nome]
    sobren = nome.split()[-1].lower()
    for k, v in PAISES.items():
        if k.split()[-1].lower() == sobren:
            return v
    return None


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


# ---------- etapa em andamento (por data) ----------
def etapa_atual():
    hoje = datetime.now(BR).date()
    proximas = []
    for eid, (slug, ini, fim, tz) in CALENDARIO.items():
        d_ini = date(hoje.year, ini[0], ini[1])
        d_fim = date(hoje.year, fim[0], fim[1])
        if d_ini <= hoje <= d_fim:
            return eid, slug, d_ini, d_fim, tz
        if hoje < d_ini:
            proximas.append((d_ini, eid, slug, d_fim, tz))
    if proximas:
        proximas.sort()
        d_ini, eid, slug, d_fim, tz = proximas[0]
        return eid, slug, d_ini, d_fim, tz
    eid = max(CALENDARIO, key=lambda k: CALENDARIO[k][2])
    slug, ini, fim, tz = CALENDARIO[eid]
    return eid, slug, date(hoje.year, *ini), date(hoje.year, *fim), tz


# ---------- coleta ----------
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
            nome_lim = traduz(n.get_text(strip=True)) if n else "?"
            surfistas.append({
                "nome": nome_lim,
                "pais": pais_de(nome_lim),
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


def stat_ids(eid, slug):
    html = busca(f"{BASE}/events/{ANO}/ct/{eid}/{slug}/results")
    ids = sorted(set(re.findall(r"statEventId=(\d+)", html)))
    if len(ids) >= 2:
        return {"M": ids[0], "F": ids[1]}
    return {"M": ids[0]} if ids else {}


def pega_call(eid, slug):
    soup = BeautifulSoup(busca(f"{BASE}/events/{ANO}/ct/{eid}/{slug}/main"), "html.parser")
    for el in soup.select("[data-timestamp]"):
        try:
            return datetime.fromisoformat(
                el["data-timestamp"].replace("Z", "+00:00")).astimezone(BR)
        except Exception:
            continue
    return None


# ---------- estado ----------
def carrega_estado():
    if os.path.exists("estado.json"):
        try:
            return json.load(open("estado.json", encoding="utf-8"))
        except Exception:
            pass
    return {"encerramentos": {}, "duracoes": [], "datas": {}}


def atualiza_estado(estado, baterias, agora):
    estado.setdefault("datas", {})
    for b in baterias:
        if b["status"] == "encerrada" and b["id"] not in estado["encerramentos"]:
            estado["encerramentos"][b["id"]] = agora.isoformat()
            estado["datas"][b["id"]] = agora.strftime("%Y-%m-%d")
    marcos = sorted(datetime.fromisoformat(v) for v in estado["encerramentos"].values())
    dur = [(b - a).total_seconds() / 60 for a, b in zip(marcos, marcos[1:])
           if 10 <= (b - a).total_seconds() / 60 <= 90]
    estado["duracoes"] = dur[-12:]
    return estado


def duracao_real(estado):
    d = estado.get("duracoes") or []
    return round(sum(d) / len(d)) if len(d) >= 3 else DUR_PADRAO + INTERVALO


# ---------- distribuicao por dia ----------
def distribui(baterias, call, passo, hoje, d_fim, tz_evento, agora, datas_reg=None):
    """Marca cada bateria pendente com data e horario."""
    tz = ZoneInfo(tz_evento)
    pend = [b for b in baterias if b["status"] != "encerrada"]
    pend.sort(key=lambda b: (ORDEM.index(b["rodada"]), b["numero"], b["genero"]))

    # dias candidatos: do dia da call (ou hoje) ate o fim da etapa
    inicio = call.date() if call else hoje
    if inicio < hoje:
        inicio = hoje
    dias = []
    d = inicio
    while d <= d_fim:
        dias.append(d)
        d += timedelta(days=1)
    if not dias:
        dias = [hoje]

    idx = 0
    for dia in dias:
        if idx >= len(pend):
            break
        tem_call = bool(call and call.date() == dia)
        # janela do dia no fuso do evento
        ini_dia = datetime.combine(dia, datetime.min.time(), tz).replace(hour=HORA_INI_LOCAL)
        if tem_call:
            ini_dia = call.astimezone(tz)
            if ini_dia < agora.astimezone(tz):
                ini_dia = agora.astimezone(tz)
        fim_dia = datetime.combine(dia, datetime.min.time(), tz).replace(hour=HORA_FIM_LOCAL)
        t = ini_dia
        while idx < len(pend) and t + timedelta(minutes=passo) <= fim_dia:
            b = pend[idx]
            br = t.astimezone(BR)
            b["data"] = br.strftime("%Y-%m-%d")
            b["dia_rotulo"] = br.strftime("%d/%m")
            if tem_call:
                b["horario"] = br.strftime("%H:%M")
                b["quando"] = br.strftime("%H:%M")
                b["estado"] = "com_horario"
            else:
                b["horario"] = None
                b["quando"] = "aguardando call"
                b["estado"] = "aguardando_call"
            t += timedelta(minutes=passo)
            idx += 1

    # sobras (nao couberam na etapa): sem data
    for b in pend[idx:]:
        b["data"] = None
        b["dia_rotulo"] = None
        b["horario"] = None
        b["quando"] = "aguardando call"
        b["estado"] = "aguardando_call"

    for b in baterias:
        if b["status"] == "encerrada":
            d = (datas_reg or {}).get(b["id"])
            b["data"] = d
            b["dia_rotulo"] = datetime.strptime(d, "%Y-%m-%d").strftime("%d/%m") if d else None
            b["horario"] = None
            b["quando"] = "encerrada"
            b["estado"] = "encerrada"
    return baterias


def monta_barra(baterias, call, hoje, nome_evento):
    """15 dias: vazio / previsto (prancha apagada) / call (prancha cheia)."""
    conta = {}
    for b in baterias:
        if b.get("data"):
            conta[b["data"]] = conta.get(b["data"], 0) + 1
    barra = []
    for i in range(DIAS_BARRA):
        d = hoje + timedelta(days=i)
        chave = d.strftime("%Y-%m-%d")
        qtd = conta.get(chave, 0)
        if qtd == 0:
            estado = "vazio"
        elif call and call.date() == d:
            estado = "call"
        else:
            estado = "previsto"
        barra.append({
            "data": chave,
            "dia": d.strftime("%d"),
            "mes": d.strftime("%m"),
            "semana": SEMANA[d.weekday()],
            "estado": estado,
            "qtd": qtd,
            "evento": nome_evento if qtd else None,
            "hoje": i == 0,
        })
    return barra


# ---------- principal ----------
def main():
    agora = datetime.now(BR)
    hoje = agora.date()
    eid, slug, d_ini, d_fim, tz_evento = etapa_atual()
    nome_evento = NOMES.get(eid, slug.replace("-", " ").title())
    print("etapa:", eid, slug, f"({d_ini} a {d_fim})")

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

    baterias = distribui(baterias, call, passo, hoje, d_fim, tz_evento, agora,
                         estado.get("datas"))
    baterias.sort(key=lambda b: (ORDEM.index(b["rodada"]), b["numero"], b["genero"]))
    barra = monta_barra(baterias, call, hoje, nome_evento)

    print("\nBARRA DE DIAS:")
    for d in barra:
        marca = {"call": "[prancha cheia]", "previsto": "[prancha vazia]", "vazio": ""}[d["estado"]]
        print(f"  {d['semana']} {d['dia']}/{d['mes']}  {marca} {d['qtd'] or ''}")

    ao_vivo = next((b for b in baterias if b["status"] == "ao_vivo"), None)
    proxima = next((b for b in baterias if b["status"] == "aguardando"), None)

    app = {
        "atualizado_em": agora.strftime("%d/%m/%Y %H:%M"),
        "evento": {"nome": nome_evento, "id": eid,
                   "inicio": d_ini.strftime("%Y-%m-%d"),
                   "fim": d_fim.strftime("%Y-%m-%d")},
        "call": call.strftime("%d/%m \u00e0s %H:%M") if call else None,
        "call_data": call.strftime("%Y-%m-%d") if call else None,
        "passo_estimado_min": passo,
        "dias": barra,
        "ao_vivo": ao_vivo,
        "proxima": proxima,
        "baterias": baterias,
    }
    json.dump(app, open("app.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump(estado, open("estado.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nOK - {len(baterias)} baterias salvas")


if __name__ == "__main__":
    main()
