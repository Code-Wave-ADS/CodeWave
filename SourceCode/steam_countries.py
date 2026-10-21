from __future__ import annotations

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "paises_steam.json"


def consultar_ranking_paises(limite: int = 10) -> str:
    """Retorna um ranking histórico de estimativas de usuários Steam por país.

    Os números vêm de uma fonte secundária e não são contagens oficiais/atuais.
    """
    with DATA_FILE.open("r", encoding="utf-8") as arquivo:
        dados = json.load(arquivo)

    paises = sorted(
        dados["dados_historicos"],
        key=lambda pais: pais["usuarios_estimados"],
        reverse=True,
    )

    resposta = [
        f"{dados['titulo']} (ranking de referência)",
        "",
    ]
    for posicao, pais in enumerate(paises[:max(1, limite)], start=1):
        quantidade = pais["usuarios_estimados"]
        resposta.append(f"{posicao}. {pais['pais']} — cerca de {quantidade:,}".replace(",", ".") + " usuários estimados")

    resposta.extend([
        "",
        "Importante: estes são números históricos aproximados de uma fonte secundária, não uma contagem oficial ou atual da Steam. Não representam jogadores simultâneos nem compradores de jogos. A disponibilidade de perfis públicos varia por país.",
        f"Fonte: {dados['fonte_nome']}",
        f"Dados: {dados['fonte_url']}",
        f"Referência metodológica: {dados['metodologia_url']}",
    ])
    return "\n".join(resposta)
