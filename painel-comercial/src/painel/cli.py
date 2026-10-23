"""Linha de comando: painel migrar | importar | criar-usuario | recalcular | servir."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path


def _imprimir_relatorio(r: dict) -> None:
    resumo = r.get("resumo") or {}
    print(f"Importação #{r['id']} · {r['fonte']} · modo {r['modo']} · {r['status']} "
          f"em {(r.get('duracao_ms') or 0) / 1000:.1f} s")
    print(f"  Linhas lidas: {r['linhas_lidas']:,} · ignoradas: {r['linhas_ignoradas']:,} · "
          f"erros: {r['total_erros']:,} · avisos: {r['total_avisos']:,}".replace(",", "."))
    for entidade in ("alunos", "interesses", "instituicoes", "volume_cursos", "volume_cidades", "volume_escolas",
                     "cadastros_novos"):
        if entidade in resumo:
            itens = " · ".join(f"{k} {v:,}".replace(",", ".") for k, v in resumo[entidade].items())
            print(f"  {entidade}: {itens}")
    for o in resumo.get("ocorrencias", []):
        print(f"  [{o['severidade']}] {o['codigo']}: {o['quantidade']:,}".replace(",", "."))
    if r.get("mensagem"):
        print(f"  {r['mensagem']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="painel", description="Painel de Inteligência Comercial")
    sub = parser.add_subparsers(dest="comando", required=True)

    sub.add_parser("migrar", help="cria/atualiza as tabelas do banco")

    p_imp = sub.add_parser("importar", help="importa uma planilha (.xlsx ou .csv)")
    p_imp.add_argument("arquivo", type=Path)
    p_imp.add_argument("--modo", choices=["completo", "incremental"], default="completo")
    p_imp.add_argument("--forcar", action="store_true",
                       help="reimporta arquivo repetido e ignora a trava de remoção excessiva")
    p_imp.add_argument("--json", action="store_true", help="imprime o relatório em JSON")

    p_usr = sub.add_parser("criar-usuario", help="cria ou atualiza um usuário")
    p_usr.add_argument("email")
    p_usr.add_argument("nome")
    p_usr.add_argument("--papel", choices=["admin", "gestor", "analista", "leitor"], default="leitor")
    p_usr.add_argument("--senha", help="se omitida, é perguntada no terminal")

    p_chave = sub.add_parser("criar-chave", help="cria uma chave de API (ex.: conector do Claude)")
    p_chave.add_argument("email", help="usuário dono da chave")
    p_chave.add_argument("nome", help="ex.: 'Conector Claude'")
    p_chave.add_argument("--escopo", action="append", default=None, help="padrão: consulta")

    sub.add_parser("recalcular", help="recalcula as visões analíticas (sem importar)")

    p_srv = sub.add_parser("servir", help="sobe a API, o painel e o endpoint MCP")
    p_srv.add_argument("--host", default="127.0.0.1")
    p_srv.add_argument("--porta", type=int, default=8000)

    p_mcp = sub.add_parser("mcp-stdio", help="servidor MCP via stdio (Claude Desktop / Claude Code local)")
    p_mcp.add_argument("--email", required=True, help="usuário em nome de quem as consultas são registradas")

    args = parser.parse_args(argv)

    from . import db
    try:
        return _executar(args)
    finally:
        db.fechar_pool()


def _executar(args: argparse.Namespace) -> int:
    from . import db

    if args.comando == "migrar":
        novas = db.migrar()
        print("Migrations aplicadas: " + (", ".join(novas) if novas else "nenhuma (banco já atualizado)"))
    elif args.comando == "importar":
        from .importacao.leitor import ArquivoInvalido
        from .importacao.servico import ImportacaoRejeitada, importar, relatorio
        try:
            r = importar(args.arquivo, modo=args.modo, forcar=args.forcar)
        except ArquivoInvalido as e:
            print(f"Arquivo inválido: {e}", file=sys.stderr)
            return 2
        except ImportacaoRejeitada as e:
            print(f"Importação rejeitada: {e}", file=sys.stderr)
            if e.importacao_id:
                _imprimir_relatorio(relatorio(e.importacao_id))
            return 3
        print(json.dumps(r, default=str, ensure_ascii=False, indent=2)) if args.json else _imprimir_relatorio(r)
    elif args.comando == "criar-usuario":
        from .seguranca import usuarios
        senha = args.senha or getpass.getpass("Senha: ")
        u = usuarios.salvar_usuario(args.email, args.nome, args.papel, senha)
        print(f"Usuário {u['email']} ({u['papel']}) salvo.")
    elif args.comando == "criar-chave":
        from .seguranca import usuarios
        u = usuarios.buscar_por_email(args.email)
        if u is None:
            print("Usuário não encontrado.", file=sys.stderr)
            return 2
        chave = usuarios.criar_chave_api(u["id"], args.nome, args.escopo or ["consulta"])
        print("Chave criada. Guarde agora; ela não será exibida de novo:")
        print(chave)
    elif args.comando == "recalcular":
        from .importacao.servico import atualizar_camada_analitica
        with db.conexao() as conn:
            atualizar_camada_analitica(conn, None)
        print("Visões analíticas recalculadas.")
    elif args.comando == "servir":
        import uvicorn
        uvicorn.run("painel.api.app:criar_app", factory=True, host=args.host, port=args.porta)
    elif args.comando == "mcp-stdio":
        from .mcp.servidor import executar_stdio
        executar_stdio(args.email)
    return 0


if __name__ == "__main__":
    sys.exit(main())
