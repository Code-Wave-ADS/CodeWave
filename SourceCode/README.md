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
├── requirements.txt
├── .env.example
├── .gitignore
└── data/
    └── steam.csv
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
