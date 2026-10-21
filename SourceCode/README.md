# Steam Code Wave Bot

Bot do Telegram em Python que usa:
- python-telegram-bot
- Ollama
- Pandas
- Dataset da Steam

## Estrutura

```text
SourceCode/
├── bot.py
├── agent.py
├── steam_analytics.py
<<<<<<< HEAD
=======
├── steam_countries.py
>>>>>>> 5379140 (Vinculação dos principais idiomas ao bot)
├── requirements.txt
├── .env.example
├── .gitignore
└── data/
<<<<<<< HEAD
    └── steam.csv
=======
    ├── steam.csv
    └── paises_steam.json
>>>>>>> 5379140 (Vinculação dos principais idiomas ao bot)
```

## Configuração

1. Crie `.env` na raiz:

```env
TELEGRAM_TOKEN=SEU_NOVO_TOKEN
OLLAMA_MODEL=qwen2.5-coder:7b
STEAM_CSV=data/steam.csv
```

2. Coloque a base completa em `data/steam.csv`.

3. Instale:

```bash
pip install -r requirements.txt
```

4. Baixe o modelo:

```bash
ollama pull qwen2.5-coder:7b
```

5. Rode:

```bash
python bot.py
```

Perguntas de exemplo:
- Qual gênero tem mais jogos?
- Qual gênero está em alta?
- Qual plataforma aparece mais?
- Qual gênero tem mais avaliações positivas?
- Qual é o preço médio dos jogos?
- Quais jogos têm mais avaliações positivas?
<<<<<<< HEAD
=======

## Ranking histórico de usuários por país

O bot reconhece perguntas como “Quais países têm mais usuários Steam?” e responde com um ranking de referência, sem chamar o Ollama para inventar os números. Os dados ficam em `data/paises_steam.json` e são servidos por `steam_countries.py`.

**Limitação importante:** a Steam não publica um ranking oficial, completo e atual de contas/jogadores por país. O ranking incorporado é uma estimativa histórica secundária, baseada em fontes publicadas sobre perfis públicos/usuários identificáveis. Não representa jogadores simultâneos, compradores de jogos ou o total atual de usuários. A resposta do bot inclui a fonte e essa ressalva. Atualize os dados somente quando uma fonte verificável, com período e metodologia claros, estiver disponível.

Fonte principal: https://worldpopulationreview.com/country-rankings/steam-users-by-country
Referência histórica/metodológica: https://steamcommunity.com/sharedfiles/filedetails/?id=923012519
>>>>>>> 5379140 (Vinculação dos principais idiomas ao bot)
