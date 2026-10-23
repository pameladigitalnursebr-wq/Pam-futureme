"""Painel executivo em HTML (arquivo único, abre no navegador) para o recorte pedido."""

from __future__ import annotations

import html
from datetime import datetime

from . import consultas as q

SECOES = (("instituicao", "Instituições mais desejadas"), ("curso", "Cursos mais procurados"),
          ("cidade", "Cidades"), ("uf", "Estados"), ("modalidade", "Modalidade"), ("posicao", "Posição da opção"))


def _n(v) -> str:
    return f"{v:,}".replace(",", ".")


def _barras(itens: list[dict]) -> str:
    if not itens:
        return '<p class="vazio">Sem resultados para este recorte.</p>'
    maximo = max(i["alunos"] for i in itens) or 1
    linhas = []
    for i in itens:
        largura = 100 * i["alunos"] / maximo
        dica = f'{i["nome"]}: {_n(i["alunos"])} alunos · {_n(i["interesses"])} interesses'
        linhas.append(
            f'<div class="barra" title="{html.escape(dica)}"><span class="nome">{html.escape(str(i["nome"]))}</span>'
            f'<span class="trilho"><span class="valor-barra" style="width:{largura:.1f}%"></span></span>'
            f'<span class="num">{_n(i["alunos"])} · {str(i["percentual_dos_alunos"]).replace(".", ",")}%</span></div>')
    return "\n".join(linhas)


def gerar(conn, f: q.Filtros, aplicados: list[dict], titulo: str = "Inteligência Comercial") -> str:
    r = q.resumo(conn, f)
    st = q.status(conn)
    recorte = "; ".join(f'{q.DIMS[a["filtro"]].titulo}: {", ".join(a["valores"])}' for a in aplicados) or "Base inteira"
    kpis = [("Alunos interessados", r["alunos"], "alunos distintos"), ("Interesses", r["interesses"], "até 3 por aluno"),
            ("Instituições", r["instituicoes"], "com interessados"), ("Cursos", r["cursos"], "no pódio dos alunos"),
            ("Estados", r["estados"], "da escola do aluno"), ("Cidades", r["cidades"], f'{_n(r["escolas"])} escolas')]
    secoes = []
    for dim, nome in SECOES:
        itens = q.ranking(conn, dim, f, 10)["itens"]
        if dim == "posicao":
            itens.sort(key=lambda i: i["chave"])
        secoes.append(f'<section class="cartao"><h2>{nome}</h2>{_barras(itens)}</section>')
    avisos = "".join(f'<p class="aviso">{html.escape(a)}</p>' for a in r["avisos"])
    leads = st["ultimas_importacoes"].get("leads", {})
    data_base = "—"
    if leads.get("em_utc"):
        data_base = datetime.fromisoformat(leads["em_utc"]).strftime("%d/%m/%Y")
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(titulo)}</title>
<style>
:root {{ color-scheme: light; --fundo:#f6f6f4; --sup:#fcfcfb; --borda:#e3e2de; --texto:#0b0b0b; --texto2:#52514e;
  --mudo:#7a7975; --serie:#2a78d6; --aviso:#fff6e0; --aviso-borda:#eda100; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ color-scheme: dark; --fundo:#121211;
  --sup:#1a1a19; --borda:#2e2e2c; --texto:#f0efec; --texto2:#c3c2b7; --mudo:#8f8e88; --serie:#3987e5;
  --aviso:#2d2510; --aviso-borda:#c98500; }} }}
* {{ box-sizing: border-box; }}
body {{ margin:0; padding:24px 16px; background:var(--fundo); color:var(--texto);
  font:14px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }}
main {{ max-width:1200px; margin:0 auto; display:grid; gap:16px; }}
h1 {{ font-size:22px; margin:0; }} h2 {{ font-size:15px; margin:0 0 12px; }}
.mudo {{ color:var(--mudo); }}
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; }}
.kpi, .cartao {{ background:var(--sup); border:1px solid var(--borda); border-radius:10px; padding:14px; }}
.kpi .v {{ font-size:28px; font-weight:700; font-variant-numeric:tabular-nums; }}
.kpi .r {{ color:var(--texto2); }} .kpi .n {{ color:var(--mudo); font-size:12px; }}
.grade {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,520px),1fr)); gap:16px; }}
.barra {{ display:grid; grid-template-columns:minmax(110px,42%) minmax(0,1fr) auto; gap:10px; align-items:center;
  padding:3px 0; }}
.nome {{ overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
.trilho {{ height:14px; }} .valor-barra {{ display:block; height:100%; background:var(--serie);
  border-radius:0 4px 4px 0; min-width:2px; }}
.num {{ color:var(--texto2); font-variant-numeric:tabular-nums; white-space:nowrap; font-size:13px; }}
.aviso {{ background:var(--aviso); border:1px solid var(--aviso-borda); border-radius:8px; padding:8px 12px; margin:0; }}
.vazio {{ color:var(--mudo); }}
</style></head>
<body><main>
<header><h1>{html.escape(titulo)}</h1>
<p class="mudo">Recorte: {html.escape(recorte)} · Base atualizada em {data_base} ·
gerado em {datetime.now():%d/%m/%Y %H:%M}</p></header>
{avisos}
<div class="kpis">{"".join(f'<div class="kpi"><div class="r">{a}</div><div class="v">{_n(b)}</div><div class="n">{c}</div></div>' for a, b, c in kpis)}</div>
<div class="grade">{"".join(secoes)}</div>
<p class="mudo">Alunos = pessoas distintas; interesses = opções de instituição (até 3 por aluno). Estado e cidade são da
escola do aluno. Passe o mouse nas barras para ver os números.</p>
</main></body></html>"""
