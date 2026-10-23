#!/usr/bin/env python3
"""Linha de comando do modo Cowork. Toda resposta sai em JSON, para o Claude ler e explicar.

Exemplos:
  python painel.py status
  python painel.py importar "Base de leads.xlsx"
  python painel.py resumo --instituicao UNIP --curso Administração
  python painel.py ranking curso --cidade Campinas --limite 10
  python painel.py buscar "puc camp"
  python painel.py dashboard --uf SP --saida painel.html
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from motor import banco, consultas as q, importacao  # noqa: E402
from motor import dashboard  # noqa: E402

FILTROS = ("instituicao", "grupo", "curso", "modalidade", "uf", "cidade", "regiao_ensino", "regiao_geografica",
           "escola", "posicao", "ano_cadastro", "genero", "faixa_etaria", "status_comercial", "situacao_atual",
           "plano_pos_medio", "aceita_comunicados")


def _saida(dados) -> None:
    print(json.dumps(dados, ensure_ascii=False, indent=1, default=str))


def _com_filtros(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("filtros (repita a opção para OU: --cidade Campinas --cidade Sorocaba)")
    for nome in FILTROS:
        g.add_argument(f"--{nome.replace('_', '-')}", dest=nome, action="append", metavar="NOME")
    g.add_argument("--incluir-suspeitas", action="store_true",
                   help="inclui respostas livres que não parecem instituição ('não sei', '3'...)")


def _filtros(conn, args):
    por_nome = {n: getattr(args, n) for n in FILTROS if getattr(args, n, None)}
    return q.resolver(conn, por_nome, args.incluir_suspeitas)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="painel.py", description="Inteligência Comercial FutureMe (modo Cowork)")
    p.add_argument("--base", type=Path, help="arquivo do banco (padrão: ./dados_painel/base_comercial.db)")
    sub = p.add_subparsers(dest="comando", required=True)

    sub.add_parser("status", help="situação da base")
    s = sub.add_parser("importar", help="importa uma planilha (.xlsx ou .csv)")
    s.add_argument("arquivo", type=Path)
    s.add_argument("--modo", choices=["completo", "incremental"], default="completo")
    s.add_argument("--forcar", action="store_true")
    s = sub.add_parser("buscar", help="procura nomes na base")
    s.add_argument("termo")
    s.add_argument("--dimensao", choices=list(q.DIMS))
    s.add_argument("--limite", type=int, default=8)
    s = sub.add_parser("resumo", help="totais para os filtros")
    _com_filtros(s)
    s = sub.add_parser("ranking", help="ranking/distribuição por uma dimensão")
    s.add_argument("dimensao", choices=list(q.DIMS))
    s.add_argument("--limite", type=int, default=10)
    _com_filtros(s)
    s = sub.add_parser("detalhar", help="alunos do recorte (sem dados pessoais)")
    s.add_argument("--pagina", type=int, default=1)
    s.add_argument("--por-pagina", type=int, default=20)
    _com_filtros(s)
    s = sub.add_parser("historico", help="total de leads por ano (base de instituições)")
    s.add_argument("dimensao", choices=["instituicao", "curso"])
    s.add_argument("nome")
    s = sub.add_parser("comparar", help="variação desde a importação anterior")
    s.add_argument("dimensao", choices=["instituicao", "curso", "uf", "cidade"])
    s.add_argument("--limite", type=int, default=15)
    s = sub.add_parser("exportar", help="exporta os alunos do recorte para .csv ou .xlsx")
    s.add_argument("--saida", type=Path, required=True)
    _com_filtros(s)
    s = sub.add_parser("dashboard", help="gera o painel executivo em HTML")
    s.add_argument("--saida", type=Path, default=Path("painel_comercial.html"))
    s.add_argument("--titulo", default="Inteligência Comercial · FutureMe")
    _com_filtros(s)
    s = sub.add_parser("pendentes", help="instituições para revisar")
    s.add_argument("--limite", type=int, default=30)
    s = sub.add_parser("unificar", help="junta a instituição ORIGEM na DESTINO (por id)")
    s.add_argument("origem_id", type=int)
    s.add_argument("destino_id", type=int)
    s = sub.add_parser("marcar", help="marca instituição como ok ou suspeita (por id)")
    s.add_argument("instituicao_id", type=int)
    s.add_argument("qualidade", choices=["ok", "suspeita"])

    args = p.parse_args(argv)
    conn = banco.conectar(args.base)
    try:
        return _executar(conn, args)
    except importacao.ImportacaoRejeitada as e:
        _saida({"rejeitada": True, "mensagem": str(e)})
        return 3
    except q.Ambiguo as a:
        if a.opcoes:
            _saida({"ambiguo": True, "filtro": a.dimensao, "termo": a.termo,
                    "mensagem": "Mais de um valor corresponde ao termo. Pergunte qual a pessoa quer.",
                    "opcoes": [{"nome": o["nome"], "alunos": o["alunos"]} for o in a.opcoes]})
        else:
            _saida({"encontrado": False, "filtro": a.dimensao, "termo": a.termo,
                    "mensagem": f"Nenhum valor de '{a.dimensao}' corresponde a '{a.termo}' na base."})
        return 4
    except ValueError as e:
        _saida({"erro": str(e)})
        return 2
    finally:
        conn.close()


def _executar(conn, args) -> int:
    c = args.comando
    if c != "importar" and c != "status" and not q.status(conn)["base_carregada"]:
        _saida({"erro": "Base vazia. Importe primeiro as planilhas: python painel.py importar <arquivo.xlsx>"})
        return 2
    if c == "status":
        _saida(q.status(conn))
    elif c == "importar":
        _saida(importacao.importar(conn, args.arquivo, args.modo, args.forcar))
    elif c == "buscar":
        if args.dimensao:
            _saida({"dimensao": args.dimensao, "resultados": _limpar(q.buscar(conn, args.dimensao, args.termo,
                                                                              args.limite))})
        else:
            _saida({k: _limpar(v) for k, v in q.busca_rapida(conn, args.termo, args.limite).items()})
    elif c in ("resumo", "ranking", "detalhar", "exportar", "dashboard"):
        f, aplicados = _filtros(conn, args)
        if c == "resumo":
            _saida({**q.resumo(conn, f), "filtros_aplicados": aplicados})
        elif c == "ranking":
            r = q.ranking(conn, args.dimensao, f, args.limite)
            r["itens"] = _limpar(r["itens"])
            _saida({**r, "filtros_aplicados": aplicados})
        elif c == "detalhar":
            _saida({**q.detalhar(conn, f, args.pagina, args.por_pagina), "filtros_aplicados": aplicados})
        elif c == "exportar":
            _saida({**_exportar(conn, f, args.saida), "filtros_aplicados": aplicados})
        else:
            args.saida.write_text(dashboard.gerar(conn, f, aplicados, args.titulo), encoding="utf-8")
            _saida({"arquivo": str(args.saida.resolve()), "filtros_aplicados": aplicados})
    elif c == "historico":
        escolha = q.escolher(args.dimensao, args.nome, q.buscar(conn, args.dimensao, args.nome, 10))[0]
        _saida(q.historico_anual(conn, args.dimensao, escolha["chave"]))
    elif c == "comparar":
        _saida(q.comparar_importacoes(conn, args.dimensao, args.limite))
    elif c == "pendentes":
        _saida(q.pendentes(conn, args.limite))
    elif c == "unificar":
        _saida(q.unificar(conn, args.origem_id, args.destino_id))
    elif c == "marcar":
        q.marcar(conn, args.instituicao_id, args.qualidade)
        _saida({"ok": True})
    return 0


def _limpar(itens: list[dict]) -> list[dict]:
    return [{"nome": i["nome"], "alunos": i["alunos"], "interesses": i["interesses"],
             "percentual_dos_alunos": i["percentual_dos_alunos"]} for i in itens]


def _exportar(conn, f, saida: Path) -> dict:
    linhas = q.detalhar(conn, f, 1, 200000)["alunos"]
    colunas = list(linhas[0].keys()) if linhas else ["cadastro"]
    if saida.suffix.lower() == ".xlsx":
        try:
            from openpyxl import Workbook
        except ImportError:
            saida = saida.with_suffix(".csv")
        else:
            wb = Workbook(write_only=True)
            ws = wb.create_sheet("Alunos")
            ws.append(colunas)
            for l in linhas:
                ws.append([l[c] for c in colunas])
            wb.save(saida)
            return {"arquivo": str(saida.resolve()), "linhas": len(linhas)}
    with open(saida, "w", newline="", encoding="utf-8-sig") as arq:
        w = csv.writer(arq, delimiter=";")
        w.writerow(colunas)
        w.writerows([l[c] for c in colunas] for l in linhas)
    return {"arquivo": str(saida.resolve()), "linhas": len(linhas)}


if __name__ == "__main__":
    sys.exit(main())
